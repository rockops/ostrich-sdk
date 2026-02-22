import logging
import os
import shutil
import sys
import yaml
import hashlib
import subprocess
import jsonschema
from typing import Any, Dict, List, Optional
from pathlib import Path
from semver import Version
from jinja2 import Environment, FileSystemLoader, Template
from envsubst import envsubst
from glom import glom
from .exceptions import OstrichError

class OstrichLogger(logging.StreamHandler):
    def emit(self, entry):
        try:
            super().emit(entry)
        except OSError as exc:
            if os.name == 'nt' and getattr(exc, 'winerror', 0) == 6:
                return
            raise

# Global state
execution_base_dir = ""
current_configuration = []
template_engine: Optional[Template] = None
rendering_env: Optional[Environment] = None

class ExecutionParams:
    def __init__(self):
        self.show_help = False
        self.is_debug = False
        self.is_dry_run = False
        self.recursive_cleanup = False
        self.ignore_dependencies = False
        self.tasks_to_skip = []
        self.completed_tasks = []
        self.custom_output = False
        self.manifest_path = "ostrich.yaml"
        self.kube_path: Optional[str] = None
        self.active_operation = ""
        self.extra_args = []
        self.registry_url: Optional[str] = None
        self.scratch_dir: Optional[str] = None
        self.plugin_scratch: Optional[str] = None
        self.log_threshold = logging.INFO
        self.strictly_initialize = False
        self.cleanup_plugin_scratch = True
        self.suppress_branding = False
        self.allow_unverified_tls = False
        self.raw_manifest_data: Any = None

    def initialize_manifest(self):
        """Loads and processes the ostrich.yaml manifest."""
        try:
            logging.debug("Accessing manifest: %s", self.manifest_path)
            
            raw_text = None
            for enc in ['utf-8-sig', 'utf-16']:
                try:
                    with open(self.manifest_path, 'r', encoding=enc) as f:
                        raw_text = f.read()
                        break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            
            if raw_text is None:
                with open(self.manifest_path, 'r') as f:
                    raw_text = f.read()

            system_env = os.environ.copy()
            dynamic_env_file = os.path.join(InternalPaths.get_config_root(), "env.yaml")
            if os.path.exists(dynamic_env_file):
                try:
                    with open(dynamic_env_file, 'r') as f:
                        override_env = yaml.safe_load(f)
                        if override_env:
                            system_env.update(override_env)
                except Exception as err:
                    logging.warning("Failed to integrate env.yaml: %s", err)

            j2 = Environment(variable_start_string='[[', variable_end_string=']]')
            try:
                raw_text = j2.from_string(raw_text).render(env=system_env)
            except Exception as jerr:
                raise OstrichError(f"Manifest templating failed ({self.manifest_path}): {jerr}")

            raw_text = envsubst(raw_text)
            logging.debug("Processed manifest content:\n%s", raw_text)
            self.raw_manifest_data = yaml.safe_load(raw_text)
            
            if self.raw_manifest_data:
                kind = self.lookup_config("template.kind", None)
                if kind:
                    try:
                        tpl_path = InternalPaths.resolve_template_path(str(kind))
                        validation_schema = os.path.join(tpl_path, "_doc/schema.yaml")
                        if os.path.exists(validation_schema):
                            logging.debug("Schema verification for %s vs %s", self.manifest_path, validation_schema)
                            with open(validation_schema, 'r') as sf:
                                schema_data = yaml.safe_load(sf)
                            jsonschema.validate(instance=self.raw_manifest_data, schema=schema_data)
                    except OstrichError:
                        pass
                    except jsonschema.exceptions.ValidationError as verr:
                        key_path = ".".join(map(str, verr.path))
                        msg = f"Validation Error in {self.manifest_path}"
                        if key_path:
                            msg += f" at '{key_path}'"
                        raise OstrichError(f"{msg}:\n{verr.message}")

            self.raw_manifest_data['params'] = self
        except yaml.YAMLError as yerr:
            raise OstrichError(f"YAML Syntax Error in {self.manifest_path}: {yerr}")
        except Exception as exc:
            raise OstrichError(f"IO Error reading {self.manifest_path}: {exc}")

    def lookup_config(self, accessor: str, fallback="_MANDATORY_"):
        """Retreives a value from the manifest using dot-notation."""
        try:
            ptr = self.raw_manifest_data
            for segment in accessor.split("."):
                ptr = ptr[segment]
            return ptr
        except KeyError:
            if fallback == "_MANDATORY_":
                logging.fatal("Missing required configuration: %s", accessor)
                raise
            return fallback

    def parse_cli_flags(self):
        """Processes standard Ostrich CLI arguments."""
        remaining = []
        cursor = 0
        args = self.extra_args
        while cursor < len(args):
            token = args[cursor]
            if token in ['-o', '--output']:
                if cursor + 1 < len(args):
                    self.scratch_dir = args[cursor+1]
                    self.custom_output = True
                    cursor += 2
                else:
                    raise OstrichError("Option -o/--output requires a directory path.")
            elif token in ['-dr', '--dry-run']:
                self.is_dry_run = True
                if self.scratch_dir is None:
                    self.scratch_dir = "dry-run"
                cursor += 1
            elif token == '--rm':
                self.recursive_cleanup = True
                cursor += 1
            elif token in ['-d', '--debug']:
                logging.getLogger().setLevel(logging.DEBUG)
                self.log_threshold = logging.DEBUG
                cursor += 1
            elif token == '--nologo':
                self.suppress_branding = True
                cursor += 1
            elif token == '--force':
                self.strictly_initialize = True
                cursor += 1
            elif token in ['-h', '--help', 'help']:
                self.show_help = True
                cursor += 1
            elif token == '--skip-tls-verify':
                self.allow_unverified_tls = True
                cursor += 1
            else:
                remaining.append(token)
                cursor += 1
        self.extra_args = remaining

