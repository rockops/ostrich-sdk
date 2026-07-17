import getpass
import json
import logging
import os

import src.util as util
from subprocess import run
from src.ostrichException import OstrichException
import os.path
from os import path
import traceback
import yaml
from glom import glom
from src.template import templateAll


_params: util.Params = None
_dryRun: bool = False
_localConfig: dict = {}
_argc: int = 0
_argv: list = []
_loglevel: int = logging.INFO


# Runners implementation

# Execute an operation in the current process
def inprocess(operation: str, params: util.Params):
    """
    Execute a dynamically loaded Python operation file in the current process.
    This function reads and executes a Python script file located at 
    {params.tmpdir}/{operation}/{operation}.py. It sets up global variables
    needed by the operation and handles execution errors with detailed 
    error reporting.
    Args:
        operation (string): The name of the operation to execute. Used to 
            construct the file path to the operation script.
        params (util.Params): A parameters object containing:
            - tmpdir (str): The temporary directory path where operation files are stored
            - dryRun (bool): Whether to run in dry-run mode
            - operationParams (list): Command-line parameters to pass to the operation
            - loglevel (int): The logging level to set
    Raises:
        OstrichException: If the operation script encounters an error during 
            execution. The exception includes the file path, line number where 
            the error occurred, and a code context (5 lines before and after 
            the error).
        Exception: Re-raises any other exceptions not caught by the custom 
            error handler.
    Side Effects:
        Sets global variables:
        - _params: The operation parameters
        - _dryRun: The dry-run flag
        - _localConfig: The loaded configuration
        - _argc: The count of operation parameters
        - _argv: The operation parameters list
        - _loglevel: The logging level
    """
    logging.info(f"Execute {params.tmpdir}/{operation}/{operation}.py")
    with open(f"{params.tmpdir}/{operation}/{operation}.py","r") as f:
        code=f.read()

        exec_globals = globals().copy()
        exec_globals.update({
            "_params": params,
            "_dryRun": params.dryRun,
            "_localConfig": util.loadConf(),
            "_argv": params.operationParams,
            "_argc": len(params.operationParams),
            "_loglevel": params.loglevel,
        })

        try:
            exec(code, exec_globals)
        except Exception as e:
            lineNumber: int = None
            # Get the line number
            for entry in traceback.extract_tb(e.__traceback__):
              if(entry.filename=="<string>"):
                lineNumber = entry.lineno
                beforeStart = lineNumber - 5 if lineNumber - 5 >= 0 else 0
                beforeEnd = lineNumber - 1 if lineNumber - 1 >= 0 else 0
                afterStart = lineNumber if lineNumber < len(code) else len(code)
                afterEnd = lineNumber + 5 if lineNumber + 5 < len(code) else len(code)

                logging.error("Error occurred in %s at line %d: %s", f"{params.tmpdir}/{operation}/{operation}.py",lineNumber, str(e))
                codeLines=code.split("\n")
                print("Code:")
                for line in codeLines[beforeStart:beforeEnd]:
                    print("   "+line)
                print(">> "+codeLines[lineNumber-1])
                for line in codeLines[afterStart:afterEnd]:
                    print("   "+line)
                print("----")
                raise OstrichException(f"Error in {params.tmpdir}/{operation}/{operation}.py at line {lineNumber}: {str(e)}")
        
            raise


