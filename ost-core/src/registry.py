import logging
import os
import yaml
import json
import requests
import re
import urllib3
from urllib.parse import urlparse
from packaging import version
import base64
import src.util as util
from src.util import Params
from src.ostrichException import OstrichException

# Suppress InsecureRequestWarning as we often deal with internal/self-signed registries
# that might be trusted at the system level but not by the requests' default CA bundle.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_REGISTRY = {'name': 'ostrich', 'url': 'ghcr.io/rockops/osplate'}

def load_registries():
    config_file = os.path.expanduser("~") + "/.ostrich/config/config.yaml"
    config = util.safeLoad(config_file)
    registries = config.get('registries', [])
    
    # Check if ostrich is already there (manually added or overridden)
    for reg in registries:
        if reg.get('name') == 'ostrich':
            return registries
            
    # If not, add the default one at the beginning
    return [DEFAULT_REGISTRY] + registries

def registryUsage():
    print("""Usage: ost registry <command> [parameters]
Available commands:
  - login <name> : login to an OCI registry
  - logout <name> : logout from an OCI registry
  - add [-f] <name> <url> : add a registry to the configuration. Use -f to override.
  - list : list all configured registries
  - rm <name> : remove a registry from the configuration
  - trust <name> : skip TLS verification for a specific registry
""")

def get_oci_auth(hostname):
    config_path = os.path.expanduser("~") + "/.ostrich/helm/config/registry/config.json"
    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path, "r") as f:
            auth_config = json.load(f)
        return auth_config.get("auths", {}).get(hostname, {}).get("auth")
    except Exception:
        return None

def oci_request(url, auth_base64, skip_tls_verify=False):
    headers = {}
    if auth_base64:
        headers["Authorization"] = f"Basic {auth_base64}"
    
    def perform_get(target_url, target_headers=None, target_params=None):
        try:
            return requests.get(target_url, headers=target_headers, params=target_params, timeout=10, verify=not skip_tls_verify)
        except requests.exceptions.SSLError as ssl_err:
            if not skip_tls_verify:
                logging.error(f"TLS certificate verification failed for {target_url}\nskip certificate validation using --skip-tls-verify")
                raise SystemExit(1)
            else:
                return requests.get(target_url, headers=target_headers, params=target_params, timeout=10, verify=False)
        except requests.exceptions.ConnectionError as conn_err:
            err_str = str(conn_err).lower()
            if "ssl" in err_str or "certificate" in err_str or "certify" in err_str:
                if not skip_tls_verify:
                    logging.error(f"TLS certificate verification failed for {target_url}\nskip certificate validation using --skip-tls-verify")
                    raise SystemExit(1)
            raise

    response = perform_get(url, headers)

    if response.status_code == 401:
        challenge = response.headers.get("Www-Authenticate", "")
        if "Bearer" in challenge:
            match = re.search(r'Bearer realm="([^"]+)",service="([^"]+)"', challenge)
            if match:
                realm = match.group(1)
                service = match.group(2)
                scope = re.search(r'scope="([^"]+)"', challenge)
                params = {"service": service}
                if scope:
                    params["scope"] = scope.group(1)
                
                token_headers = {"Authorization": f"Basic {auth_base64}"} if auth_base64 else {}
                token_resp = perform_get(realm, token_headers, params)
                
                if token_resp.status_code == 200:
                    token = token_resp.json().get("token") or token_resp.json().get("access_token")
                    if token:
                        headers = {"Authorization": f"Bearer {token}"}
                        response = perform_get(url, headers)
                    
    return response

