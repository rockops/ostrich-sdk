from inspect import currentframe, stack
import logging
import os
import shutil
import string
import sys
from typing import Any
from semver import Version
import yaml
import hashlib
from jinja2 import Environment, FileSystemLoader, Template
from src.ostrichException import OstrichException
from subprocess import run
import subprocess
from pathlib import Path
import jsonschema
from envsubst import envsubst
from glom import glom
import copy

class SafeStreamHandler(logging.StreamHandler):
    """
    A custom logging handler that suppresses [WinError 6] on Windows, 
    which occur when writing to closed handles (often during pytest execution).
    """
    def emit(self, record):
        try:
            super().emit(record)
        except OSError as e:
            # On Windows, [WinError 6] "The handle is invalid" happens when
            # pytest captures stdout/stderr. We suppress this specific error.
            if os.name == 'nt' and getattr(e, 'winerror', 0) == 6:
                pass
            else:
                raise

# Location of the config file
location=""
configAll: Any = []
jinja: Template
e: Environment

class Params:
    usage=False
    debug=False
    dryRun=False
    rmTmpDir=False
    noDeps=False
    skip=[]
    executedTasks=[]
    userOutput=False
    pluginFile="ostrich.yaml"
    kubeConfig: string=None
    operation=""
    operationParams=[]
    registry: string=None
    tmpdir: string=None
    pluginTmpDir: string=None
    loglevel=logging.INFO
    forceTmpDir=False
    deletePluginTmpDir=True
    nologo=False
    skipTlsVerify=False
    
    parsedPluginConfig: Any

    def loadPluginConf(self):
        try:
            logging.debug("Loading %s",self.pluginFile)
            
            content = None
            # Try different encodings: utf-8-sig handles BOM, utf-16 for PowerShell 5.1 redirection
            for encoding in ['utf-8-sig', 'utf-16']:
                try:
                    with open(self.pluginFile, 'r', encoding=encoding) as f:
                        content = f.read()
                        break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            
            if content is None:
                # Fallback to default encoding
                with open(self.pluginFile, 'r') as f:
                    content = f.read()

            # Templating with Jinja
            env_data = os.environ.copy()
            env_yaml_path = os.path.join(getConfigRoot(), "env.yaml")
            if os.path.exists(env_yaml_path):
                try:
                    with open(env_yaml_path, 'r') as f:
                        env_config = yaml.safe_load(f)
                        if env_config:
                            env_data.update(env_config)
                except Exception as e:
                    logging.warning("Error loading env.yaml: %s", e)

            jinja_env = Environment(
                variable_start_string='[[',
                variable_end_string=']]',
            )
            try:
                content = jinja_env.from_string(content).render(env=env_data)
            except Exception as e:
                raise OstrichException(f"Error templating {self.pluginFile}: {e}")

            content = envsubst(content)
            logging.debug("Templated config:\n%s", content)
            self.parsedPluginConfig = yaml.safe_load(content)
            
            # Schema validation
            if self.parsedPluginConfig:
                template_kind = self.getPluginConf("template.kind", None)
                if template_kind:
                    try:
                        template_path = getTemplatePath(str(template_kind))
                        schema_path = os.path.join(template_path, "_doc/schema.yaml")
                        if os.path.exists(schema_path):
                            logging.debug("Validating %s against schema %s", self.pluginFile, schema_path)
                            with open(schema_path, 'r') as sf:
                                schema = yaml.safe_load(sf)
                            jsonschema.validate(instance=self.parsedPluginConfig, schema=schema)
                    except OstrichException:
                        # Template path not found, skip validation
                        pass
                    except jsonschema.exceptions.ValidationError as e:
                        path = ".".join([str(p) for p in e.path])
                        if path:
                            raise OstrichException(f"Configuration validation failed for {self.pluginFile} at key \"{path}\":\n{e.message}")
                        else:
                            raise OstrichException(f"Configuration validation failed for {self.pluginFile}:\n{e.message}")

            self.parsedPluginConfig['params']=self
        except yaml.YAMLError as e:
            raise OstrichException(f"Error parsing YAML file {self.pluginFile} {str(e)}")
        except BaseException as e:
            raise OstrichException(f"Error loading file {self.pluginFile} {str(e)}")

    def getPluginConf(self, key: string, defval="_UNDEFINED_"):
        try:
            ret=self.parsedPluginConfig
            for k in key.split("."):
                ret=ret[k]
            return ret
        except BaseException:
            if defval=="_UNDEFINED_":
                logging.fatal("Cannot get plugin param \"%s\" in file %s",key,self.pluginFile)
                raise
            else:
                return defval

    def collectStandardArgs(self):
        new_args = []
        i = 0
        args = self.operationParams
        while i < len(args):
            if args[i] in ['-o', '--output']:
                if i + 1 < len(args):
                    self.tmpdir = args[i+1]
                    self.userOutput = True
                    i += 2
                    continue
                else:
                    raise OstrichException("Missing value for -o/--output option")
            elif args[i] in ['-dr', '--dry-run']:
                self.dryRun = True
                if self.tmpdir is None:
                    self.tmpdir = "dry-run"
                i += 1
                continue
            elif args[i] == '--rm':
                self.rmTmpDir = True
                i += 1
                continue
            elif args[i] in ['-d', '--debug']:
                logging.getLogger().setLevel(logging.DEBUG)
                self.loglevel = logging.DEBUG
                i += 1
                continue
            elif args[i] == '--nologo':
                self.nologo = True
                i += 1
                continue
            elif args[i] == '--force':
                self.forceTmpDir = True
                i += 1
                continue
            elif (args[i] == '-h' or args[i] == '--help' or args[i] == 'help'):
                self.usage=True
                i += 1
                continue
            elif args[i] == '--skip-tls-verify':
                self.skipTlsVerify = True
                i += 1
                continue
            else:
                new_args.append(args[i])
                i += 1
        self.operationParams = new_args

