from inspect import currentframe, stack
import logging
import os
import shutil
import string
import sys
from typing import Any, List, Optional, Union
from semver import Version
import yaml
import hashlib
from jinja2 import Environment, FileSystemLoader, Template
from src.ostrichException import OstrichException
from subprocess import run, CompletedProcess
import subprocess
from pathlib import Path
import jsonschema
from envsubst import envsubst
from glom import glom
import copy

class RobustLoggingHandler(logging.StreamHandler):
    """
    Enhanced StreamHandler that gracefully handles invalid handles, 
    particularly useful in Windows environments and parallel test execution.
    """
    def emit(self, record):
        try:
            super().emit(record)
        except OSError as exc:
            if os.name == 'nt' and getattr(exc, 'winerror', 0) == 6:
                return
            raise

# Global execution state
configAll = {}
jinja_environment = None
active_working_directory = None
global_jinja_template = None

class OstrichRuntimeContext:
    """
    Manages the parameters and state for a single Ostrich execution session.
    """
    def __init__(self):
        self.usage = False
        self.debug = False
        self.dryRun = False
        self.rmTmpDir = False
        self.noDeps = False
        self.skip = []
        self.executedTasks = []
        self.userOutput = False
        self.pluginFile = "ostrich.yaml"
        self.kubeConfig: Optional[str] = None
        self.operation = ""
        self.operationParams = []
        self.registry: Optional[str] = None
        self.tmpdir: Optional[str] = None
        self.pluginTmpDir: Optional[str] = None
        self.loglevel = logging.INFO
        self.forceTmpDir = False
        self.deletePluginTmpDir = True
        self.nologo = False
        self.skipTlsVerify = False
        self.parsedPluginConfig: Any = None

    def initialize_plugin_context(self):
        """Loads and prepares the plugin configuration."""
        try:
            logging.debug("Initializing context from %s", self.pluginFile)
            
            raw_content = None
            # Search for content with supported encodings
            for enc in ['utf-8-sig', 'utf-16']:
                try:
                    with open(self.pluginFile, 'r', encoding=enc) as f:
                        raw_content = f.read()
                        break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            
            if raw_content is None:
                with open(self.pluginFile, 'r') as f:
                    raw_content = f.read()

            # Prepare environmental data for templating
            context_data = os.environ.copy()
            settings_path = Path(get_configuration_base()) / "env.yaml"
            if settings_path.exists():
                try:
                    with open(settings_path, 'r') as f:
                        extra_settings = yaml.safe_load(f)
                        if extra_settings:
                            context_data.update(extra_settings)
                except Exception as err:
                    logging.warning("Failed to incorporate env.yaml: %s", err)

            engine = Environment(variable_start_string='[[', variable_end_string=']]')
            try:
                processed_content = engine.from_string(raw_content).render(env=context_data)
            except Exception as render_err:
                raise OstrichException(f"Templating failure in {self.pluginFile}: {render_err}")

            processed_content = envsubst(processed_content)
            logging.debug("Expanded configuration:\n%s", processed_content)
            self.parsedPluginConfig = yaml.safe_load(processed_content)
            
            # Validate against schema if available
            if self.parsedPluginConfig:
                kind = self.fetch_plugin_setting("template.kind", None)
                if kind:
                    try:
                        tpl_path = locate_template_directory(str(kind))
                        schema_file = Path(tpl_path) / "_doc" / "schema.yaml"
                        if schema_file.exists():
                            logging.debug("Validating configuration against %s", schema_file)
                            with open(schema_file, 'r') as sf:
                                rules = yaml.safe_load(sf)
                            jsonschema.validate(instance=self.parsedPluginConfig, schema=rules)
                    except (OstrichException, jsonschema.exceptions.ValidationError) as validation_err:
                        if isinstance(validation_err, OstrichException):
                            pass # Template not found, skip
                        else:
                            key_path = ".".join(map(str, validation_err.path))
                            prefix = f"Violation at '{key_path}': " if key_path else ""
                            raise OstrichException(f"Schema validation error in {self.pluginFile}: {prefix}{validation_err.message}")

            self.parsedPluginConfig['params'] = self
        except yaml.YAMLError as y_err:
            raise OstrichException(f"YAML syntax error in {self.pluginFile}: {y_err}")
        except Exception as generic_err:
            raise OstrichException(f"Resource loading failed for {self.pluginFile}: {generic_err}")

    def fetch_plugin_setting(self, path_key: str, fallback="_UNDEFINED_"):
        """Retrieves a nested configuration value using a dot-separated key."""
        try:
            nodes = path_key.split(".")
            cursor = self.parsedPluginConfig
            for node in nodes:
                cursor = cursor[node]
            return cursor
        except Exception:
            if fallback == "_UNDEFINED_":
                logging.fatal("Mandatory parameter '%s' missing in %s", path_key, self.pluginFile)
                raise
            return fallback

    def parse_cli_arguments(self):
        """Extracts standard Ostrich options from the operation parameters."""
        remaining = []
        idx = 0
        input_args = self.operationParams
        while idx < len(input_args):
            arg = input_args[idx]
            if arg in ['-o', '--output']:
                if idx + 1 < len(input_args):
                    self.tmpdir = input_args[idx+1]
                    self.userOutput = True
                    idx += 2
                else:
                    raise OstrichException("Flag %s requires a path" % arg)
            elif arg in ['-dr', '--dry-run']:
                self.dryRun = True
                if self.tmpdir is None:
                    self.tmpdir = "dry-run"
                idx += 1
            elif arg == '--rm':
                self.rmTmpDir = True
                idx += 1
            elif arg in ['-d', '--debug']:
                logging.getLogger().setLevel(logging.DEBUG)
                self.loglevel = logging.DEBUG
                idx += 1
            elif arg == '--nologo':
                self.nologo = True
                idx += 1
            elif arg == '--force':
                self.forceTmpDir = True
                idx += 1
            elif arg in ['-h', '--help', 'help']:
                self.usage = True
                idx += 1
            elif arg == '--skip-tls-verify':
                self.skipTlsVerify = True
                idx += 1
            else:
                remaining.append(arg)
                idx += 1
        self.operationParams = remaining