def registry(params: Params):
    params.collectStandardArgs()
    if len(params.operationParams) == 0:
        registryUsage()
        return

    config_file = os.path.expanduser("~") + "/.ostrich/config/config.yaml"

    sub_op = params.operationParams[0]
    if sub_op == "login":
        if len(params.operationParams) < 2:
            registryUsage()
            raise OstrichException("Invalid number of parameters")
        name = params.operationParams[1]
        
        registries = load_registries()

        
        url = None
        target_reg = None
        for reg in registries:
            if reg.get('name') == name:
                url = reg.get('url')
                target_reg = reg
                break
        
        if url is None:
            logging.error(f"Registry '{name}' not found in configuration.")
            logging.info("To add a registry, use: ost registry add <name> <url>")
            raise OstrichException(f"Registry '{name}' not found")

        logging.info(f"Logging in to registry: {name} ({url})")
        
        # Extract the registry part (e.g., docker.io/repo -> docker.io)
        registry_url = url
        if "://" in registry_url:
            scheme_part, rest = registry_url.split("://", 1)
            registry_host = rest.split("/", 1)[0]
            registry_url = f"{scheme_part}://{registry_host}"
        else:
            registry_url = registry_url.split("/", 1)[0]

        helm_args = ["registry", "login", registry_url]
        skip_verify = params.skipTlsVerify or (target_reg and target_reg.get('insecure', False))
        if skip_verify:
            helm_args.append("--insecure")
        util.helm(*helm_args)
    elif sub_op == "logout":
        if len(params.operationParams) < 2:
            registryUsage()
            raise OstrichException("Invalid number of parameters")
        name = params.operationParams[1]
        
        registries = load_registries()

        
        url = None
        target_reg = None
        for reg in registries:
            if reg.get('name') == name:
                url = reg.get('url')
                target_reg = reg
                break
        
        if url is None:
            logging.error(f"Registry '{name}' not found in configuration.")
            raise OstrichException(f"Registry '{name}' not found")

        logging.info(f"Logging out from registry: {name} ({url})")
        
        registry_url = url
        if "://" in registry_url:
            scheme_part, rest = registry_url.split("://", 1)
            registry_host = rest.split("/", 1)[0]
            registry_url = f"{scheme_part}://{registry_host}"
        else:
            registry_url = registry_url.split("/", 1)[0]

        helm_args = ["registry", "logout", registry_url]
        skip_verify = params.skipTlsVerify or (target_reg and target_reg.get('insecure', False))
        if skip_verify:
            helm_args.append("--insecure")
        util.helm(*helm_args)
    elif sub_op == "add":
        args = params.operationParams[1:]
        force = params.forceTmpDir
        
        if "-f" in args:
            force = True
            args.remove("-f")
        if "--force" in args:
            force = True
            args.remove("--force")

        if len(args) < 2:
            registryUsage()
            raise OstrichException("Invalid number of parameters")
            
        name = args[0]
        url = args[1]
        
        config_dir = os.path.dirname(config_file)
        os.makedirs(config_dir, exist_ok=True)
        
        config = util.safeLoad(config_file)
        if 'registries' not in config:
            config['registries'] = []
            
        # Check if registry already exists
        if force:
            config['registries'] = [r for r in config['registries'] if r.get('name') != name]
        else:
            for reg in config['registries']:
                if reg.get('name') == name:
                    raise OstrichException(f"Registry {name} already exists. Use \"ost registry add -f\" to force update")

        config['registries'].append({'name': name, 'url': url})
        
        util.safeWriteYaml(config_file, config)
            
        logging.info(f"Registry {name} ({url}) added to configuration")
    elif sub_op in ["list", "ls"]:
        registries = load_registries()
        
        if not registries:
            logging.info("No registries configured")
            return
            
        logging.info("Configured registries:")
        for reg in registries:
            insecure_str = " [insecure]" if reg.get('insecure') else ""
            print(f"- {reg.get('name')}: {reg.get('url')}{insecure_str}")
    elif sub_op == "rm":
        if len(params.operationParams) < 2:
            registryUsage()
            raise OstrichException("Invalid number of parameters")
        name = params.operationParams[1]
        
        if name == 'ostrich':
            raise OstrichException("The 'ostrich' registry is the official Ostrich registry and cannot be removed.")

        config = util.safeLoad(config_file)
        registries = config.get('registries', [])
        
        new_registries = [r for r in registries if r.get('name') != name]
        
        if len(new_registries) == len(registries):
            raise OstrichException(f"Registry {name} not found")

        config['registries'] = new_registries
        util.safeWriteYaml(config_file, config)
            
        logging.info(f"Registry {name} removed from configuration")
    elif sub_op == "trust":
        if len(params.operationParams) < 2:
            registryUsage()
            raise OstrichException("Invalid number of parameters")
        name = params.operationParams[1]
        
        config = util.safeLoad(config_file)
        registries = config.get('registries', [])
        
        found = False
        for reg in registries:
            if reg.get('name') == name:
                reg['insecure'] = True
                found = True
                break
                
        if not found:
            raise OstrichException(f"Registry {name} not found in configuration")
            
        config['registries'] = registries
        util.safeWriteYaml(config_file, config)
        logging.info(f"Registry {name} is now marked as trusted (skipping TLS verification)")
    else:
        registryUsage()
        raise OstrichException(f"Unknown registry sub-command: {sub_op}")