# Execute an operation locally by running commands defined in a YAML file
def shell(operation: str, params: util.Params):
    """
    Execute local commands defined in a YAML configuration file.
    
    Loads a YAML file containing a list of commands and environment variables,
    merges the environment variables with the current process environment,
    and executes each command sequentially in a shell.
    
    Args:
        operation (string): The name of the operation, used to locate the command file
            at {params.tmpdir}/{operation}/{operation}.yaml
        params (util.Params): Parameters object containing tmpdir path where operation
            configuration files are stored
    
    Raises:
        OstrichException: If the command file is not found at the expected path
        OstrichException: If any command in the list fails (returns non-zero exit code)
    
    Returns:
        None
    """
    commandFile=f"{params.tmpdir}/{operation}/{operation}.yaml"
    if not os.path.isfile(commandFile):
        raise OstrichException(f"Local command file {commandFile} not found")

    commandConf=util.safeLoad(commandFile)
    commands=commandConf.get("commands",[])
    envVars=commandConf.get("env",{})

    env=os.environ.copy()
    for k in envVars.keys():
        env[k]=envVars[k]

    env["LOGLEVEL"]=str(params.loglevel)
    env["DRYRUN"]=str(params.dryRun).lower()
    env["TEMPLATE_DIR"]=params.tmpdir
    env["OPERATION"]=operation
    env["ARGV"]=",".join(params.operationParams)
    env["ARGC"]=str(len(params.operationParams))
    env["ARGV_JSON"]=json.dumps(params.operationParams)

    for command in commands:
        logging.debug(f"Executing local command: {command}")
        result=run(command, shell=True, env=env)
        if(result.returncode != 0):
            raise OstrichException(f"Local command {command} failed with code {result.returncode}")