# Compatibility alias
Params = OstrichRuntimeContext
Params.loadPluginConf = OstrichRuntimeContext.initialize_plugin_context
Params.getPluginConf = OstrichRuntimeContext.fetch_plugin_setting
Params.collectStandardArgs = OstrichRuntimeContext.parse_cli_arguments

def verify_execution(command_list):
    """Executes a command and raises an exception if it fails."""
    if run(command_list).returncode != 0:
        raise OstrichException("Command failed: %s" % " ".join(command_list))

def get_binary_root():
    """Returns the absolute path to the Ostrich SDK base directory."""
    return str(Path(__file__).resolve().parent.parent)

def get_custom_template_base():
    return get_configuration_base() + "/templates"

def get_bundled_template_base():
    return get_binary_root() + "/templates"

def get_testing_template_base():
    return get_binary_root() + "/test-templates"

def locate_template_directory(identifier: str):
    """Finds the filesystem path for a given template identifier."""
    target_id = str(identifier)
    search_origins = [get_bundled_template_base(), get_testing_template_base(), get_custom_template_base()]
    
    # Priority 1: Match by direct folder name
    for folder in search_origins:
        candidate = Path(folder) / target_id
        if candidate.is_dir():
            return str(candidate)
            
    # Priority 2: Match by internal metadata 'name' attribute
    for folder in search_origins:
        base_path = Path(folder)
        if not base_path.exists():
            continue
        for entry in base_path.iterdir():
            if entry.is_dir() and entry.name != "global":
                manifest = entry / "template.yaml"
                if manifest.exists():
                    try:
                        with open(manifest, 'r') as f:
                            meta = yaml.safe_load(f)
                            if meta and meta.get('name') == target_id:
                                return str(entry)
                    except Exception:
                        continue

    raise OstrichException("Template resource '%s' not located" % target_id)

