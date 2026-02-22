import logging
import os
import yaml
import json
import requests
import re
import urllib3
import base64
from urllib.parse import urlparse
from packaging import version

import src.util as util
from src.util import Params
from src.ostrichException import OstrichException

# Ignore security warnings for self-hosted registries with local CA issues
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CORE_REGISTRY = {'name': 'ostrich', 'url': 'ghcr.io/rockops/osplate'}

def get_config_registries():
    """Retrieves the list of configured OCI registries."""
    cfg_path = os.path.expanduser("~") + "/.ostrich/config/config.yaml"
    settings = util.read_yaml_safe(cfg_path)
    defined = settings.get('registries', [])
    
    # Ensure core registry is always present unless specifically overridden
    if any(r.get('name') == 'ostrich' for r in defined):
        return defined
            
    return [CORE_REGISTRY] + defined


def render_registry_usage():
    print("""OCI Registry Management:
  ost registry <command> [args]

Actions:
  - login <name>           : Authenticate session with <name>
  - logout <name>          : Terminate session with <name>
  - add [-f] <name> <url>  : Register a new OCI source. -f to overwrite.
  - list | ls              : Enumerate current registries
  - rm <name>              : Unregister <name> from Ostrich
""")


def extract_credential(host):
    """Attempts to find Helm-stored credentials for a given host."""
    store = os.path.expanduser("~") + "/.ostrich/helm/config/registry/config.json"
    if not os.path.exists(store):
        return None
    try:
        with open(store, "r") as f:
            secret_data = json.load(f)
        return secret_data.get("auths", {}).get(host, {}).get("auth")
    except Exception:
        return None


def dispatch_oci_call(url, token_b64):
    """Performs an authenticated OCI registry request with bearer token discovery."""
    comm_headers = {"Authorization": f"Basic {token_b64}"} if token_b64 else {}
    
    def internal_call(target, h, verify=True):
        try:
            return requests.get(target, headers=h, timeout=12, verify=verify)
        except Exception:
            return requests.get(target, headers=h, timeout=12, verify=False)

    resp = internal_call(url, comm_headers)

    # Handle Bearer authentication challenge
    if resp.status_code == 401:
        auth_header = resp.headers.get("Www-Authenticate", "")
        if "Bearer" in auth_header:
            realm_match = re.search(r'Bearer realm="([^"]+)"', auth_header)
            svc_match = re.search(r'service="([^"]+)"', auth_header)
            if realm_match and svc_match:
                token_url = realm_match.group(1)
                query = {"service": svc_match.group(1)}
                scope_match = re.search(r'scope="([^"]+)"', auth_header)
                if scope_match: query["scope"] = scope_match.group(1)
                
                auth_resp = internal_call(token_url + "?" + "&".join([f"{k}={v}" for k, v in query.items()]), comm_headers)
                
                if auth_resp.status_code == 200:
                    payload = auth_resp.json()
                    access_key = payload.get("token") or payload.get("access_token")
                    if access_key:
                        return internal_call(url, {"Authorization": f"Bearer {access_key}"})
                    
    return resp