def assert_system_call(cmd: List[str]):
    if subprocess.run(cmd).returncode != 0:
        raise OstrichError(f"Subprocess failure: {' '.join(cmd)}")

class InternalPaths:
    @staticmethod
    def get_binary_root():
        return os.path.abspath(os.path.dirname(sys.argv[0]))

    @staticmethod
    def get_config_root():
        return os.path.expanduser("~") + "/.ostrich"

    @staticmethod
    def get_ext_templates():
        return f"{InternalPaths.get_config_root()}/templates"

    @staticmethod
    def get_builtin_templates():
        return f"{InternalPaths.get_binary_root()}/templates"

    @staticmethod
    def get_test_templates():
        return f"{InternalPaths.get_binary_root()}/test-templates"

    @classmethod
    def resolve_template_path(cls, identifier: str):
        search_roots = [cls.get_builtin_templates(), cls.get_test_templates(), cls.get_ext_templates()]
        
        # Exact match
        for root in search_roots:
            candidate = os.path.join(root, identifier)
            if os.path.isdir(candidate):
                return candidate
                
        # Discovery by metadata
        for root in search_roots:
            if not os.path.exists(root): continue
            for item in os.listdir(root):
                if item == "global": continue
                sub = os.path.join(root, item)
                if os.path.isdir(sub):
                    meta = os.path.join(sub, "template.yaml")
                    if os.path.exists(meta):
                        try:
                            with open(meta, 'r') as f:
                                cfg = yaml.safe_load(f)
                                if cfg and cfg.get('name') == identifier:
                                    return sub
                        except Exception: pass

        raise OstrichError(f"Template '{identifier}' not found in any known locations.")

