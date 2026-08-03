import logging
import os
import sys
from typing import Any
import yaml
import src.util as util

parsedConfig: Any=None

def loadConf():
    global parsedConfig

    # Load relative to this module's file location (src/conf.py -> config.yaml is in parent)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config.yaml")
    if not os.path.exists(config_path):
        config_path = os.path.join(util.root(), "config.yaml")
    with open(config_path, "r") as f:
        parsedConfig = yaml.safe_load(f)



# Gets the conf key :
# Check in the plugin configuration,
# Else reads in the global config file
# Else Check it an env var exist, replacing . by _ prefixed by ost 
# Finaly, returns the default value
def getConf(key,params: util.Params,defval=None):

    ret=params.getPluginConf(key,"__NOTFOUND__")

    if(ret != "__NOTFOUND__"):
        logging.debug("%s=%s [got from plugin conf]",key,ret)
        return ret
    else:
        try:
            ret=parsedConfig
            for k in key.split("."):
                ret=ret[k]
            logging.debug("%s=%s [got from global config file]",key,ret)
            return ret

        except Exception:
            envvar="os_"+key.replace('.','_')
            ret = os.environ.get(envvar)
            if ret!=None:
                logging.debug("%s=%s [got from ENV %s]",key,ret,envvar)
                return ret
            else:
                logging.debug("%s=%s [default value]",key,defval)
                return defval