def manage_registries(ctx: Params):
    """CLI handler for registry operations."""
    ctx.parse_cli_arguments()
    args = ctx.operationParams
    if not args:
        render_registry_usage()
        return

    db_path = os.path.expanduser("~") + "/.ostrich/config/config.yaml"
    mode = args[0]

    if mode == "login":
        if len(args) < 2:
            render_registry_usage()
            raise OstrichException("Missing registry name")
        
        target = args[1]
        active_list = get_config_registries()
        endpoint = next((r['url'] for r in active_list if r['name'] == target), None)
        
        if not endpoint:
            logging.error("Registry '%s' undefined.", target)
            raise OstrichException(f"Unknown registry identifier: {target}")

        logging.info("Initiating authentication for %s (%s)", target, endpoint)
        
        # Isolate hostname
        raw_uri = endpoint
        if "://" in raw_uri:
            p = urlparse(raw_uri)
            raw_uri = f"{p.scheme}://{p.hostname}"
        else:
            raw_uri = raw_uri.split("/", 1)[0]

        h_flags = ["registry", "login", raw_uri]
        if ctx.skipTlsVerify: h_flags.append("--insecure")
        util.execute_helm_command(*h_flags)

    elif mode == "logout":
        if len(args) < 2:
            render_registry_usage()
            raise OstrichException("Missing registry name")
            
        target = args[1]
        active_list = get_config_registries()
        endpoint = next((r['url'] for r in active_list if r['name'] == target), None)
        
        if not endpoint:
            raise OstrichException(f"Registry '{target}' not in configuration")

        logging.info("Terminating session with %s", target)
        raw_host = endpoint.split("://")[-1].split("/")[0] if "://" in endpoint else endpoint.split("/")[0]
        
        h_flags = ["registry", "logout", raw_host]
        if ctx.skipTlsVerify: h_flags.append("--insecure")
        util.execute_helm_command(*h_flags)

    elif mode == "add":
        payload = args[1:]
        overwrite = ctx.forceTmpDir
        
        # Manual flag detection
        processed_args = []
        for a in payload:
            if a in ["-f", "--force"]: overwrite = True
            else: processed_args.append(a)

        if len(processed_args) < 2:
            render_registry_usage()
            raise OstrichException("Usage: add <name> <url>")
            
        new_tag, new_url = processed_args[0], processed_args[1]
        
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        current_cfg = util.read_yaml_safe(db_path)
        if 'registries' not in current_cfg: current_cfg['registries'] = []
            
        if overwrite:
            current_cfg['registries'] = [r for r in current_cfg['registries'] if r.get('name') != new_tag]
        elif any(r.get('name') == new_tag for r in current_cfg['registries']):
            raise OstrichException(f"Conflict: Registry '{new_tag}' already exists. Use -f to force update.")

        current_cfg['registries'].append({'name': new_tag, 'url': new_url})
        with open(db_path, 'w') as f:
            yaml.dump(current_cfg, f)
        logging.info("Successfully registered '%s' [%s]", new_tag, new_url)

    elif mode in ["list", "ls"]:
        all_reg = get_config_registries()
        if not all_reg:
            logging.info("No OCI sources currently defined")
            return
        logging.info("Configured OCI Sources:")
        for r in all_reg:
            print(f" -> {r.get('name')} : {r.get('url')}")

    elif mode == "rm":
        if len(args) < 2:
            render_registry_usage()
            raise OstrichException("Missing registry identifier")
        target = args[1]
        if target == 'ostrich':
            raise OstrichException("Removal of the default 'ostrich' registry is prohibited.")

        current_cfg = util.read_yaml_safe(db_path)
        filtered = [r for r in current_cfg.get('registries', []) if r.get('name') != target]
        
        if len(filtered) == len(current_cfg.get('registries', [])):
            raise OstrichException(f"Identifier '{target}' not located")

        current_cfg['registries'] = filtered
        with open(db_path, 'w') as f:
            yaml.dump(current_cfg, f)
        logging.info("Unregistered source '%s'", target)
    else:
        render_registry_usage()
        raise OstrichException(f"Unmapped registry action: {mode}")