def search(params: Params):
    config_file = os.path.expanduser("~") + "/.ostrich/config/config.yaml"
    # Skip the "search" operation parameter if called from template.py
    # If called from "ost template search", params.operationParams[0] is "search"
    args = params.operationParams[1:]
    if len(args) == 0:
        # We allow empty search to list everything if no query is provided
        # Wait, the user might want "ost template search" to list everything?
        # Actually in the previous implementation it raised an error if no query.
        # But if we list everything from registries it might be noisy.
        # Let's keep the logic but maybe allow empty query if registry filter is present.
        pass

    show_all_versions = False
    if "--versions" in args:
        show_all_versions = True
        args.remove("--versions")

    registries = load_registries()
    registry_names = [r.get('name') for r in registries]

    registry_filter = None
    query = ""

    if len(args) >= 2:
        registry_filter = args[0]
        query = args[1]
    elif len(args) == 1:
        if args[0] in registry_names:
            registry_filter = args[0]
            query = ""
        else:
            query = args[0]
    
    found = False
    for reg in registries:
        if registry_filter and reg.get('name') != registry_filter:
            continue

        skip_verify = params.skipTlsVerify or reg.get('insecure', False)

        url_str = reg.get('url')
        if "://" not in url_str:
            url_str = "https://" + url_str
        
        parsed = urlparse(url_str)
        hostname = parsed.hostname
        auth = get_oci_auth(hostname)
        path = parsed.path.strip("/")
        
        repo_names = []
        discovery_done = False

        # 1. Try GitHub API
        if "ghcr.io" in hostname or "github.com" in hostname:
            path_parts = path.split("/")
            if path_parts and path_parts[0]:
                owner = path_parts[0]
                prefix = "/".join(path_parts[1:])
                
                for api_type in ["orgs", "users"]:
                    gh_url = f"https://api.github.com/{api_type}/{owner}/packages?package_type=container"
                    headers = {"Accept": "application/vnd.github+json"}
                    if auth:
                        try:
                            decoded = base64.b64decode(auth).decode('utf-8')
                            if ":" in decoded:
                                _, token = decoded.split(":", 1)
                                headers["Authorization"] = f"token {token}"
                        except Exception:
                            pass
                    
                    try:
                        resp = requests.get(gh_url, headers=headers, timeout=10, verify=not skip_verify)
                        if resp.status_code == 200:
                            gh_packages = resp.json()
                            for pkg in gh_packages:
                                pkg_name = pkg.get("name")
                                # Full repo name in OCI: owner/pkg_name
                                full_repo_name = f"{owner}/{pkg_name}"
                                
                                if prefix and not pkg_name.startswith(prefix):
                                    continue
                                
                                if not query or query in full_repo_name:
                                    repo_names.append(full_repo_name)
                            discovery_done = True
                            break
                        elif resp.status_code in [401, 403]:
                            if not auth:
                                logging.warning(f"GitHub registry '{reg['name']}' requires authentication to list packages.")
                                logging.info(f"Please login using: ost registry login {reg['name']}")
                            else:
                                logging.warning(f"Authentication failed for GitHub registry '{reg['name']}'. Your token might be expired or lack 'read:packages' scope.")
                                logging.info(f"You can try logging in again: ost registry login {reg['name']}")
                            # We stop searching for this registry if we hit an auth error on the owner
                            discovery_done = True
                            break
                    except Exception as e:
                        logging.debug(f"GitHub API error for {gh_url}: {e}")

        # 2. Try Harbor API
        if not discovery_done:
            harbor_url = None
            if query:
                harbor_url = f"{parsed.scheme}://{hostname}/api/v2.0/search?q={query}"
            else:
                harbor_url = f"{parsed.scheme}://{hostname}/api/v2.0/repositories"
            
            resp = oci_request(harbor_url, auth, skip_verify)
            if resp.status_code == 200:
                data = resp.json()
                repos = data.get("repository") if isinstance(data, dict) else data
                if repos:
                    for r in repos:
                        repo_names.append(r.get("repository_name") or r.get("name"))
                    discovery_done = True
            elif resp.status_code in [401, 403]:
                if not auth:
                    logging.warning(f"Registry '{reg['name']}' requires authentication to search.")
                    logging.info(f"Please login using: ost registry login {reg['name']}")
                else:
                    logging.warning(f"Authentication failed for registry '{reg['name']}'.")
                    logging.info(f"Please check your credentials or login again: ost registry login {reg['name']}")
                discovery_done = True

        # 3. Try standard OCI _catalog
        if not discovery_done:
            catalog_url = f"{parsed.scheme}://{hostname}/v2/_catalog"
            resp = oci_request(catalog_url, auth, skip_verify)
            if resp.status_code == 200:
                candidates = resp.json().get("repositories", [])
                for r in candidates:
                    if not query or query in r:
                        repo_names.append(r)
                discovery_done = True
            elif resp.status_code in [401, 403]:
                if not auth:
                    logging.warning(f"Registry '{reg['name']}' requires authentication to list catalog.")
                    logging.info(f"Please login using: ost registry login {reg['name']}")
                else:
                    logging.warning(f"Catalog access denied for registry '{reg['name']}'. It might be required to login or the feature might be disabled.")
                    logging.info(f"You can try logging in: ost registry login {reg['name']}")
                discovery_done = True

        # Process found repositories
        for repo_name in sorted(list(set(repo_names))):
            # If a path is configured for the registry, the repository must be within that path
            display_name = None
            if path:
                if repo_name == path:
                    display_name = ""
                elif repo_name.startswith(path + "/"):
                    display_name = repo_name[len(path):].lstrip("/")
                elif repo_name == f"{hostname}/{path}":
                    display_name = ""
                elif repo_name.startswith(f"{hostname}/{path}/"):
                    display_name = repo_name[len(f"{hostname}/{path}"):].lstrip("/")
                
                if display_name is None:
                    # Skip repositories outside the configured path
                    continue
            else:
                display_name = repo_name

            full_display_name = f"{reg['name']}/{display_name}" if display_name else reg['name']

            tags_url = f"{parsed.scheme}://{hostname}/v2/{repo_name}/tags/list"
            tags_resp = oci_request(tags_url, auth, skip_verify)
            if tags_resp.status_code == 200:
                tags = tags_resp.json().get("tags", [])
                if tags:
                    if show_all_versions:
                        for t in tags:
                            print(f"- {full_display_name}:{t}")
                            found = True
                    else:
                        try:
                            valid_tags = [t for t in tags if t]
                            if valid_tags:
                                latest = sorted(valid_tags, key=version.parse)[-1]
                                print(f"- {full_display_name}:{latest}")
                                found = True
                        except Exception:
                            latest = sorted(tags)[-1]
                            print(f"- {full_display_name}:{latest}")
                            found = True
                else:
                    print(f"- {full_display_name}")
                    found = True
            else:
                print(f"- {full_display_name}")
                found = True
    
    if not found:
        logging.info("No matching packages found")