class TemplateFilters:
    @staticmethod
    def resolve_path(value: str):
        if not value:
            raise OstrichError("Filter 'here' requires a valid path.")
        
        base = execution_base_dir
        if os.path.isabs(value):
            return value.replace("\\", "/")
        return os.path.normpath(os.path.join(base, value)).replace("\\", "/")

    @staticmethod
    def strip_trailing_slashes(value: str):
        if not value: return ""
        return value.rstrip("/").rstrip("\\")

    @staticmethod
    def generate_hash(value: str):
        if not value: raise OstrichError("Cannot hash an empty value.")
        return hashlib.md5(value.encode('utf-8')).hexdigest()

    @staticmethod
    def from_manifest(value: str):
        global current_configuration
        loc = current_configuration['_ostrich']['templateLocation']
        return f"{loc}/{value}".replace("\\", "/")

    @staticmethod
    def from_system(value: str):
        return f"{InternalPaths.get_builtin_templates()}/{value}".replace("\\", "/")

    @staticmethod
    def from_output_root(value: str):
        global current_configuration
        base = current_configuration['_ostrich']['tmpdir']
        return os.path.abspath(f"{base}/{value}").replace("\\", "/")

    @staticmethod
    def from_op_dir(value: str):
        global current_configuration
        ctx = current_configuration['_ostrich']
        return f"{ctx['templateLocation']}/{ctx['operation']}/{value}".replace("\\", "/")

    @staticmethod
    def clear_snapshots(value: str):
        if not value: return ""
        return value.split("-")[0]

    @staticmethod
    def to_yaml_str(obj: Any):
        return yaml.dump(obj)

    @staticmethod
    def verify_version_min(current: str, required: str, field: str):
        if not current: raise OstrichError(f"Unspecified version in {field}")
        if Version.parse(current) < Version.parse(required):
            raise OstrichError(f"Version {current} in {field} is below required {required}")
        return current

    @staticmethod
    def verify_version_max(current: str, maximum: str, field: str):
        if not current: raise OstrichError(f"Unspecified version in {field}")
        if Version.parse(current) > Version.parse(maximum):
            raise OstrichError(f"Version {current} in {field} exceeds maximum {maximum}")
        return current

    @staticmethod
    def convert_to_posix(p: str):
        if not p: return p
        normalized = os.path.abspath(p)
        if os.name == 'nt':
            drive, tail = os.path.splitdrive(normalized)
            if drive:
                return f"/{drive[0].lower()}{tail.replace('\\', '/')}"
        return normalized.replace('\\', '/')

    @staticmethod
    def resolve_input(val, key_name):
        global current_configuration
        full_key = f"template.params.input.{key_name}"
        target = glom(current_configuration, full_key, default=None)
        if target is None:
            raise OstrichError(f"Dynamic input '{key_name}' not resolved in config.")
        
        base_path = TemplateFilters.resolve_path(target)
        if val:
            return os.path.normpath(os.path.join(base_path, val)).replace("\\", "/")
        return base_path

def helm_execute(*args: str):
    if not shutil.which("helm"):
        raise OstrichError("The 'helm' binary is missing from PATH.")

    data_store = Path(InternalPaths.get_config_root()) / "helm"
    env_overrides = {
        **os.environ,
        "HELM_CONFIG_HOME": str(data_store / "config"),
        "HELM_CACHE_HOME":  str(data_store / "cache"),
        "HELM_DATA_HOME":   str(data_store / "data"),
    }

    for path_key in ["HELM_CONFIG_HOME", "HELM_CACHE_HOME", "HELM_DATA_HOME"]:
        Path(env_overrides[path_key]).mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(["helm", *args], env=env_overrides, check=False)
    if proc.returncode != 0:
        raise OstrichError(f"Helm operation failed (args: {' '.join(args)})")

# Re-implementing dict_merge more concisely
def deep_merge(target, source):
    for k, v in source.items():
        if k in target and isinstance(target[k], dict) and isinstance(v, dict):
            deep_merge(target[k], v)
        else:
            target[k] = v

def assemble_merged_config(tpl_dir: str, config_data: Any, params: ExecutionParams):
    global current_configuration
    current_configuration = config_data
    
    current_configuration['_ostrich'] = {
        'loglevel': params.log_threshold,
        'operation': "",
        'tmpdir': params.scratch_dir
    }

    def load_resource(p):
        if os.path.exists(p):
            with open(p) as f:
                return yaml.safe_load(f) or {}
        return {}

    global_cfg = load_resource(f"{tpl_dir}/../global/config.yaml")
    local_cfg = load_resource(f"{tpl_dir}/config.yaml")
    deep_merge(global_cfg, local_cfg)

    default_data = {}
    default_file = f"{tpl_dir}/default.yaml"
    if os.path.exists(default_file):
        with open(default_file, 'r') as f:
            raw_def = f.read()
        try:
            rendered_def = Environment(variable_start_string='[[', variable_end_string=']]').from_string(raw_def).render(**current_configuration)
            default_data = yaml.safe_load(rendered_def) or {}
        except Exception as err:
            raise OstrichError(f"Failed to process default.yaml in {tpl_dir}: {err}")

    deep_merge(default_data, current_configuration)
    current_configuration = default_data
    params.raw_manifest_data = current_configuration

    current_configuration['_ostrich'].update({
        'sdkconfig': global_cfg,
        'templateLocation': InternalPaths.resolve_template_path(params.lookup_config("template.kind")),
        'templateRoot': InternalPaths.get_builtin_templates(),
        'localconfig': load_resource(InternalPaths.get_config_root() + "/sdk-config/config.yaml")
    })
    
    return current_configuration