def perform_template_discovery(ctx: Params):
    """Searches through OCI registries for available templates."""
    search_params = ctx.operationParams[1:]
    
    detailed_listing = False
    if "--versions" in search_params:
        detailed_listing = True
        search_params.remove("--versions")

    all_sources = get_config_registries()
    permitted_names = [r.get('name') for r in all_sources]

    limit_source = None
    term = ""

    if len(search_params) >= 2:
        limit_source, term = search_params[0], search_params[1]
    elif len(search_params) == 1:
        if search_params[0] in permitted_names:
            limit_source = search_params[0]
        else:
            term = search_params[0]
    
    hits = 0
    for src in all_sources:
        if limit_source and src.get('name') != limit_source:
            continue

        raw_loc = src.get('url')
        if "://" not in raw_loc: raw_loc = "https://" + raw_loc
        
        parsed_uri = urlparse(raw_loc)
        host = parsed_uri.hostname
        credential = extract_credential(host)
        prefix_path = parsed_uri.path.strip("/")
        
        discovered_repos = []

        # Provider Strategy 1: GitHub API Integration
        if any(g in host for g in ["ghcr.io", "github.com"]):
            segments = prefix_path.split("/")
            if segments and segments[0]:
                org = segments[0]
                filter_key = "/".join(segments[1:])
                
                for scope in ["orgs", "users"]:
                    api_endpoint = f"https://api.github.com/{scope}/{org}/packages?package_type=container"
                    auth_headers = {"Accept": "application/vnd.github+json"}
                    if credential:
                        try:
                            readable = base64.b64decode(credential).decode('utf-8')
                            if ":" in readable:
                                auth_headers["Authorization"] = f"token {readable.split(':', 1)[1]}"
                        except Exception: pass
                    
                    try:
                        gh_resp = requests.get(api_endpoint, headers=auth_headers, timeout=12)
                        if gh_resp.status_code == 200:
                            for item in gh_resp.json():
                                name = item.get("name")
                                full_id = f"{org}/{name}"
                                if (not filter_key or name.startswith(filter_key)) and (not term or term in full_id):
                                    discovered_repos.append(full_id)
                            break
                        elif gh_resp.status_code in [401, 403]:
                            status = "unauthenticated" if not credential else "denied"
                            logging.warning("GitHub access %s for %s", status, src['name'])
                            break
                    except Exception: pass

        # Provider Strategy 2: Harbor-compatible Search API
        if not discovered_repos:
            search_api = f"{parsed_uri.scheme}://{host}/api/v2.0/search?q={term}" if term else f"{parsed_uri.scheme}://{host}/api/v2.0/repositories"
            h_resp = dispatch_oci_call(search_api, credential)
            if h_resp.status_code == 200:
                raw_data = h_resp.json()
                results = raw_data.get("repository") if isinstance(raw_data, dict) else raw_data
                if results:
                    for obj in results:
                        discovered_repos.append(obj.get("repository_name") or obj.get("name"))

        # Provider Strategy 3: Standard OCI Catalog Discovery
        if not discovered_repos:
            cat_url = f"{parsed_uri.scheme}://{host}/v2/_catalog"
            c_resp = dispatch_oci_call(cat_url, credential)
            if c_resp.status_code == 200:
                for entry in c_resp.json().get("repositories", []):
                    if not term or term in entry:
                        discovered_repos.append(entry)

        # Output formatting and version discovery
        for repo in sorted(list(set(discovered_repos))):
            rel_name = None
            if prefix_path:
                if repo == prefix_path: rel_name = ""
                elif repo.startswith(prefix_path + "/"):
                    rel_name = repo[len(prefix_path):].lstrip("/")
                elif repo == f"{host}/{prefix_path}": rel_name = ""
                elif repo.startswith(f"{host}/{prefix_path}/"):
                    rel_name = repo[len(f"{host}/{prefix_path}"):].lstrip("/")
                
                if rel_name is None: continue
            else:
                rel_name = repo

            qualified_label = f"{src['name']}/{rel_name}" if rel_name else src['name']

            # Tag enumeration
            tag_svc = f"{parsed_uri.scheme}://{host}/v2/{repo}/tags/list"
            t_resp = dispatch_oci_call(tag_svc, credential)
            if t_resp.status_code == 200:
                tag_list = t_resp.json().get("tags", [])
                if tag_list:
                    if detailed_listing:
                        for tag in tag_list:
                            print(f" * {qualified_label}:{tag}")
                            hits += 1
                    else:
                        try:
                            valid = [t for t in tag_list if t]
                            if valid:
                                top = sorted(valid, key=version.parse)[-1]
                                print(f" * {qualified_label}:{top}")
                                hits += 1
                        except Exception:
                            print(f" * {qualified_label}:{sorted(tag_list)[-1]}")
                            hits += 1
                else:
                    print(f" * {qualified_label}")
                    hits += 1
            else:
                print(f" * {qualified_label}")
                hits += 1
    
    if hits == 0:
        logging.info("No matching template resources identified in registries.")

# Compatibility aliases
registry = manage_registries
search = perform_template_discovery