def define_working_location(path):
    global active_working_directory
    active_working_directory = path

def fetch_working_location():
    return active_working_directory

# --- Template Engine Logic ---

def filter_resolve_local(path_str):
    if not path_str:
        raise OstrichException("Relative path filter received empty input" + get_diagnostic_context())
    if os.path.isabs(path_str):
        return path_str.replace("\\", "/")
    return os.path.normpath(os.path.join(active_working_directory, path_str)).replace("\\", "/")

def filter_strip_slashes(val):
    if val == "": return ""
    if not val:
        raise OstrichException("Slug filter received empty input" + get_diagnostic_context())
    return str(val).rstrip("/\\")
    
def filter_md5(text):
    if not text:
        raise OstrichException("MD5 filter received empty input" + get_diagnostic_context())
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def filter_tpl_asset(filename):
    if not filename:
        raise OstrichException("Asset lookup received empty input" + get_diagnostic_context())
    return (configAll['_ostrich']['templateLocation'] + "/" + filename).replace("\\", "/")

def filter_global_asset(filename):
    if not filename:
        raise OstrichException("Global asset lookup received empty input" + get_diagnostic_context())
    return (get_bundled_template_base() + "/" + filename).replace("\\", "/")

def filter_instance_asset(filename):
    return os.path.abspath(configAll['_ostrich']['tmpdir'] + "/" + filename).replace("\\", "/")

def filter_operation_asset(filename):
    if not filename:
        raise OstrichException("Job asset lookup received empty input" + get_diagnostic_context())
    base = configAll['_ostrich']['templateLocation']
    op = configAll['_ostrich']['operation']
    return (f"{base}/{op}/{filename}").replace("\\", "/")

def filter_strip_snapshot(version_str):
    if not version_str:
        raise OstrichException("Snapshot trimmer received empty input" + get_diagnostic_context())
    return version_str.split("-")[0]

def wrapped_basename(p): return os.path.basename(p)
def wrapped_dirname(p): 
    res = os.path.dirname(p)
    return res if res else "."

def format_boolean(val):
    if isinstance(val, bool):
        return "true" if val else "false"
    return val

def serialize_yaml(obj): return yaml.dump(obj)

def validate_min_version(current, required, label):
    if not current:
        raise OstrichException(f"Version missing for check at {label}")
    if Version.parse(current) < Version.parse(required):
        raise OstrichException(f"Requirement failed: {current} @ {label} is below minimum {required}")
    return current

def validate_max_version(current, limit, label):
    if not current:
        raise OstrichException(f"Version missing for check at {label}")
    if Version.parse(current) > Version.parse(limit):
        raise OstrichException(f"Requirement failed: {current} @ {label} exceeds maximum {limit}")
    return current

def normalize_to_posix(path_val):
    if not path_val: return path_val
    abs_p = os.path.abspath(path_val)
    if os.name == 'nt':
        drive, body = os.path.splitdrive(abs_p)
        if drive:
            return "/" + drive[0].lower() + body.replace('\\', '/')
    return abs_p.replace('\\', '/')

def filter_input_mapping(subpath, key_name):
    lookup = f"template.params.input.{key_name}"
    mapped_base = glom(configAll, lookup, default=None)
    if mapped_base is None:
        raise OstrichException(f"Configuration key '{lookup}' specifically required but undefined")
    
    root_path = filter_resolve_local(mapped_base)
    if subpath:
        return os.path.normpath(os.path.join(root_path, subpath)).replace("\\", "/")
    return root_path

def global_raise_error(reason):
    raise OstrichException(reason)

def get_macro_lineno():
    """Extracts the template line number where a macro or filter was invoked."""
    target_frame = None
    for info in stack():
        if info.frame.f_globals.get("__jinja_template__"):
            target_frame = info.frame.f_globals.get("__jinja_template__")
            break
    if target_frame:
        return target_frame.get_corresponding_lineno(currentframe().f_back.f_lineno)
    return 0