def runcheck(cmd):
    if(run(cmd).returncode!=0):
        raise OstrichException(f"Error executing command {' '.join(cmd)}")

def root():
    return os.path.abspath(os.path.dirname(sys.argv[0]))

def extraTemplateRoot():
    return getConfigRoot()+"/templates"

def templateRoot():
    return root()+"/templates"

def testTemplateRoot():
    return root()+"/test-templates"

def getTemplatePath(tpl: string):
    tpl_str = str(tpl)
    ret=templateRoot()+"/"+tpl_str
    if os.path.isdir(ret) == False:
        ret=testTemplateRoot()+"/"+tpl_str
        if os.path.isdir(ret) == False:
            ret=extraTemplateRoot()+"/"+tpl_str
            if os.path.isdir(ret) == False:
                raise OstrichException(f"Template {tpl_str} does not exist")
    return ret


def setLocation(str):
    global location
    location=str

def getLocation():
    global location
    return location

## Jinja2 filters
def here(str):
    if(not str):
      raise OstrichException(f"'here' fiter called with an undefined or empty input "+getCurrentLocation())  
    
    global location
    if(os.path.isabs(str)):
        return str.replace("\\", "/")
    else:
        return os.path.normpath(os.path.join(location, str)).replace("\\", "/")

def noslash(str):
    if(str == ""):
        return ""
    if(not str):
      raise OstrichException(f"'noslash' fiter called with an empty input "+getCurrentLocation())  
    ret=str
    while(ret.endswith("/") or ret.endswith("\\")):
        ret=ret[:-1]
    return ret
    
def md5hash(str):
    if(not str):
      raise OstrichException(f"'md5hash' fiter called with an undefined or empty input "+getCurrentLocation())  
    return hashlib.md5(str.encode('utf-8')).hexdigest()

def fromTemplate(str):
    if(not str):
      raise OstrichException(f"'fromTemplate' fiter called with an undefined or empty input "+getCurrentLocation())  
    return (configAll['_ostrich']['templateLocation']+"/"+str).replace("\\", "/")

def fromTemplates(str):
    if(not str):
      raise OstrichException(f"'fromTemplates' fiter called with an undefined or empty input "+getCurrentLocation())  
    return (templateRoot()+"/"+str).replace("\\", "/")

def fromTemplateInstance(str):
    global configAll
    return os.path.abspath(configAll['_ostrich']['tmpdir']+"/"+str).replace("\\", "/")

def fromJob(str):
    if(not str):
      raise OstrichException(f"'fromJob' fiter called with an undefined or empty input "+getCurrentLocation())  
    return (configAll['_ostrich']['templateLocation']+"/"+configAll['_ostrich']['operation']+"/"+str).replace("\\", "/")

def nosnapshot(str):
    if(not str):
      raise OstrichException(f"'nosnapshot' fiter called with an undefined or empty input "+getCurrentLocation())  
    return str.split("-")[0]

def basename(path):
    return os.path.basename(path)