def process_template(tpl_dir: str, config_bundle: Any, params: ExecutionParams, handler_func):
    logging.debug("Rendering templates from %s", tpl_dir)
    cfg = assemble_merged_config(tpl_dir, config_bundle, params)

    root_path = InternalPaths.resolve_template_path(params.lookup_config("template.kind"))
    for subdir, _, files in os.walk(tpl_dir):
        rel_subdir = os.path.relpath(subdir, root_path)
        if rel_subdir == ".": rel_subdir = ""
        rel_subdir = rel_subdir.replace("\\", "/")

        if rel_subdir.startswith("_"): continue

        cfg['_ostrich']['operation'] = rel_subdir.split("/")[0]

        for fname in files:
            cfg['_ostrich']['currentfile'] = fname
            src_path = os.path.join(subdir, fname)
            
            if fname.endswith(".tmpl"):
                with open(src_path, 'r') as f:
                    content = f.read()
                rendered = render_string(content, True)
                handler_func(rendered, f"{rel_subdir}/{fname[:-5]}", params)
            else:
                try:
                    with open(src_path, 'r') as f:
                        data = f.read()
                    handler_func(data, f"{rel_subdir}/{fname}", params)
                except UnicodeDecodeError:
                    abs_target_dir = os.path.join(params.scratch_dir, rel_subdir)
                    os.makedirs(abs_target_dir, exist_ok=True)
                    shutil.copy(src_path, os.path.join(abs_target_dir, fname))

def addFilter(name, func):
    global rendering_env
    if rendering_env:
        rendering_env.filters[name] = func

def addGlobal(name, func):
    global rendering_env
    if rendering_env:
        rendering_env.globals[name] = func

def render_string(source: str, enable_nested: bool):
    global current_configuration, rendering_env
    
    rendering_env = Environment(
        block_start_string='[%', block_end_string='%]',
        variable_start_string='[[', variable_end_string=']]',
        comment_start_string='[#', comment_end_string='#]',
        loader=FileSystemLoader("/")
    )

    f = TemplateFilters
    rendering_env.filters.update({
        'here': f.resolve_path, 'noslash': f.strip_trailing_slashes,
        'md5hash': f.generate_hash, 'fromTemplate': f.from_manifest,
        'fromTemplates': f.from_system, 'fromJob': f.from_op_dir,
        'fromTemplateInstance': f.from_output_root, 'nosnapshot': f.clear_snapshots,
        'basename': os.path.basename, 'dirname': lambda p: os.path.dirname(p) or ".",
        'bool': lambda b: str(b).lower() if isinstance(b, bool) else b,
        'yaml': f.to_yaml_str, 'minVersion': f.verify_version_min,
        'maxVersion': f.verify_version_max, 'toUnixPath': f.convert_to_posix,
        'input': f.resolve_input
    })

    if enable_nested:
        rendering_env.filters['render'] = lambda s: render_string(s, False)

    rendering_env.globals.update({
        'raise': lambda m: (lambda x: exec('raise OstrichError(x)'))(m), # Hacky but works for lambda
        'get': lambda k: glom(current_configuration, k),
        '_': lambda k: glom(current_configuration, k, default=""),
        'isDebugEnabled': lambda: current_configuration['_ostrich']['loglevel'] < logging.INFO,
        'env': os.getenv
    })

    # Hook for pre-processing scripts
    for script_path in [f"{InternalPaths.get_builtin_templates()}/global/pretemplate.py", 
                        f"{current_configuration['_ostrich']['templateLocation']}/pretemplate.py"]:
        if os.path.exists(script_path):
            with open(script_path, 'r') as sf:
                code = sf.read()
            exec(code, globals(), {'env': rendering_env})

    try:
        return rendering_env.from_string(source).render(current_configuration)
    except Exception as err:
        raise OstrichError(f"Rendering failed for {current_configuration['_ostrich']['currentfile']}: {err}")