def get_diagnostic_context():
    """Generates a string describing the current template location for errors."""
    active_tpl = None
    for info in stack():
        if info.frame.f_globals.get("__jinja_template__"):
            active_tpl = info.frame.f_globals.get("__jinja_template__")
            break
    if not active_tpl: return ""
    
    if active_tpl == global_jinja_template:
        return " at line %d" % get_macro_lineno()
    else:
        line = active_tpl.get_corresponding_lineno(currentframe().f_back.f_lineno)
        return " in %s at line %d" % (active_tpl, line)

def global_get_nested(path):
    ctx = get_diagnostic_context()
    pointer = configAll
    chain = ""
    for segment in path.split("."):
        if pointer is None: return ""
        chain += segment + "."
        if segment not in pointer:
            raise OstrichException(f"Nested property '{chain[:-1]}' is undefined{ctx}")
        pointer = pointer[segment]
    return pointer

def global_safe_get(path):
    pointer = configAll
    for segment in path.split("."):
        if pointer is None or segment not in pointer:
            return ""
        pointer = pointer[segment]
    return pointer

def check_debug_status():
    return configAll['_ostrich']['loglevel'] < logging.INFO

def fetch_env_var(name): return os.getenv(name)

def sub_render(text): return render_template_string(text, False)

def get_configuration_base():
    return str(Path.home() / ".ostrich")

def get_tooling_config_path():
    return get_configuration_base() + "/sdk-config"

def get_main_config_file():
    return get_tooling_config_path() + "/config.yaml"

def read_yaml_safe(path_to_file) -> dict:
    if not os.path.isfile(path_to_file):
        return {}
    with open(path_to_file, 'r') as stream:
        data = yaml.safe_load(stream)
        return data if data else {}

def load_system_config():
    return read_yaml_safe(get_main_config_file())

def register_extensions(env_obj, is_main=True):
    """Registers filters and globals for a Jinja environment."""
    env_obj.filters.update({
        'here': filter_resolve_local,
        'noslash': filter_strip_slashes,
        'md5hash': filter_md5,
        'fromTemplate': filter_tpl_asset,
        'fromTemplates': filter_global_asset,
        'fromJob': filter_operation_asset,
        'fromTemplateInstance': filter_instance_asset,
        'nosnapshot': filter_strip_snapshot,
        'basename': wrapped_basename,
        'dirname': wrapped_dirname,
        'bool': format_boolean,
        'yaml': serialize_yaml,
        'minVersion': validate_min_version,
        'maxVersion': validate_max_version,
        'toUnixPath': normalize_to_posix,
        'input': filter_input_mapping
    })
    
    env_obj.globals.update({
        'raise': global_raise_error,
        'get': global_get_nested,
        '_': global_safe_get,
        'isDebugEnabled': check_debug_status,
        'env': fetch_env_var
    })
    
    # Add project-specific custom filters/globals if defined
    if is_main:
        env_obj.filters['render'] = sub_render

def addFilter(name, func):
    """Jinja2 filter registration hook."""
    if jinja_environment:
        jinja_environment.filters[name] = func

def addGlobal(name, obj):
    """Jinja2 global registration hook."""
    if jinja_environment:
        jinja_environment.globals[name] = obj

