import getpass
import json
import logging
import os
import string
import os.path
from os import path
import traceback
import yaml
from glom import glom
from subprocess import run

import src.util as util
from src.ostrichException import OstrichException
from src.template import templateAll

# Shared execution state
runtime_context: util.Params = None
is_dry_run_active: bool = False
system_wide_config: dict = {}
arg_count: int = 0
arg_values: list = []
current_verbosity: int = logging.INFO


# --- Runner Implementations ---

def execute_native_task(op_name: str, ctx: util.Params):
    """
    Launches a Python-based operation within the current runtime process.
    """
    script_target = f"{ctx.tmpdir}/{op_name}/{op_name}.py"
    logging.info("Starting native execution: %s", script_target)
    
    with open(script_target, "r") as src:
        global runtime_context, is_dry_run_active, system_wide_config
        global arg_count, arg_values, current_verbosity
        
        runtime_context = ctx
        is_dry_run_active = ctx.dryRun
        system_wide_config = util.loadConf()
        arg_values = ctx.operationParams
        arg_count = len(ctx.operationParams)
        current_verbosity = ctx.loglevel
        
        payload = src.read()

        try:
            exec(payload, globals())
        except Exception as exc:
            line_no = None
            for frame in traceback.extract_tb(exc.__traceback__):
                if frame.filename == "<string>":
                    line_no = frame.lineno
                    
                    # Compute window for error display
                    start = max(0, line_no - 5)
                    end = line_no + 5
                    
                    logging.error("Failure in %s at line %d: %s", script_target, line_no, exc)
                    lines = payload.split("\n")
                    print("Context snippet:")
                    for i, content in enumerate(lines[start:end], start=start+1):
                        prefix = ">> " if i == line_no else "   "
                        print(f"{prefix}{content}")
                    print("----------------")
                    raise OstrichException(f"Execution failed in {script_target} [Line {line_no}]: {exc}")
            raise


def execute_shell_task(op_name: str, ctx: util.Params):
    """
    Runs a series of local shell commands defined in an operation manifest.
    """
    manifest_path = f"{ctx.tmpdir}/{op_name}/{op_name}.yaml"
    if not os.path.isfile(manifest_path):
        raise OstrichException(f"Operation manifest missing: {manifest_path}")

    spec = util.safeLoad(manifest_path)
    sequence = spec.get("commands", [])
    custom_env = spec.get("env", {})

    process_env = os.environ.copy()
    process_env.update(custom_env)
    
    # Standardize environment for the sub-operation
    process_env.update({
        "LOGLEVEL": str(ctx.loglevel),
        "DRYRUN": str(ctx.dryRun).lower(),
        "TEMPLATE_DIR": ctx.tmpdir,
        "OPERATION": op_name,
        "ARGV": ",".join(ctx.operationParams),
        "ARGC": str(len(ctx.operationParams)),
        "ARGV_JSON": json.dumps(ctx.operationParams)
    })

    for cmd_str in sequence:
        logging.debug("Triggering shell command: %s", cmd_str)
        outcome = run(cmd_str, shell=True, env=process_env)
        if outcome.returncode != 0:
            raise OstrichException(f"Shell task '{cmd_str}' exited with error code {outcome.returncode}")