def dirname(path):
    ret=os.path.dirname(path)
    if ret=="":
        ret="."
    return ret

def bool_helper(b):
    if isinstance(b, bool):
        if(b):
            return "true"
        else:
            return "false"
    else:
        return b

def toYaml(data):
    return yaml.dump(data)


def minVersion(version: string,versionToCheck: string,key: string) -> string:
    if(not version):
        raise OstrichException(f"Version not defined in {key}")

    v1= Version.parse(version)
    v2= Version.parse(versionToCheck)
    if v1 < v2:
        raise OstrichException(f"Version {version} defined in {key} must be greater than {versionToCheck}")
    return version

def maxVersion(version: string,versionToCheck: string,key: string) -> string:
    if(not version):
        raise OstrichException(f"Version not defined in {key}")

    v1= Version.parse(version)
    v2= Version.parse(versionToCheck)
    if v1 > v2:
        raise OstrichException(f"Version {version} defined in {key} must be lower than {versionToCheck}")
    return version


def toUnixPath(p):
    if not p:
        return p
    p = os.path.abspath(p)
    if os.name == 'nt':
        drive, tail = os.path.splitdrive(p)
        if drive:
            res = "/" + drive[0].lower() + tail.replace('\\', '/')
        else:
            res = p.replace('\\', '/')
        return res
    return p.replace('\\', '/')


def input_filter(value, input_name):
    global configAll
    # Use glom's default to avoid exception inside glom and handle it ourselves
    key = f"template.params.input.{input_name}"
    input_path = glom(configAll, key, default=None)
    
    if input_path is None:
        # We raise the exception, but we don't log it manually.
        # templateString will log it once at the end.
        raise OstrichException(f"Cannot locate key {key} in config file")
    
    # This path is relative from the ostrich.yaml location (result of 'here' filter)
    base = here(input_path)
    
    # Combine with the input value
    if value:
        return os.path.normpath(os.path.join(base, value)).replace("\\", "/")
    return base

## Jinja2 globals

def raise_helper(msg):
    raise OstrichException(msg)


# Get the line number from the stack as suggested in:
# https://stackoverflow.com/questions/71784095/how-to-get-current-line-of-source-file-when-processing-a-macro
def getCurrentLineNo():
    for frameInfo in stack():
        if frameInfo.frame.f_globals.get("__jinja_template__") is not None:
            template = frameInfo.frame.f_globals.get("__jinja_template__")
            break
    return template.get_corresponding_lineno(currentframe().f_back.f_lineno)

# Returns the current location in the template
# if the template is the root one, it returns the line number
# else it returns the template name and the line number (happens when we are in an included template)
def getCurrentLocation():
    template = None
    for frameInfo in stack():
        if frameInfo.frame.f_globals.get("__jinja_template__") is not None:
            template = frameInfo.frame.f_globals.get("__jinja_template__")
            break
    if template is None:
        return ""
    global jinja
    if(template == jinja):
        return " at line "+str(getCurrentLineNo())
    else:
        return "in "+str(template)+" at line "+str(template.get_corresponding_lineno(currentframe().f_back.f_lineno))


def get_helper(key):
    loc=getCurrentLocation()
    global configAll
    ret=configAll
    currentKey=""
    for k in key.split("."):
        if ret==None:
            return ""
        currentKey+=k+"."
        if k not in ret:
            raise OstrichException(f"Key {currentKey[:-1]} not defined {loc}")
        ret=ret[k]

    return ret


def safe_helper(key):
    global configAll
    ret=configAll
    currentKey=""

    for k in key.split("."):
        if ret==None:
            return ""
        currentKey+=k+"."
        if k not in ret:
            return ""
        ret=ret[k]
    return ret

def isDebugEnabled():
    global configAll
    return configAll['_ostrich']['loglevel'] < logging.INFO

## ----------------------------

def env(str):
    return os.getenv(str)

def render(str):
    return templateString(str,False)

def getConfigRoot():
    return os.path.expanduser("~")+"/.ostrich"

def getConfigDir():
    return getConfigRoot()+"/sdk-config"

def getConfigFile():
    return getConfigDir()+"/config.yaml"

def safeLoad(filename) -> dict:
    if not os.path.isfile(filename):
        return {}
    with open(filename, 'r+') as file:
        ret = yaml.safe_load(file)
        if ret==None:
            return {}
        return ret

def loadConf():
    return safeLoad(getConfigFile())


def filterDecorator(func):
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def globalDecorator(func):
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    
    return wrapper