def execute_jinja_rendering(template_body: str, context_data: dict, enable_recursive_render: bool = False):
    global configAll, global_jinja_template, jinja_environment
    configAll = context_data

    jinja_environment = Environment(
        block_start_string='[%',
        block_end_string='%]',
        variable_start_string='[[',
        variable_end_string=']]',
        comment_start_string='[#',
        comment_end_string='#]',
        loader=FileSystemLoader("/")
    )
    
    register_extensions(jinja_environment, enable_recursive_render)

    # Execute system-wide pre-render logic
    pre_sys = f"{get_bundled_template_base()}/global/pretemplate.py"
    if os.path.exists(pre_sys):
        logging.debug("Running system pre-hook: %s", pre_sys)
        with open(pre_sys, "r") as ps:
            script = ps.read()
            # Provide symbols to the execution context
            sandbox = {
                "env": jinja_environment, 
                "params": configAll,
                "addFilter": addFilter,
                "addGlobal": addGlobal
            }
            try:
                exec(script, globals(), sandbox)
            except Exception as pre_err:
                logging.exception(pre_err)
                raise OstrichException(f"Global pre-render script failed: {pre_err}")

    # Execute template-local pre-render logic
    tpl_loc = configAll['_ostrich']['templateLocation']
    pre_local = f"{tpl_loc}/pretemplate.py"
    if os.path.exists(pre_local):
        logging.debug("Running local pre-hook: %s", pre_local)
        with open(pre_local, "r") as pl:
            script = pl.read()
            sandbox = {
                "env": jinja_environment, 
                "params": configAll,
                "addFilter": addFilter,
                "addGlobal": addGlobal
            }
            try:
                exec(script, globals(), sandbox)
            except Exception as loc_err:
                logging.exception(loc_err)
                raise OstrichException(f"Local pre-render script failed: {loc_err}")

    try:
        global_jinja_template = jinja_environment.from_string(template_body)
        return global_jinja_template.render(configAll)
    except Exception as exc:
        details = " ".join(map(str, exc.args))
        if getattr(exc, 'filename', None): details += f" in {exc.filename}"
        if getattr(exc, 'lineno', None): details += f" at line {exc.lineno}"
        origin = configAll['_ostrich'].get('currentfile', 'unknown')
        raise OstrichException(f"Rendering error in {origin}: [{type(exc).__name__}] {details}")

def deep_merge_dicts(base, overlay):
    """Recursively merges dictionary values from overlay into base."""
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge_dicts(base[key], value)
        else:
            base[key] = value

def build_merged_configuration(search_dir: str, user_config: Any, ctx: OstrichRuntimeContext):
    global configAll
    configAll = user_config
    configAll['_ostrich'] = {
        'loglevel': ctx.loglevel,
        'operation': "",
        'tmpdir': ctx.tmpdir
    }

    # Load multi-level metadata
    levels = [
        (f"{search_dir}/../global/config.yaml", "global shared"),
        (f"{search_dir}/config.yaml", "template specific")
    ]
    
    meta_accum = {}
    for path, desc in levels:
        if os.path.exists(path):
            logging.debug("Loading %s metadata from %s", desc, path)
            with open(path) as f:
                deep_merge_dicts(meta_accum, yaml.safe_load(f))

    # Load and template default values
    defaults = {}
    default_path = f"{search_dir}/default.yaml"
    if os.path.exists(default_path):
        logging.debug("Processing defaults: %s", default_path)
        with open(default_path) as f:
            raw_defaults = f.read()
        
        tpl_engine = Environment(variable_start_string='[[', variable_end_string=']]')
        try:
            ready_defaults = tpl_engine.from_string(raw_defaults).render(**configAll)
            defaults = yaml.safe_load(ready_defaults) or {}
        except Exception as def_err:
            raise OstrichException(f"Defaults templating failed in {search_dir}: {def_err}")

    # Final prioritization: User Config > Defaults
    deep_merge_dicts(defaults, configAll)
    configAll = defaults
    ctx.parsedPluginConfig = configAll

    # Populate final internal context
    configAll['_ostrich'].update({
        'sdkconfig': meta_accum,
        'templateLocation': locate_template_directory(ctx.fetch_plugin_setting("template.kind")),
        'templateRoot': get_bundled_template_base(),
        'localconfig': load_system_config()
    })
    
    return configAll