def execute_container_task(op_name: str, ctx: util.Params):
    """
    Dispatches the operation to be executed within a Docker or Podman container.
    """
    manifest_path = f"{ctx.tmpdir}/{op_name}/{op_name}.yaml"
    if not os.path.isfile(manifest_path):
        raise OstrichException(f"Isolated task manifest missing: {manifest_path}")

    spec = util.safeLoad(manifest_path)
    sequence = spec.get("commands", [])
    container_env = spec.get("env", {}).copy()

    def map_path(original_path):
        """Maps local paths for container visibility. Identity mapping for compatibility."""
        return original_path

    # Prepare environment variables for the container
    container_env.update({
        "LOGLEVEL": str(ctx.loglevel),
        "DRYRUN": str(ctx.dryRun).lower(),
        "TEMPLATE_DIR": map_path(ctx.tmpdir),
        "OPERATION": op_name,
        "ARGV": ",".join(ctx.operationParams),
        "ARGC": str(len(ctx.operationParams)),
        "ARGV_JSON": json.dumps(ctx.operationParams),
        "OST_DEBUG": str(logging.DEBUG),
        "OST_INFO": str(logging.INFO),
        "OST_WARNING": str(logging.WARNING),
        "OST_ERROR": str(logging.ERROR),
        "OST_CRITICAL": str(logging.CRITICAL),
        "OST_DEBUG_MODE": str(ctx.loglevel <= logging.DEBUG).lower()
    })

    driver = ctx.getPluginConf("template.runtime", "docker")
    if driver not in ["docker", "podman"]:
        raise OstrichException(f"Invalid container runtime requested: {driver}")

    # Verify driver availability
    try:
        check = run([driver, "-v"], capture_output=True, text=True)
        if check.returncode != 0:
            raise OstrichException(f"Runtime '{driver}' is installed but non-functional")
    except FileNotFoundError:
        raise OstrichException(f"Command '{driver}' not found in system PATH")

    logging.info("Active container driver: %s", check.stdout.strip())

    def resolve_host_mount_path(local_path):
        """Translates paths for nested container environments (DooD/DinD)."""
        normalized = os.path.normpath(local_path)
        mapping_registry = "/ostrich-volumes.yaml"
        
        if os.path.exists(mapping_registry):
            try:
                with open(mapping_registry, "r") as f:
                    table = yaml.safe_load(f)
                    if table:
                        # Priority to longest container path prefixes
                        table.sort(key=lambda item: len(item.get("container", "")), reverse=True)
                        for entry in table:
                            c_path = entry.get("container")
                            h_path = entry.get("host")
                            if c_path and h_path:
                                cp_norm = os.path.normpath(c_path)
                                hp_norm = os.path.normpath(h_path)
                                if normalized.startswith(cp_norm):
                                    translation = normalized.replace(cp_norm, hp_norm, 1)
                                    logging.debug("Path translation applied: %s -> %s", normalized, translation)
                                    return translation
            except Exception as err:
                logging.warning("Error parsing path mapping table: %s", err)
        return normalized

    # Base container command construction
    base_cmd = [driver, "run", "--rm"]
    for var, val in container_env.items():
        base_cmd.extend(["-e", f"{var}={val}"])
    
    # Volume mounts
    mounts = [
        (os.path.abspath(ctx.tmpdir), map_path(ctx.tmpdir)),
        (util.getLocation(), map_path(util.getLocation())),
        (util.templateRoot(), map_path(util.templateRoot())),
        (util.testTemplateRoot(), map_path(util.testTemplateRoot())),
        (util.extraTemplateRoot(), map_path(util.extraTemplateRoot())),
        ("/var/run/docker.sock", "/var/run/docker.sock")
    ]
    
    for src, dst in mounts:
        # Note: we assume these paths should be mounted if they are defined
        if src:
            base_cmd.extend(["-v", f"{resolve_host_mount_path(src)}:{dst}"])

    # Network configuration
    net_config = ctx.getPluginConf("template.network", None)
    if net_config:
        base_cmd.extend(["--network", net_config])

    # Credential sharing (Docker config)
    dot_docker = os.path.join(os.path.expanduser("~"), ".docker", "config.json")
    if os.path.isfile(dot_docker):
        if ctx.getPluginConf("runner.user", None) or hasattr(os, 'getuid'):
            container_env["DOCKER_CONFIG"] = "/.docker"
            base_cmd.extend(["-v", f"{resolve_host_mount_path(dot_docker)}:/.docker/config.json:ro"])
        else:
            base_cmd.extend(["-v", f"{resolve_host_mount_path(dot_docker)}:/root/.docker/config.json:ro"])

    # Populate /etc/hosts entries
    etc_hosts = "/etc/hosts" if os.name != 'nt' else os.path.join(os.environ.get('SystemRoot', ''), 'System32/drivers/etc/hosts')
    if os.path.isfile(etc_hosts):
        try:
            seen_hosts = set()
            with open(etc_hosts, 'r') as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped or stripped.startswith('#'): continue
                    segments = stripped.split()
                    if len(segments) >= 2:
                        ip_addr = segments[0]
                        # Rudimentary IP validation
                        if all(c in '0123456789.:abcdefABCDEF' for c in ip_addr):
                            for h_name in segments[1:]:
                                if h_name.lower() not in ['localhost', 'ip6-localhost', 'ip6-loopback'] and (h_name, ip_addr) not in seen_hosts:
                                    base_cmd.extend(["--add-host", f"{h_name}:{ip_addr}"])
                                    seen_hosts.add((h_name, ip_addr))
        except Exception as hosts_err:
            logging.warning("Skipped host propagation: %s", hosts_err)

    base_cmd.extend(["-w", map_path(util.getLocation())])

    # Runtime-specific flags
    if driver == "podman":
        base_cmd.extend(["--userns=keep-id", "--security-opt", "label=disable"])
    else:
        req_user = glom(spec, "runner.user", default=ctx.getPluginConf("runner.user", None))
        if req_user:
            base_cmd.extend(["--user", str(req_user)])
        elif hasattr(os, 'getuid'):
            u, g = os.getuid(), os.getgid()
            base_cmd.extend(["--user", f"{u}:{g}"])
            if os.path.exists("/var/run/docker.sock"):
                base_cmd.extend(["--group-add", str(os.stat("/var/run/docker.sock").st_gid)])

    # Dispatch individual commands
    tpl_entrypoint = glom(spec, "runner.entrypoint", default=ctx.getPluginConf("runner.entrypoint", None))
    tpl_image = glom(spec, "runner.image", default=ctx.getPluginConf("runner.image", None))

    for instruction in sequence:
        dispatch_cmd = base_cmd.copy()
        target_entry = tpl_entrypoint
        target_image = tpl_image

        if isinstance(instruction, dict):
            target_image = instruction.get("image", tpl_image)
            target_entry = instruction.get("entrypoint", tpl_entrypoint)
            cmd_payload = instruction.get("cmd", [])
        else:
            cmd_payload = instruction

        if not target_image:
            raise OstrichException(f"No container image defined for {op_name}")

        if target_entry:
            dispatch_cmd.extend(["--entrypoint", target_entry])
        
        dispatch_cmd.append(target_image)

        if isinstance(cmd_payload, list):
            dispatch_cmd.extend(cmd_payload)
        elif isinstance(cmd_payload, str):
            dispatch_cmd.extend(["sh", "-c", cmd_payload])
        elif isinstance(cmd_payload, dict):
            for flag, val in cmd_payload.items():
                dispatch_cmd.append(flag)
                if val is not None: dispatch_cmd.append(str(val))
        else:
            raise OstrichException(f"Malformed command spec in {op_name}")

        logging.debug("Container call: %s", " ".join(map(str, dispatch_cmd)))
        exec_result = run([str(p) for p in dispatch_cmd], shell=False)
        if exec_result.returncode != 0:
            raise OstrichException(f"Task failure inside container: {cmd_payload} (Code {exec_result.returncode})")