def addFilter(name,func):
    global e
    if(name in e.filters):
        raise OstrichException(f"Filter {name} already defined")
    e.filters[name]=filterDecorator(func)


def addGlobal(name,func):
    global e
    if(name in e.globals):
        raise OstrichException(f"Global {name} already defined")
    e.globals[name]=globalDecorator(func)


def templateString(srcTemplate: string, filterRender: bool):
    global configAll
    global jinja
    global e

    e=Environment(block_start_string='[%',
    block_end_string='%]',
    variable_start_string='[[',
    variable_end_string=']]',
    comment_start_string='[#',
    comment_end_string='#]',
    loader=FileSystemLoader("/"))

    e.filters['here']=here
    e.filters['noslash']=noslash
    e.filters['md5hash']=md5hash
    e.filters['fromTemplate']=fromTemplate
    e.filters['fromTemplates']=fromTemplates
    e.filters['fromJob']=fromJob
    e.filters['fromTemplateInstance']=fromTemplateInstance
    e.filters['nosnapshot']=nosnapshot
    e.filters['basename'] = basename
    e.filters['dirname']  = dirname
    e.filters['bool'] = bool_helper
    e.filters['yaml'] = toYaml
    e.filters['minVersion'] = minVersion
    e.filters['maxVersion'] = maxVersion
    e.filters['toUnixPath'] = toUnixPath
    e.filters['input'] = input_filter

    e.globals['raise']=raise_helper
    e.globals['get']=get_helper
    e.globals['_']=safe_helper
    e.globals['isDebugEnabled']=isDebugEnabled
    e.globals['env']=env

    if(filterRender):
      e.filters['render']=render

    logging.debug(f"Execute {templateRoot()}/global/pretemplate.py")
    with open(f"{templateRoot()}/global/pretemplate.py","r") as f:
        code=f.read()
        locals={}
        locals['env']=e
        try:
            exec(code,globals(),locals)
        except Exception as e:
            logging.exception(e)
            raise OstrichException(f"Error executing global pretemplate.py: {e}")

    if os.path.exists(f"{configAll['_ostrich']['templateLocation']}/pretemplate.py"):
        logging.debug(f"Execute {configAll['_ostrich']['templateLocation']}/pretemplate.py")
        with open(f"{configAll['_ostrich']['templateLocation']}/pretemplate.py","r") as f:
            code=f.read()
            locals={}
            locals['env']=e
            try:
                exec(code,globals(),locals)
            except Exception as e:
                logging.exception(e)
                raise OstrichException(f"Error executing local pretemplate.py: {e}")

    try:
        jinja = e.from_string(srcTemplate)
        return jinja.render(configAll)
    except Exception as e:
        msg=" ".join(e.args)
        if(hasattr(e, 'filename') and e.filename!=None):
            msg+=" in "+str(e.filename)  
        if(hasattr(e, 'lineno')):
            msg+=" at line "+str(e.lineno)
        if(hasattr(e, 'name') and e.name!=None):
            msg+=" ("+str(e.name)+")"  
        if(hasattr(e, 'names') and e.names!=None):
            msg+=" ("+str(e.names)+")"
        raise OstrichException(f"Error rendering file {configAll['_ostrich']['currentfile']}: [{type(e).__name__}] {msg}")


def dict_merge(dct, merge_dct):
    """ Recursive dict merge. Inspired by :meth:``dict.update()``, instead of
    updating only top-level keys, dict_merge recurses down into dicts nested
    to an arbitrary depth, updating keys. The ``merge_dct`` is merged into
    ``dct``.
    :param dct: dict onto which the merge is executed
    :param merge_dct: dct merged into dct
    :return: None
    """
    for k, v in merge_dct.items():
        if (k in dct and isinstance(dct[k], dict) and isinstance(merge_dct[k], dict)):
            dict_merge(dct[k], merge_dct[k])
        else:
            dct[k] = merge_dct[k]