# Execute an operation in a container
def container(operation: str, params: util.Params):
    commandFile=f"{params.tmpdir}/{operation}/{operation}.yaml"
    if not os.path.isfile(commandFile):
        raise OstrichException(f"Local command file {commandFile} not found")

    commandConf=util.safeLoad(commandFile)
    commands=commandConf.get("commands",[])
    envVars=commandConf.get("env",{})

    env={}
    for k in envVars.keys():
        env[k]=envVars[k]

    def toContainerPath(p):
        return util.toUnixPath(p)

    env["LOGLEVEL"]=str(params.loglevel)
    env["DRYRUN"]=str(params.dryRun).lower()
    env["TEMPLATE_DIR"]=toContainerPath(params.tmpdir)
    env["OPERATION"]=operation
    env["ARGV"]=",".join(params.operationParams)
    env["ARGC"]=str(len(params.operationParams))
    env["ARGV_JSON"]=json.dumps(params.operationParams)

    env["OST_DEBUG"]=str(logging.DEBUG)
    env["OST_INFO"]=str(logging.INFO)
    env["OST_WARNING"]=str(logging.WARNING)
    env["OST_ERROR"]=str(logging.ERROR)
    env["OST_CRITICAL"]=str(logging.CRITICAL)
    env["OST_DEBUG_MODE"]=str(params.loglevel <= logging.DEBUG).lower()

    runtime=params.getPluginConf("template.runtime","docker")

    entrypointDefault=glom(commandConf,"runner.entrypoint",default=params.getPluginConf("runner.entrypoint",None))
    imageDefault=glom(commandConf,"runner.image",default=params.getPluginConf("runner.image",None))
    
    if(runtime not in ["docker","podman"]):
        raise OstrichException(f"Unsupported container runtime {runtime} for operation {operation}")

    testCommand= [runtime, "-v"]

    try:
        result=run(testCommand, shell=False, capture_output=True, text=True)
    except FileNotFoundError:
        raise OstrichException(f"Container runtime {runtime} not available")

    if(result.returncode != 0):
        raise OstrichException(f"Container runtime {runtime} not available: {result.stderr}")

    logging.info(f"Using container runtime: {result.stdout.strip()}")
    
    def getHostPath(p):
        """
        Translate a container-local path to its corresponding path on the host machine.

        This function is necessary for Docker-in-Docker (DinD) environments. When 
        mounting volumes in a nested container, the source path must be from the 
        host's perspective, not the intermediate container's.

        It uses the translation table from '/ostrich-volumes.yaml' (generated by ostd) 
        to perform a reverse search and find the right path on the host.
        If '/ostrich-volumes.yaml' does not exist, it returns the path as-is.
        """
 
        path = os.path.normpath(p)
        
        if os.path.exists("/ostrich-volumes.yaml"):
            try:
                with open("/ostrich-volumes.yaml", "r") as f:
                    mappings = yaml.safe_load(f)
                    if mappings:
                        # Sort by container path length descending to match longest prefix first
                        mappings.sort(key=lambda x: len(x.get("container", "")), reverse=True)
                        for m in mappings:
                            container_path = m.get("container")
                            host_path = m.get("host")
                            if container_path and host_path:
                                cp = os.path.normpath(container_path)
                                hp = os.path.normpath(host_path)
                                if path.startswith(cp):
                                    res = path.replace(cp, hp, 1)
                                    logging.debug(f"Translated container path {path} to host path {res} using /ostrich-volumes.yaml")
                                    return res
            except Exception as e:
                logging.warning(f"Error reading /ostrich-volumes.yaml: {e}")

        return path

    dockerCommand=[runtime]

    dockerCommand.append("run")
    dockerCommand.append("--rm")
    for k in env.keys():
        dockerCommand.append("-e")
        dockerCommand.append(f"{k}={env[k]}")
    dockerCommand.append("-v")
    tmpDir = os.path.abspath(params.tmpdir)
    dockerCommand.append(f"{getHostPath(tmpDir)}:{toContainerPath(tmpDir)}")
    location=util.getLocation()
    dockerCommand.append("-v")
    dockerCommand.append(f"{getHostPath(location)}:{toContainerPath(location)}")

    templateRoot = util.templateRoot()
    if os.path.exists(templateRoot):
        dockerCommand.append("-v")
        dockerCommand.append(f"{getHostPath(templateRoot)}:{toContainerPath(templateRoot)}")

    testTemplateRoot = util.testTemplateRoot()
    if os.path.exists(testTemplateRoot):
        dockerCommand.append("-v")
        dockerCommand.append(f"{getHostPath(testTemplateRoot)}:{toContainerPath(testTemplateRoot)}")

    extraRoot = util.extraTemplateRoot()
    if os.path.exists(extraRoot):
        dockerCommand.append("-v")
        dockerCommand.append(f"{getHostPath(extraRoot)}:{toContainerPath(extraRoot)}")

    # Always mount docker socket
    dockerCommand.append("-v")
    dockerCommand.append("/var/run/docker.sock:/var/run/docker.sock")

    # Support for specifying a custom network (e.g. host)
    network = params.getPluginConf("template.network", None)
    if network:
        dockerCommand.append("--network")
        dockerCommand.append(network)

    # Mount host's Docker configuration to share registry credentials
    docker_config = os.path.join(os.path.expanduser("~"), ".docker", "config.json")
    if os.path.isfile(docker_config):
        # We mount it to the user's home in the container. 
        # Since we often run with --user UID:GID, we should try to put it where the container's user expects it.
        # For buildpacks/pack and many others, /root/.docker/config.json or $HOME/.docker/config.json is standard.
        container_home = "/root" # Default if running as root
        if params.getPluginConf("runner.user", None) or hasattr(os, 'getuid'):
            # If not root, we don't know the container home for sure, but many images use /home/cnb or similar.
            # However, most tools also look at DOCKER_CONFIG env var.
            env["DOCKER_CONFIG"] = "/.docker"
            dockerCommand.append("-v")
            dockerCommand.append(f"{getHostPath(docker_config)}:/.docker/config.json:ro")
        else:
            dockerCommand.append("-v")
            dockerCommand.append(f"{getHostPath(docker_config)}:/root/.docker/config.json:ro")

    # Add host's hosts file entries to the container for portability.
    # Using --add-host is more robust than bind-mounting /etc/hosts as it ensures
    # the entries are also available via Docker's internal DNS (127.0.0.11),
    # which is required by some resolvers (like Go's) in minimal containers.
    # This also populates the container's /etc/hosts file with these entries.
    hosts_file = "/etc/hosts"
    if os.name == 'nt':
        hosts_file = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'System32\\drivers\\etc\\hosts')
    
    if os.path.isfile(hosts_file):
        try:
            added_hosts = set()
            with open(hosts_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        ip = parts[0]
                        # Basic check for an IP address (IPv4 or IPv6)
                        if any(c in '0123456789.:' for c in ip) and all(c in '0123456789.:abcdefABCDEF' for c in ip):
                            for name in parts[1:]:
                                if name.lower() not in ['localhost', 'ip6-localhost', 'ip6-loopback', 'ip6-allnodes', 'ip6-allrouters']:
                                    if (name, ip) not in added_hosts:
                                        dockerCommand.append("--add-host")
                                        dockerCommand.append(f"{name}:{ip}")
                                        added_hosts.add((name, ip))
        except Exception as e:
            logging.warning(f"Failed to parse host's hosts file: {e}")

    dockerCommand.append("-w")
    dockerCommand.append(toContainerPath(location))

    if runtime == "podman":
        dockerCommand.append("--userns=keep-id")
        # Security opt needed for socket access in podman
        dockerCommand.append("--security-opt")
        dockerCommand.append("label=disable")
    else:
        user = glom(commandConf, "runner.user", default=params.getPluginConf("runner.user", None))
        if user:
            dockerCommand.append("--user")
            dockerCommand.append(user)
        else:
            if hasattr(os, 'getuid'):
                uid = os.getuid()
                gid = os.getgid()
                dockerCommand.append("--user")
                dockerCommand.append(f"{uid}:{gid}")
                
                # If we are not root, we need to add the group of the docker socket to the user
                if os.path.exists("/var/run/docker.sock"):
                    docker_gid = os.stat("/var/run/docker.sock").st_gid
                    dockerCommand.append("--group-add")
                    dockerCommand.append(str(docker_gid))

    for command in commands:
        fullCommand=dockerCommand.copy()
        cmd = command  # Initialize cmd for error reporting

        entrypoint=entrypointDefault
        image=imageDefault

        if isinstance(command,str) or isinstance(command,list):
            cmd = command
            if entrypoint is not None:
                fullCommand.append("--entrypoint")
                fullCommand.append(entrypoint)
            
            if image is None:
                raise OstrichException(f"No container image defined for operation {operation}")
            
            fullCommand.append(image)

            if isinstance(command,list):
                fullCommand.extend(command)
            else:
                fullCommand.extend(["sh","-c",command])
        elif isinstance(command,dict):
            cmd=command.get("cmd",None)
            if cmd is None:
                raise OstrichException(f"Invalid command definition in operation {operation}: 'cmd' key missing")
            
            entrypoint=command.get("entrypoint",entrypointDefault)
            image=command.get("image",imageDefault)
                
            if entrypoint is not None:
                fullCommand.append("--entrypoint")
                fullCommand.append(entrypoint)
                
            if image is None:
                raise OstrichException(f"No container image defined for operation {operation}")
                
            fullCommand.append(image)
                
            if isinstance(cmd, str):
                fullCommand.extend(["sh","-c",cmd])
            elif isinstance(cmd, dict):
                for k,v in cmd.items():
                    fullCommand.append(k)
                    if v is not None:
                        fullCommand.append(str(v))
            elif isinstance(cmd, list):
                fullCommand.extend(cmd)
            else:
                raise OstrichException(f"Invalid command definition in operation {operation}: expected string, list or dict")
        

        fullCommand = [str(i) for i in fullCommand]
        logging.debug(f"Executing local command: {"|".join(fullCommand)}")
        result=run(fullCommand, shell=False)
        if(result.returncode != 0):
            raise OstrichException(f"Container command {cmd} failed with code {result.returncode}")


def task(operation: str, params: util.Params):

    if not params.noDeps:
        depfile=f"{params.tmpdir}/{operation}/dependencies.yaml"
        if os.path.isfile(depfile):
            with open(depfile) as f:
                dependenciesYaml = yaml.safe_load(f)
                dependencies=dependenciesYaml['dependencies']
                for dep in dependencies:
                    if dep in params.skip:
                        logging.info(f"Skipping dependency {dep}")
                    else:
                        if dep in params.executedTasks:
                            logging.info(f"Dependency {dep} already executed")
                        else:
                            params.executedTasks.append(dep)
                            task(dep,params)

    if not os.path.isdir(f"{params.tmpdir}/{operation}"):
        raise OstrichException(f"Operation {operation} not found for template {params.getPluginConf('template.kind')}")

    # Gets the runner: first look in the operation conf (<operation>/<operation>.yaml),
    # else in the template conf (template.yaml)
    operationConfFile=f"{params.tmpdir}/{operation}/{operation}.yaml"
    runner="_NOTFOUND_"
    if os.path.isfile(operationConfFile):
        operationConf=util.safeLoad(operationConfFile)
        runner=glom(operationConf,"runner.kind",default="_NOTFOUND_")

    if(runner=="_NOTFOUND_"):
        templateConfFile=f"{params.tmpdir}/template.yaml"
        if os.path.isfile(templateConfFile):
            templateConf=util.safeLoad(templateConfFile)
            runner=glom(templateConf,"runner.kind",default="inprocess")
        else:
            runner="inprocess"


    logging.info("=========== %s ===========",operation)
    if(runner=="inprocess"):
        inprocess(operation,params)
    elif(runner=="shell"):
        shell(operation,params)
    elif(runner=="container"):
        container(operation,params)
    else:
        logging.error("Unknown runner %s for operation %s",runner,operation)
        print("""Available runners:
- inprocess : execute the operation in the current process (Python)
- shell     : execute local commands defined in a YAML file
- container : execute the operation in a container""")
        raise OstrichException(f"Unknown runner {runner} for operation {operation}")



def execute(params: util.Params):
    templateAll(params)
    task(params.operation,params)





def configUsage():
    print("""Usage: 
- ost config <operation> <param>
  Available operation:
  - help                                      : print this help
  - get | list                                : list all config keys
  - get <key>                                 : get the value of the <key> key
  - set <key> <value>                         : set the value of the <key> key to <value>
  - unset <key>                               : delete the <key> key
  - login <type> <url> <user> <password>      : login to a service of type <type> (example: helm)
                                                if no parameter is set, interactive mode is proposed
  - login <type> list                         : list the credentials  (token + user/password) for a service of type <type>
  - logout <type> <url>                       : logout from a service of type <repotype>
  - token <type> <url> <token>                : set a token a service of type <type> (example: sonarqube)
                                                if no parameter is set, interactive mode is proposed
  - token <type> list                         : list the credentials (token + user/password) for a service of type <type>
          
  Example:
  To login to a helm registry: 
    ost config login helm http://myregistry.com myuser mypassword
  To logout from a sonar registry:
    ost config logout sonar http://mysonar.com""")



def lscred(config: dict, type: str):
    for k in config.keys():
        spl=k.split("_")
        if(len(spl)>2 and (spl[1] in ["credential"])):
            if(type=="list" or spl[0]==type):
                if(len(config[k].split(':'))==1):
                    val="***"
                else:
                    val=config[k].split(':')[0]+":***"
                print(f"{spl[0]}: {k.replace(spl[0]+'_credential_','')}={val}")


def config(params: util.Params):
    params.collectStandardArgs()

    if(len(params.operationParams)==0):
        configUsage()
        raise OstrichException("Invalid number of parameters")

    if(params.operationParams[0]=="help" or params.usage):
        configUsage()
        return
    
    confdir=util.getConfigDir()
    conffile=util.getConfigFile()

    os.makedirs(confdir,exist_ok=True)

    logging.debug("Config file location: %s",conffile)

    if(params.operationParams[0] in ["get","list"]):
        if not path.isfile(conffile):
            logging.info("No configuration available")
            return

        config=util.safeLoad(conffile)
        if(len(params.operationParams)==1):
            for k in config.keys():
                spl=k.split("_")
                val=config[k]                    
                if(len(spl)>2 and (spl[1] in ["credential"])):
                    if(":" in config[k]):
                        val=config[k].split(':')[0]+":***"
                    else:
                        val="***"
                print(f"{k}={val}")
        else:
            try:
                print(config[params.operationParams[1]])
            except KeyError:
                raise OstrichException(f"Key {params.operationParams[1]} not found")

    elif(params.operationParams[0] in ["set"]):
        if(len(params.operationParams)!=3):
            logging.error("Invalid number of parameters")
            configUsage()
            raise OstrichException("Invalid number of parameters")
        
        config=util.safeLoad(conffile)
        config[params.operationParams[1]]=params.operationParams[2]
        util.safeWriteYaml(conffile, config)
        logging.info("Configuration updated for key %s",params.operationParams[1])

    elif(params.operationParams[0] in ["unset"]):
        if(len(params.operationParams)!=2):
            logging.error("Invalid number of parameters")
            configUsage()
            raise OstrichException("Invalid number of parameters")
        
        config = util.safeLoad(conffile)
        config.pop(params.operationParams[1], None)
        util.safeWriteYaml(conffile, config)
        logging.info("Configuration key %s deleted",params.operationParams[1])

    elif(params.operationParams[0] in ["login"]):
        config=util.safeLoad(conffile)
        if(len(params.operationParams)<2):
            configUsage()
            raise OstrichException("Invalid number of parameters")
    
        type=params.operationParams[1]

        if(type=="list" or len(params.operationParams)>=3 and params.operationParams[2] in ["list"]):
            lscred(config,type)
            return

        if(len(params.operationParams)==5):
            repo=params.operationParams[2]
            user=params.operationParams[3]
            password=params.operationParams[4]
        elif(len(params.operationParams)==3):
            repo=params.operationParams[2]
            user=input(type+" user: ")
            password=getpass.getpass()
        else:
            repo=input(type+" address: ")
            user=input(type+" user: ")
            password=getpass.getpass()

        # Delete the trailing /
        while(repo.endswith("/")):
            repo=repo[:-1]            

        config[type+'_credential_'+repo]=user+":"+password
        util.safeWriteYaml(conffile, config)
        logging.info("Credential registered for %s server %s",type,repo)

    elif(params.operationParams[0] in ["token"]):
        config=util.safeLoad(conffile)
        if(len(params.operationParams)<2):
            configUsage()
            raise OstrichException("Invalid number of parameters")
    
        type=params.operationParams[1]

        if(type=="list" or len(params.operationParams)>=3 and params.operationParams[2] in ["list"]):
            lscred(config,type)
            return

        if(len(params.operationParams)==4):
            repo=params.operationParams[2]
            password=params.operationParams[3]
        elif(len(params.operationParams)==3):
            repo=params.operationParams[2]
            password=getpass.getpass(type+" token: ")
        else:
            repo=input(type+" address: ")
            password=getpass.getpass(type+" token: ")

        # Delete the trailing /
        while(repo.endswith("/")):
            repo=repo[:-1]            

        config[type+'_credential_'+repo]=password
        util.safeWriteYaml(conffile, config)
        logging.info("Token registered for %s server %s",type,repo)

    elif(params.operationParams[0] in ["logout"]):
        if(len(params.operationParams)<3):
            configUsage()
            raise OstrichException("Invalid number of parameters")

        type=params.operationParams[1]

        if(len(params.operationParams)==3):
            repo=params.operationParams[2]
        else:
            repo=input(type+" address: ")

        config=util.safeLoad(conffile)
        config.pop(type+'_credential_'+repo, None)
        util.safeWriteYaml(conffile, config)
        logging.info("Credential deleted for %s server %s",type,repo)
