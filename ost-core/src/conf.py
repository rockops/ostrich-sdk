import logging
import os
import sys
from typing import Any
import yaml
import src.util as util

# Internal cache for global settings
global_settings_cache: Any = None

def initialize_global_settings():
    """Reads the static global configuration file from the application's root."""
    global global_settings_cache
    target = os.path.join(os.path.dirname(sys.argv[0]), "config.yaml")
    with open(target, "r") as f:
        global_settings_cache = yaml.safe_load(f)

def resolve_setting_value(key, params: util.Params, fallback=None):
    """
    Resolution hierarchy for settings:
    1. Plugin-specific configuration (via params)
    2. Global configuration file
    3. Environment variables (prefix 'os_', dot replaced by underscore)
    4. Provided default value
    """
    
    # Priority 1: Plugin Context
    val = params.fetch_plugin_setting(key, "__MISSING__")
    if val != "__MISSING__":
        logging.debug("Param '%s' -> %s [Plugin Scope]", key, val)
        return val
        
    # Priority 2: Global Configuration Cache
    try:
        cursor = global_settings_cache
        for segment in key.split("."):
            cursor = cursor[segment]
        logging.debug("Param '%s' -> %s [Global Scope]", key, cursor)
        return cursor
    except Exception:
        pass

    # Priority 3: Environmental Override
    env_key = "os_" + key.replace('.', '_')
    env_val = os.environ.get(env_key)
    if env_val is not None:
        logging.debug("Param '%s' -> %s [Env: %s]", key, env_val, env_key)
        return env_val

    # Priority 4: Default Fallback
    logging.debug("Param '%s' -> %s [Fallback]", key, fallback)
    return fallback

# Compatibility aliases
loadConf = initialize_global_settings
getConf = resolve_setting_value
parsedConfig = global_settings_cache
