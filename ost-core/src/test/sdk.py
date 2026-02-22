import json
import logging
import os
import re
import requests
import selectors
import string
import subprocess
import sys
import time
import yaml
from pathlib import Path
from jsonpath_ng.ext import parse
from kubernetes import config, client

def resolve_sdk_resource_path(relative):
    """Calculates the absolute path of a resource based on execution environment."""
    if os.getenv("USE_OSTD", "false").lower() == "true":
        return os.path.normpath(f"/sdk/{relative}").replace("\\", "/")
    
    # Path calculation for host environment
    parent_dir = Path(__file__).resolve().parent
    root_dir = parent_dir.parent.parent
    return str((root_dir / relative).resolve()).replace("\\", "/")

# Terminal Aesthetics
CLR_DEFAULT = '\033[0;m'
CLR_WARN    = '\033[38;5;11m'
CLR_MUTE    = '\033[38;5;8m'
CLR_FAIL    = '\033[38;5;9m'
CLR_SUCCESS = '\033[38;5;10m'
CLR_INFO    = '\033[38;5;12m'
CLR_STRESS  = '\033[38;5;13m'
CLR_DEBUG   = '\033[38;5;14m'
FMT_UNDER   = '\033[4m'

def output_indented_lines(text: str):
    """Prints each line with a 2-space prefix."""
    for line in text.splitlines():
        if line.strip():
            print(f"  {line.rstrip()}\r\n", end="", flush=True)

def modify_yaml_dictionary(data: dict, path_key: str, val: any, is_yaml_fragment: bool = False) -> dict:
    """Updates a nested dictionary value using a dot-notation key."""
    segments = path_key.split('.')
    cursor = data
    for bit in segments[:-1]:
        if bit not in cursor:
            cursor[bit] = {}
        cursor = cursor[bit]
    
    cursor[segments[-1]] = yaml.safe_load(val) if is_yaml_fragment else val
    return data

def transform_yaml_string(raw_yaml: str, path_key: str, val: any, is_yaml_fragment: bool = False) -> str:
    """Parses, modifies, and re-serializes a YAML string."""
    obj = yaml.safe_load(raw_yaml)
    updated = modify_yaml_dictionary(obj, path_key, val, is_yaml_fragment)
    return yaml.dump(updated)

def patch_yaml_file(file_path: str, path_key: str, val: any, is_yaml_fragment: bool = False):
    """Reads a YAML file, applies a modification, and writes it back."""
    with open(file_path, 'r') as f:
        original = f.read()
    updated = transform_yaml_string(original, path_key, val, is_yaml_fragment)
    with open(file_path, 'w') as f:
        f.write(updated)

def verify_regex_match(text: str, pattern: str):
    """Ensures at least one line in the text matches the provided regex."""
    logging.info("Validating output against pattern: %s", pattern)
    for line in text.splitlines():
        if re.match(pattern, line):
            logging.info("Regex hit: %s", line)
            return
    assert False, f"Constraint violation: No line matches '{pattern}'"

def spawn_monitored_process(argv: list, expected_code: int = None, must_have: str = None, must_not_have: str = None):
    """Executes a command, streams output, and validates exit status/content."""
    logging.info("Launching process: %s", argv)
    
    full_output = ""
    if os.name == 'nt':
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate()
        if out:
            chunk = out.decode('utf-8', errors='replace')
            output_indented_lines(chunk)
            full_output += chunk
        if err:
            chunk = err.decode('utf-8', errors='replace')
            output_indented_lines(chunk)
            full_output += chunk
    else:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        watcher = selectors.DefaultSelector()
        watcher.register(proc.stdout, selectors.EVENT_READ)
        watcher.register(proc.stderr, selectors.EVENT_READ)

        print(CLR_WARN, flush=True)
        active = True
        while active:
            for key, _ in watcher.select():
                blob = key.fileobj.read1().decode()
                if not blob:
                    active = False
                else:
                    color_prefix = "" if key.fileobj is proc.stdout else CLR_FAIL
                    output_indented_lines(color_prefix + blob + (CLR_WARN if key.fileobj is proc.stderr else ""))
                    full_output += blob
        print(CLR_DEFAULT, flush=True)
        proc.wait()

    logging.info("Process exited with code: %s", proc.returncode)
    if expected_code is not None:
        assert proc.returncode == expected_code, f"Exit mismatch: Expected {expected_code}, got {proc.returncode}"
    
    if must_have:
        assert re.search(must_have, full_output), f"Output missing required pattern: '{must_have}'"
    if must_not_have:
        assert not re.search(must_not_have, full_output), f"Output contains forbidden pattern: '{must_not_have}'"
        
    return full_output, proc.returncode