def process_template_suite(source_dir: str, config_bundle: Any, ctx: OstrichRuntimeContext, action_callback):
    """Walks through a template directory and applies the specified action to each file."""
    logging.debug("Initiating template suite processing for %s", source_dir)
    
    global configAll
    configAll = build_merged_configuration(source_dir, config_bundle, ctx)
    
    base_tpl_path = locate_template_directory(ctx.fetch_plugin_setting("template.kind"))
    
    for current_dir, subdirs, files in os.walk(source_dir):
        relative_path = os.path.relpath(current_dir, base_tpl_path)
        relative_path = "" if relative_path == "." else relative_path.replace("\\", "/")
        
        if relative_path.startswith("_"):
            continue # Metadata directories
            
        configAll['_ostrich']['operation'] = relative_path.split("/")[0]

        for entry in files:
            configAll['_ostrich']['currentfile'] = entry
            full_src = f"{current_dir}/{entry}"
            
            if entry.endswith(".tmpl"):
                with open(full_src, 'r') as f:
                    content = f.read()
                rendered = render_template_string(content, True)
                
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    print(f"--- Render result for {entry} ---\n{rendered}\n--- End ---")
                
                action_callback(rendered, f"{relative_path}/{entry[:-5]}", ctx)
            else:
                try:
                    with open(full_src, 'r') as f:
                        content = f.read()
                    action_callback(content, f"{relative_path}/{entry}", ctx)
                except UnicodeDecodeError:
                    # Binary file fallback
                    target_abs = Path(ctx.tmpdir) / relative_path
                    target_abs.mkdir(parents=True, exist_ok=True)
                    shutil.copy(full_src, target_abs / entry)

# Compatibility helpers
def setLocation(p): define_working_location(p)
def getLocation(): return fetch_working_location()
def root(): return get_binary_root()
def extraTemplateRoot(): return get_custom_template_base()
def templateRoot(): return get_bundled_template_base()
def testTemplateRoot(): return get_testing_template_base()
def getTemplatePath(i): return locate_template_directory(i)
def getConfigRoot(): return get_configuration_base()
def getConfigDir(): return get_tooling_config_path()
def getConfigFile(): return get_main_config_file()
def safeLoad(p): return read_yaml_safe(p)
def loadConf(): return load_system_config()
def template(d, c, p, o): return process_template_suite(d, c, p, o)
def helm(*args): return execute_helm_command(*args)
def templateString(t, c): return execute_jinja_rendering(t, c)
def getMergedConfig(d, c, p): return build_merged_configuration(d, c, p)
def toUnixPath(p): return normalize_to_posix(p)

def input_filter(val, key):
    """Path resolution filter for template inputs."""
    loc = fetch_working_location()
    try:
        # Resolve config path: template.params.input.<key>
        lookup_path = f"template.params.input.{key}"
        cfg_val = glom(configAll, lookup_path)
        
        # Construct absolute path
        parts = [loc]
        if cfg_val: parts.append(cfg_val)
        if val: parts.append(val)
        
        return os.path.normpath(os.path.join(*parts)).replace("\\", "/")
    except Exception:
        raise OstrichException(f"Error in 'input' filter for '{key}'")

# Helper alias for external usage
def template(inputDir, config, params, operation):
    return process_template_suite(inputDir, config, params, operation)

def get_isolated_helm_context(root: Path) -> dict:
    """Returns an environment configuration that isolates Helm storage paths."""
    return {
        **os.environ,
        "HELM_CONFIG_HOME": str(root / "config"),
        "HELM_CACHE_HOME":  str(root / "cache"),
        "HELM_DATA_HOME":   str(root / "data"),
    }

def execute_helm_command(*args):
    """Executes a helm command within an isolated environment."""
    if not shutil.which("helm"):
        raise OstrichException("Executable 'helm' not found in system path")

    storage_root = Path(get_configuration_base()) / "helm"
    env_vars = get_isolated_helm_context(storage_root)

    for path_key in ["HELM_CONFIG_HOME", "HELM_CACHE_HOME", "HELM_DATA_HOME"]:
        Path(env_vars[path_key]).mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(["helm", *args], env=env_vars, check=False)
    if proc.returncode != 0:
        raise OstrichException("Helm execution error for arguments: %s" % " ".join(args))