def run_workflow_step(op_id: str, ctx: util.Params):
    """
    Handles dependency resolution and execution of a specific workflow operation.
    """
    if not ctx.noDeps:
        dep_manifest = f"{ctx.tmpdir}/{op_id}/dependencies.yaml"
        if os.path.isfile(dep_manifest):
            with open(dep_manifest) as df:
                tree = yaml.safe_load(df)
                for requirement in tree.get('dependencies', []):
                    if requirement in ctx.skip:
                        logging.info("Bypassing skipped dependency: %s", requirement)
                    elif requirement in ctx.executedTasks:
                        logging.info("Dependency already met: %s", requirement)
                    else:
                        ctx.executedTasks.append(requirement)
                        run_workflow_step(requirement, ctx)

    op_root = f"{ctx.tmpdir}/{op_id}"
    if not os.path.isdir(op_root):
        raise OstrichException(f"Operation logic not found: {op_id}")

    # Determine appropriate execution runner
    op_cfg_file = f"{op_root}/{op_id}.yaml"
    found_runner = "_UNDEFINED_"
    if os.path.isfile(op_cfg_file):
        found_runner = glom(util.safeLoad(op_cfg_file), "runner.kind", default="_UNDEFINED_")

    if found_runner == "_UNDEFINED_":
        tpl_cfg_file = f"{ctx.tmpdir}/template.yaml"
        if os.path.isfile(tpl_cfg_file):
            found_runner = glom(util.safeLoad(tpl_cfg_file), "runner.kind", default="inprocess")
        else:
            found_runner = "inprocess"

    logging.info(">>> Executing stage: %s <<<", op_id)
    dispatch_map = {
        "inprocess": execute_native_task,
        "shell": execute_shell_task,
        "container": execute_container_task
    }
    
    if found_runner not in dispatch_map:
        logging.error("Unsupported execution engine: %s", found_runner)
        print("Valid engines: inprocess, shell, container")
        raise OstrichException(f"Invalid runner configuration: {found_runner}")
        
    dispatch_map[found_runner](op_id, ctx)


def orchestrate_execution(ctx: util.Params):
    """Entry point for fulfilling an Ostrich operation request."""
    templateAll(ctx)
    run_workflow_step(ctx.operation, ctx)


# --- Configuration and Help ---

def display_config_help():
    print(r'''                              _              
     ____   ___  _____  ___  |_| ___  __   _  
    / __ \ / __||_   _||   ) | |/ __||  |_| | 
    |(oO)| \__ \  | |  |   \ | |\__ \)   _  | 
    \_\/_/ |___/  |_|  |_|\_\|_||___/|__| |_|_  _
      ||                            ___   __| || | __
      ||                           / __| / _` || |/ /
                                   \__ \| (_| ||   < 
                                   |___/ \__,_||_|\_\

Usage: 
- ost config <action> <key> [value]

Management Commands:
  - help                  : Show this assistance menu
  - list | get            : Enumerate all configuration entries
  - get <target>          : Retrieve value for <target>
  - set <key> <val>       : Define/Update <key> with <val>
  - unset <key>           : Purge <key> from configuration

Authentication:
  - login <svc> <url> <u> <p> : Authenticate with <svc> (e.g., helm)
  - login <svc> list          : Show registered credentials for <svc>
  - logout <svc> <url>        : Remove credentials for <svc> @ <url>
  - token <svc> <url> <t>     : Use a secret token for <svc>
  - token <svc> list          : Enumerate registered tokens
''')