def execute_ost_command(args=[], expected_status=0, required_patterns=None, forbidden_patterns=None, quiet=False):
    """Wrapper for running the 'ost' or 'ostd' CLI tools in tests."""
    base_dir = Path(__file__).resolve().parent
    mode_ostd = os.getenv("USE_OSTD", "false").lower() == "true"
    
    cmd_base = []
    if mode_ostd:
        import platform
        os_type = platform.system().lower()
        suffix = ".exe" if os_type == "windows" else ""
        os_dir = "windows" if os_type == "windows" else ("darwin" if os_type == "darwin" else "linux")
        binary = base_dir.parent.parent.parent / "bin" / os_dir / f"ostd{suffix}"
        
        cmd_base = [str(binary), "--nologo"]
        tag_env = os.getenv("OST_IMAGE_TAG")
        if tag_env:
            cmd_base.extend(["--image", "ostrich-sdk", "--tag", tag_env])
            
        for env_k, env_v in os.environ.items():
            if env_k.startswith(("TEST_", "QUOTE_")):
                cmd_base.extend(["-e", f"{env_k}={env_v}"])
    else:
        entry_script = (base_dir.parent.parent / "ost").resolve()
        cmd_base = [sys.executable, str(entry_script), "--nologo"]

    if logging.getLogger().getEffectiveLevel() <= logging.DEBUG and not quiet:
        cmd_base.append("--debug")
        
    cmd_base.extend(args)
    logging.info("Invoking Ostrich CLI: %s", " ".join(cmd_base))
    
    raw_log = ""
    if os.name == 'nt':
        p = subprocess.Popen(cmd_base, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        o, e = p.communicate()
        if o:
            msg = o.decode('utf-8', errors='replace')
            output_indented_lines(msg)
            raw_log += msg.replace("\r", "")
        if e:
            msg = e.decode('utf-8', errors='replace')
            output_indented_lines(msg)
            raw_log += msg.replace("\r", "")
    else:
        p = subprocess.Popen(cmd_base, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        mon = selectors.DefaultSelector()
        mon.register(p.stdout, selectors.EVENT_READ)
        mon.register(p.stderr, selectors.EVENT_READ)
        
        print(CLR_DEBUG, flush=True)
        running = True
        while running:
            for k, _ in mon.select():
                data = k.fileobj.read1().decode()
                if not data: running = False
                else: 
                    output_indented_lines(data)
                    raw_log += data
        print(CLR_DEFAULT, flush=True)

    p.wait()
    if p.returncode != expected_status:
        assert False, f"CLI Error: expected {expected_status}, got {p.returncode}"

    # Pattern validation
    for spec, negate in [(required_patterns, False), (forbidden_patterns, True)]:
        if spec:
            items = spec if isinstance(spec, list) else [spec]
            for pat in items:
                found = bool(re.search(pat, raw_log, re.MULTILINE))
                if negate:
                    assert not found, f"Forbidden pattern '{pat}' found in output"
                else:
                    assert found, f"Required pattern '{pat}' missing from output"

    return raw_log, p.returncode

def digest_helm_output(raw_text: str) -> dict:
    """Parses multi-document YAML from Helm dry-run markers."""
    capture, buf = False, ""
    for line in raw_text.splitlines():
        if "=== TEMPLATE ===" in line: capture = True
        elif "=== END TEMPLATE ===" in line: return parse_yamls_to_map(buf)
        elif capture: buf += line + "\n"
    return {}

def scaffold_test_dir(base_path, yaml_body=None):
    """Sets up a temporary ostrich workspace."""
    cfg = base_path / "ostrich.yaml"
    os.chdir(base_path)
    if yaml_body:
        with open(cfg, "w") as f: f.write(yaml_body)

def switch_to_sample(file_ref, app_name):
    """Jumps to a pre-defined sample application directory."""
    target = os.path.join(resolve_sample_base(file_ref), app_name)
    os.chdir(target)
    logging.info("Workspace shifted to: %s", target)

def write_test_file(path, data):
    with open(path, "w") as f: f.write(data)

def audit_file_content(path, positive=None, negative=None):
    """Verifies the content of a file against positive and negative regex rules."""
    with open(path, "r") as f:
        body = f.read()
        if positive:
            for p in (positive if isinstance(positive, list) else [positive]):
                assert re.search(p, body, re.MULTILINE), f"File {path} lacks expected pattern '{p}'"
        if negative:
            for n in (negative if isinstance(negative, list) else [negative]):
                assert not re.search(n, body, re.MULTILINE), f"File {path} contains forbidden pattern '{n}'"

def stream_file(target_path):
    """Outputs the content of a file to the logger/stdout."""
    with open(target_path, "r", encoding="utf-8") as f:
        msg = f.read()
        print(f"\n--- Reading {target_path} ---\n{CLR_SUCCESS}{msg}{CLR_DEFAULT}\n--- EOF ---\n")

def fetch_doc_sample(caller_file):
    with open(os.path.join(os.path.dirname(caller_file), "../_doc/ostrich.yaml"), "r") as f:
        return f.read()

def resolve_sample_base(caller_file):
    return os.path.normpath(os.path.join(os.path.dirname(caller_file), "..", "_samples"))

def fetch_template_node_config(caller_file):
    with open(os.path.join(os.path.dirname(caller_file), "../config.yaml"), "r") as f:
        return yaml.safe_load(f.read())

def run_helm_render(chart_dir, sub_file="", ns="", overrides=[], val_files=[], extra_flags=[], multi=False, verbose=True):
    """Invokes 'helm template' and retrieves parsed YAML results."""
    args = ["helm", "template"]
    if sub_file: args.extend(["-s", sub_file])
    args.extend(extra_flags)
    
    for o in overrides: args.extend(["--set", o])
    for vf in val_files: args.extend(["-f", vf])
    
    if ns:
        args.extend(["--namespace", ns, "--set", f"global.namespace={ns}"])
    
    args.append(chart_dir)
    raw = ""
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    if os.name == 'nt':
        o, e = proc.communicate()
        if verbose:
            if o: output_indented_lines(o.decode(errors='replace'))
            if e: output_indented_lines(CLR_FAIL + e.decode(errors='replace') + CLR_WARN)
        raw = o.decode(errors='replace')
    else:
        sel = selectors.DefaultSelector()
        sel.register(proc.stdout, selectors.EVENT_READ)
        sel.register(proc.stderr, selectors.EVENT_READ)
        if verbose: print(CLR_WARN, flush=True)
        active = True
        while active:
            for k, _ in sel.select():
                data = k.fileobj.read1().decode()
                if not data: active = False
                else:
                    if verbose: output_indented_lines(CLR_FAIL + data + CLR_WARN if k.fileobj is proc.stderr else data)
                    if k.fileobj is proc.stdout: raw += data
        if verbose: print(CLR_DEFAULT, flush=True)
        proc.wait()

    assert proc.returncode == 0, "Helm rendering failed"
    docs = list(yaml.safe_load_all(raw))
    return docs if multi else docs[0]

def validate_jsonpath(blob: dict, query: str, goal: str, use_regex: bool = False):
    """Checks a specific node in a dictionary using JSONPath."""
    matches = [m.value for m in parse(query).find(blob)]
    assert matches, f"No matches for JSONPath '{query}'"
    
    found = False
    for m in matches:
        if use_regex:
            if re.match(goal, str(m)): (found := True); break
        else:
            if str(m) == goal: (found := True); break
    
    assert found, f"Match failed for '{query}'. Wanted '{goal}', got {matches}"

def parse_yamls_to_map(content: str) -> dict:
    """Parses multi-doc YAML into a name-indexed/kind-indexed lookup table."""
    lookup = {}
    for i, doc in enumerate(yaml.safe_load_all(content)):
        if doc and doc.get('metadata', {}).get('name'):
            n, k = doc['metadata']['name'], doc.get('kind', 'Unknown')
            lookup[n] = doc
            lookup[f"{k}/{n}"] = doc
    return lookup

def fetch_env_checked(key, fallback=None):
    res = os.getenv(key)
    if res is None and fallback is None:
        assert False, f"Missing required env var: {key}"
    return res if res is not None else fallback

def perform_http_get(uri, status=None, verbose=False, max_retries=0):
    """Executes a GET request with optional verification and retries."""
    for attempt in range(max_retries + 1):
        resp = requests.get(uri, verify=False)
        if verbose:
            logging.info("GET %s -> %d\n%s", uri, resp.status_code, resp.text)
        
        if status is None or resp.status_code == status:
            return resp
        if attempt < max_retries:
            time.sleep(1)
    
    assert False, f"HTTP Error: Expected {status}, got {resp.status_code} after retries"

def wipe_kubernetes_namespace(name):
    """Triggers and waits for k8s namespace deletion."""
    config.load_kube_config()
    api = client.CoreV1Api()
    try:
        api.delete_namespace(name)
        logging.info("Namespace '%s' removal initiated", name)
    except Exception as e:
        logging.error("Namespace cleanup failed: %s", e)

    logging.info("Polling for deletion of '%s'...", name)
    while True:
        try:
            api.read_namespace(name)
            print(".", end="", flush=True)
            time.sleep(2)
        except client.exceptions.ApiException as e:
            if e.status == 404:
                print(" Done.")
                break
            raise

def retrieve_k8s_secret(namespace, name):
    config.load_kube_config()
    return client.CoreV1Api().read_namespaced_secret(name, namespace)

# Backwards compatibility layer
getSDKPath = resolve_sdk_resource_path
printIndent = output_indented_lines
display = lambda: print("SDK Helper Active")
updateYamlDict = modify_yaml_dictionary
updateYaml = transform_yaml_string
updateYamlFile = patch_yaml_file
checkContentRegex = verify_regex_match
run = spawn_monitored_process
ost = execute_ost_command
extractHelmTemplateFromDryRun = digest_helm_output
createEnv = scaffold_test_dir
sampleEnv = switch_to_sample
createFile = write_test_file
checkFileContent = audit_file_content
cat = stream_file
catFilePath = lambda p: stream_file(str(p))
getSampleConfig = fetch_doc_sample
getSampleAppPath = resolve_sample_base
getTemplateConfig = fetch_template_node_config
helmTemplate = run_helm_render
checkEntry = validate_jsonpath
getEntry = lambda b, q: (parse(q).find(b)[0].value if parse(q).find(b) else None)
getEntries = lambda b, q: [m.value for m in parse(q).find(b)]
loadJson = lambda p: json.load(open(p))
loadYaml = lambda p: yaml.safe_load(open(p))
parseYaml = yaml.safe_load
parseYamlMultiDoc = parse_yamls_to_map
getenv = fetch_env_checked
httpGet = perform_http_get
deleteNs = wipe_kubernetes_namespace
getSecret = retrieve_k8s_secret