def getMergedConfig(inputDir: string, config: Any, params: Params):
    global configAll
    configAll = config
    templateConfig = {}
    globalTemplateConfig = {}

    configAll['_ostrich'] = {}
    configAll['_ostrich']['loglevel']=params.loglevel
    configAll['_ostrich']['operation']=""
    configAll['_ostrich']['tmpdir']=params.tmpdir

    if os.path.exists(inputDir+"/../global/config.yaml"):
        logging.debug("Loading global config file %s/config.yaml",inputDir+"/../global")
        with open(inputDir+"/../global/config.yaml") as f:
            globalTemplateConfig = yaml.safe_load(f)

    if os.path.exists(inputDir+"/config.yaml"):
        logging.debug("Loading config file %s/config.yaml",inputDir)
        with open(inputDir+"/config.yaml") as f:
            templateConfig = yaml.safe_load(f)
    else:
        logging.debug("No config.yaml file found in %s",inputDir)

    dict_merge(globalTemplateConfig,templateConfig)

    defaults = {}
    if os.path.exists(inputDir+"/default.yaml"):
        logging.debug("Loading default file %s/default.yaml",inputDir)
        with open(inputDir+"/default.yaml") as f:
            defaults = yaml.safe_load(f)
    else:
        logging.debug("No default.yaml file found in %s",inputDir)
    
    # Merge configAll (user config) into defaults, so user overrides defaults
    dict_merge(defaults, configAll)
    configAll = defaults    
    params.parsedPluginConfig = configAll

    configAll['_ostrich']['sdkconfig']=globalTemplateConfig
    configAll['_ostrich']['templateLocation']=getTemplatePath(params.getPluginConf("template.kind"))
    configAll['_ostrich']['templateRoot']=templateRoot()
    configAll['_ostrich']['localconfig']=safeLoad(getConfigFile())
    
    return configAll

def template(inputDir: string, config: Any, params: Params,operation):

    logging.debug(f"Templating {inputDir}")
    
    configAll = getMergedConfig(inputDir, config, params)
    configAll['_ostrich']['operation']=operation

    templatePathPrefix = getTemplatePath(params.getPluginConf("template.kind"))
    for subdir, dirs, files in os.walk(inputDir):
      logging.debug("Process subdir %s",subdir)
      dstdir = os.path.relpath(subdir, templatePathPrefix)
      if dstdir == ".":
          dstdir = ""
      dstdir = dstdir.replace("\\", "/") # Ensure forward slashes for consistency
      logging.debug("Destination dir %s",dstdir)

      # Skip test operation
      if dstdir.startswith("_"):
        logging.debug("Skip meta dir %s",dstdir)
      else:
        # The subdir is the absolute path to the template
        # we need the job, so we calculate the relative path from the template root
        # The first segment of this path is the operation
        configAll['_ostrich']['operation']=dstdir.split("/")[0]

        logging.debug("Operation %s",configAll['_ostrich']['operation'])

        for file in files:
            logging.debug("Process file %s",file)
            configAll['_ostrich']['currentfile']=file

            srcTemplateFile=subdir+"/"+file
            srcTemplate : string

            if(os.path.splitext(file)[1]==".tmpl"):

                with open(srcTemplateFile,'r') as f:
                    srcTemplate = f.read()

                template=templateString(srcTemplate,True)

                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug ("====== Templated resource ============")
                    logging.debug("Source file = %s",file)
                    print(template)
                    logging.debug ("======================================")

                operation(template,dstdir+"/"+os.path.splitext(file)[0],params)
            else:
                try:
                    with open(srcTemplateFile,'r') as f:
                        srcTemplate = f.read()
                    logging.debug("Copy file %s",file)
                    operation(srcTemplate,dstdir+"/"+file,params)

                except UnicodeDecodeError:

                    dstdirAbs=os.path.abspath(params.tmpdir+"/"+dstdir)

                    logging.debug("Copy binary file %s => %s",srcTemplateFile,dstdirAbs)

                    os.makedirs(dstdirAbs,exist_ok=True)
                    shutil.copy(srcTemplateFile,dstdirAbs+"/"+file)





def helm_env_for_ost(base_dir: Path) -> dict:
    """
    Retourne un environnement isolé pour Helm (config/cache/data)
    utilisé uniquement par ost.
    """
    return {
        **os.environ,
        "HELM_CONFIG_HOME": str(base_dir / "config"),
        "HELM_CACHE_HOME":  str(base_dir / "cache"),
        "HELM_DATA_HOME":   str(base_dir / "data"),
    }

def helm(*args: str) -> None:
    if shutil.which("helm") is None:
        raise OstrichException("helm binary not found")

    base_path = Path(getConfigRoot()) / "helm"
    env = helm_env_for_ost(base_path)

    # Crée les répertoires si nécessaires
    for key in ("HELM_CONFIG_HOME", "HELM_CACHE_HOME", "HELM_DATA_HOME"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["helm", *args],
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise OstrichException(f"Error executing helm {' '.join(args)}")