def list_credentials(data: dict, filter_type: str):
    """Displays stored credentials with masked passwords."""
    for entry, secret in data.items():
        parts = entry.split("_")
        if len(parts) > 2 and parts[1] == "credential":
            if filter_type == "list" or parts[0] == filter_type:
                sanitized = secret.split(":")[0] + ":***" if ":" in secret else "***"
                endpoint = entry.replace(f"{parts[0]}_credential_", "")
                print(f"{parts[0]} -> {endpoint}: {sanitized}")


def manage_configuration(ctx: util.Params):
    """Dispatches configuration management actions."""
    ctx.collectStandardArgs()
    params = ctx.operationParams

    if not params:
        display_config_help()
        raise OstrichException("Missing configuration command")

    cmd = params[0]
    if cmd == "help" or ctx.usage:
        display_config_help()
        return
    
    cfg_base = util.get_tooling_config_path()
    cfg_target = util.get_main_config_file()
    os.makedirs(cfg_base, exist_ok=True)

    if cmd in ["get", "list"]:
        if not os.path.isfile(cfg_target):
            logging.info("Configuration storage is empty")
            return
        
        db = util.read_yaml_safe(cfg_target)
        if len(params) == 1:
            for k, v in db.items():
                p = k.split("_")
                masked = v.split(":")[0] + ":***" if len(p) > 2 and p[1] == "credential" and ":" in v else v
                if len(p) > 2 and p[1] == "credential" and ":" not in v: masked = "***"
                print(f"{k} = {masked}")
        else:
            if params[1] in db:
                print(db[params[1]])
            else:
                raise OstrichException(f"Config key '{params[1]}' not found")

    elif cmd == "set":
        if len(params) < 3:
            raise OstrichException("Set command requires both key and value")
        db = util.read_yaml_safe(cfg_target)
        db[params[1]] = params[2]
        with open(cfg_target, 'w') as f:
            yaml.dump(db, f)
        logging.info("Updated key: %s", params[1])

    elif cmd == "unset":
        if len(params) < 2:
            raise OstrichException("Unset command requires a key")
        db = util.read_yaml_safe(cfg_target)
        db.pop(params[1], None)
        with open(cfg_target, 'w') as f:
            yaml.dump(db, f)
        logging.info("Purged key: %s", params[1])

    elif cmd in ["login", "token"]:
        db = util.read_yaml_safe(cfg_target)
        if len(params) < 2:
            raise OstrichException(f"Command '{cmd}' requires a service type")
        
        stype = params[1]
        if stype == "list" or (len(params) > 2 and params[2] == "list"):
            list_credentials(db, stype)
            return

        # Handle interactive vs CLI inputs
        if cmd == "login":
            if len(params) == 5:
                uri, usr, pwd = params[2], params[3], params[4]
            elif len(params) == 3:
                uri, usr = params[2], input(f"{stype} user: ")
                pwd = getpass.getpass()
            else:
                uri = input(f"{stype} address: ")
                usr = input(f"{stype} user: ")
                pwd = getpass.getpass()
            cred_val = f"{usr}:{pwd}"
        else:
            if len(params) == 4:
                uri, cred_val = params[2], params[3]
            elif len(params) == 3:
                uri = params[2]
                cred_val = getpass.getpass(f"{stype} token: ")
            else:
                uri = input(f"{stype} address: ")
                cred_val = getpass.getpass(f"{stype} token: ")

        uri = uri.rstrip("/")
        db[f"{stype}_credential_{uri}"] = cred_val
        with open(cfg_target, 'w') as f:
            yaml.dump(db, f)
        logging.info("Stored %s credentials for %s", cmd, uri)

    elif cmd == "logout":
        if len(params) < 3:
            raise OstrichException("Logout requires service type and address")
        stype, uri = params[1], params[2]
        db = util.read_yaml_safe(cfg_target)
        db.pop(f"{stype}_credential_{uri.rstrip('/')}", None)
        with open(cfg_target, 'w') as f:
            yaml.dump(db, f)
        logging.info("Removed credentials for %s", uri)

# Compatibility aliases
inprocess = execute_native_task
shell = execute_shell_task
container = execute_container_task
task = run_workflow_step
execute = orchestrate_execution
config = manage_configuration
