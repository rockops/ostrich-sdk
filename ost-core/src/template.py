import logging
import os
import shutil
import tempfile
import unittest

from glom import glom
import pytest
import yaml
import tarfile
import src.util as util
from src.ostrichException import OstrichException
from subprocess import run
import src.registry as registry_op

def templateUsage():
    print("""Usage: 
- ost template
  to generate the template locally in the current directory
  
- ost template <function> <param>
  Available functions:
  - help                        : print this help
  - list                        : list available templates
  - describe <template_name>    : detailed description of <template_name>
  - config <template_name>      : generate a sample configuration for <template_name>
  - install --directory <directory> : install template from directory <directory>
                                  The name of the template is the name of the directory
                                  --link : create a symlink instead of copying the folder
  - install <registry>/<template_name>:<version> : install template from a registry
                                  --skip-tls-verify : skip TLS verification (not safe for production)
  - delete|rm <template_name>   : delete a custom template
  - test <template_name>        : run the tests for the template <template_name>
                                  Details with 'ost template test info'
  - values                      : display the actual values used for rendering
  - package <template_dir>      : package the template located in <template_dir>
  - publish <folder> <registry> : package and publish a template to an OCI registry
  - search [registry] <query> [--versions] : search for templates in registries""")


def getTemplateBusinessName(templateName):
    info = getTemplateInfo(templateName)
    return info['name']

def getTemplateInfo(templateName):
    try:
        path = util.getTemplatePath(templateName)
        yaml_path = os.path.join(path, "template.yaml")
        
        source = "builtin"
        if path.startswith(util.extraTemplateRoot()):
            if os.path.islink(path):
                source = os.readlink(path)
            else:
                source_file = os.path.join(path, ".ostrich_source")
                if os.path.exists(source_file):
                    with open(source_file, "r") as f:
                        source = f.read().strip()
                else:
                    source = "custom"
        elif path.startswith(util.testTemplateRoot()):
            source = "test"

        config = {}
        if os.path.exists(yaml_path):
            config = util.safeLoad(yaml_path)
        
        return {
            "name": glom(config, "name", default=templateName),
            "version": glom(config, "version", default="0.0.0"),
            "description": glom(config, "description", default=""),
            "source": source
        }
    except Exception:
        pass
    
    # Fallback if template.yaml is missing or error occurs
    return {
        "name": templateName,
        "version": "0.0.0",
        "description": "",
        "source": "unknown"
    }
            

def describePretty(templateName):
    if os.path.exists(util.getTemplatePath(templateName)+"/_doc/description.md"):
      cmd=['glow', util.getTemplatePath(templateName)+"/_doc/description.md" ]
      try:  
        if(run(cmd).returncode != 0):
          raise OstrichException("glow failed")
      except BaseException:
        print(getTemplateDescription(templateName))
        print("===    Display raw markdown. Consider installing glow  ===")
        print("===             to improve your experience             ===")
    else:
        raise OstrichException(f"No description available for {templateName}")
    

def getTemplateDescription(templateName):
    try:
        with open(util.getTemplatePath(templateName)+"/_doc/description.md","r") as f:
            return f.read()
    except OstrichException:
        raise
    except BaseException:
        return f"No description available for {templateName}"


def getTemplateConfig(templateName):
    try:
        with open(util.getTemplatePath(templateName)+"/_doc/ostrich.yaml","r") as f:
            return f.read()
    except OstrichException:
        raise
    except BaseException as base:
        logging.critical(f"No configuration available for template {templateName}")
        raise OstrichException(base)


def testUsage():
    print("""Usage:
- ost template test <template_name> [-- pytest options]
    o Execute the tests for the template <template_name>. The tests are located in the 'test' directory of the template.
      Any files matching test_*.py will be executed using pytest.    
    o If <template_name> is 'all', all the tests for all the templates will be executed.
    o To pass extra options, use '--' followed by the options.
      --test <file.py::test_suite::test_name>   : execute only the test <test_name> in the suite <test_suite> in the file <file.py>
      --ost                                     : execute tests using the ost (Python) runner only
      --ostd                                    : execute tests using the ostd (Docker) runner only
      (default is to run both if supported by the test)
      other options after -- are directly passeed to pytest.

    Examples:
          
    - To execute the tests for all the templates:      
        ost template test all 
    - To execute the unit tests:
        ost template test unit-tests
    - To execute the unit tests using the Docker runner (ostd):
        ost template test unit-tests --ostd
    - To exectute the frontend tests, and display the output even for successful tests:
        ost template test frontend -- -rP
      (check the pytest documentation for more options)
    - To execute a specific test in the frontend tests:
        ost template test frontend -- -k test_mytest
          Note: with this option, all the frontend tests with a name matching 'test_mytest'
          will be executed. You can potentially execute multiple tests with this option.
          or
        ost template test frontend -- --test test_front.py::TestFrontend::test_mytest
      This will execute exactly 1 test, 'test_mytest' in the 'TestFrontend' suite.
    
""")



def installTemplateFromDir(name, sourceDir, link=False, source=None):
    if not name or name in [".", ".."]:
        raise OstrichException(f"Invalid template name: {name}")
    
    target = os.path.join(util.extraTemplateRoot(), name)
    logging.debug("Target=%s",target)
    if(os.path.lexists(target)):
        if os.path.islink(target):
            os.unlink(target)
        else:
            shutil.rmtree(target)
    os.makedirs(util.extraTemplateRoot(), exist_ok=True)
    
    if link:
        sourceAbs = os.path.abspath(sourceDir)
        os.symlink(sourceAbs, target)
        logging.info(f"Template {name} successfully linked to {target}")
    else:
        shutil.copytree(sourceDir,target)
        logging.info(f"Template {name} successfully installed in {target}")
        if source:
            with open(os.path.join(target, ".ostrich_source"), "w") as f:
                f.write(source)

def ensureTmpDir(params: util.Params):
    logging.info("Using output dir %s",params.tmpdir)
    if not os.path.exists(params.tmpdir):
        os.makedirs(params.tmpdir)

    if os.listdir(params.tmpdir):
        if(params.rmTmpDir):
            logging.info("Cleaning output directory")
            shutil.rmtree(params.tmpdir)
        else:
            if(not params.forceTmpDir):
                raise OstrichException("Directory "+params.tmpdir+" is not empty. Use \"--rm\" option to force cleanup or \"--force\" to overwrite existing files")



def saveToTmp(template: str, originalFilename: str,params: util.Params):
    
    dest=os.path.abspath(params.tmpdir+"/"+originalFilename)
    destdir=os.path.dirname(dest)

    if not os.path.isdir(destdir):
        os.makedirs(destdir)

    with open(dest,"w") as f:
        f.write(template)


def templateAll(params: util.Params):
    pluginName=params.getPluginConf("plugin.name","no-name")
    pluginBusinessName=params.getPluginConf("plugin.business_name","Generic plugin")
    pluginVersion=params.getPluginConf("plugin.version","0.0.0")
    template=params.getPluginConf("template.kind")

    logging.info("Template plugin \"%s\" (%s:%s)",pluginBusinessName,pluginName, pluginVersion)

    templatePath=util.getTemplatePath(template)

    logging.debug("ParsedPluginConfig=%s",params.parsedPluginConfig)

    util.template(templatePath,params.parsedPluginConfig,params,saveToTmp)

    for root, dirs, files in os.walk(templatePath):
        for filename in files:
            proot = os.path.relpath(root, templatePath)
            if proot == ".":
                proot = ""
            proot = proot.replace("\\", "/")
            
            targetFilename=filename
            if(targetFilename.endswith(".tmpl")):
                targetFilename=targetFilename.replace(".tmpl","")
            
            # Using os.path.join for safety
            target = os.path.join(params.tmpdir, proot, targetFilename)
            
            if os.path.exists(target):
                st = os.stat(os.path.join(root, filename))
                logging.debug(f"chmod {st.st_mode} {target}")
                os.chmod(target,st.st_mode)

    for root, dirs, files in os.walk(params.tmpdir):
        for dirname in dirs:
            if(dirname == "application-name"):
                shutil.copytree(os.path.join(root, dirname),os.path.join(root,pluginName), dirs_exist_ok = True)
                shutil.rmtree(os.path.join(root, dirname))
                #os.rename(os.path.join(root, dirname),os.path.join(root,pluginName))

def packageUsage():
    print("""Usage:
- ost template package <template_dir> [-o|--output <output_dir>]
  o Package the template located in <template_dir> into a distributable format.
""")


def packageAux(packageDir: str, packageOutput: str, deleteTmpDir: bool):
    logging.debug("Packaging template from %s to %s",packageDir,packageOutput)

    if(not os.path.isdir(packageDir)):
        raise OstrichException(f"Template directory {packageDir} does not exist or is not a directory")

    if(not os.path.isdir(packageOutput)):
        raise OstrichException(f"Output directory {packageOutput} does not exist or is not a directory")

    if(not os.path.exists(packageDir+"/template.yaml")):
        packageUsage()
        raise OstrichException(f"Template directory {packageDir} does not contain a template.yaml file")

    logging.info(f"Packaging template from {packageDir} to {packageOutput}")

    templateContent=util.safeLoad(packageDir+"/template.yaml")
    plugin_name=glom(templateContent, "name", default=None)

    if(plugin_name is None):
        raise OstrichException(f"Template file {packageDir}/template.yaml does not define a plugin name")

    # Validation: _doc/ostrich.yaml must exist and template.kind must match plugin_name
    ostrich_yaml_path = packageDir + "/_doc/ostrich.yaml"
    if not os.path.exists(ostrich_yaml_path):
        raise OstrichException(f"Template directory {packageDir} does not contain a _doc/ostrich.yaml file")
    
    ostrichContent = util.safeLoad(ostrich_yaml_path)
    template_kind = glom(ostrichContent, "template.kind", default=None)
    
    if template_kind != plugin_name:
        raise OstrichException(f"Validation failed: template.kind '{template_kind}' in _doc/ostrich.yaml does not match template name '{plugin_name}' in template.yaml")

    with tempfile.TemporaryDirectory(delete=deleteTmpDir) as tmpdirname:
        logging.debug("Using temporary directory %s",tmpdirname)

        targetTmpDir=tmpdirname+"/"+plugin_name
        os.makedirs(targetTmpDir, exist_ok=True)
        shutil.copytree(packageDir,targetTmpDir+"/template", dirs_exist_ok = True)
        
        chart={}
        chart["apiVersion"]="v2"
        chart["name"]=plugin_name
        chart["version"]=glom(templateContent, "version", default="0.0")
        chart["description"]=glom(templateContent, "description", default="Ostrich template plugin")
        chart["type"]="application" 

        with open(targetTmpDir+"/Chart.yaml","w") as f:
            yaml.dump(chart, f)

        logging.info(f"Packaging helm chart to {packageOutput}")
        util.helm("package", targetTmpDir, "-d", packageOutput)
        

def package(params: util.Params):
    logging.info("Packaging template plugin")

    args=params.operationParams[1:]
    packageDir="."

    # The -o option is a standard option, and the argument is in the params.tmpdir variable
    packageOutput=params.tmpdir if params.tmpdir != None else "."

    while len(args):
        param=args.pop(0)
        if(packageDir == "."):
            packageDir=param
        else:
            packageUsage()
            quit(1)

    packageAux(packageDir,packageOutput,params.deletePluginTmpDir)


def template(params: util.Params):
    logging.debug("PARAMS %s",params.usage)
    logging.debug("operationParams %s",params.operationParams)

    params.collectStandardArgs()
    args = params.operationParams

    if params.usage or (len(args) > 0 and args[0] in ["help", "-h", "--help"]):
        templateUsage()
        return

    # If no subcommand, render the template in the current directory
    if len(args) == 0:
        try:
            params.loadPluginConf()
        except BaseException as e:
            logging.error("Try \"ost template help\" to know how to use the template command")
            raise OstrichException(f"Error loading plugin configuration for rendering: {str(e)}")

        if not params.userOutput:
            params.tmpdir = params.getPluginConf("plugin.name", "no-name")
        ensureTmpDir(params)
        templateAll(params)
        return

    sub = args[0]

    if sub in ["list", "ls"]:
        logging.info("Available plugins:")
        
        folders = []
        templatePath=util.templateRoot()
        if os.path.exists(templatePath):
            for t in os.listdir(templatePath):
                if t != "global":
                    folders.append(t)
        
        extraTemplatePath=util.extraTemplateRoot()
        if os.path.exists(extraTemplatePath):
            for t in os.listdir(extraTemplatePath):
                if t != "global" and t not in folders:
                    folders.append(t)

        for t in sorted(folders):
            info = getTemplateInfo(t)
            desc = f": {info['description']}" if info['description'] else ""
            source_info = f" [{info['source']}]" if info['source'] else ""
            print(f"- {info['name']} ({info['version']}){source_info}{desc}")

        print("")
        print("To get a detailed description of a template, use:")
        print("  ost template describe <template_name>")
        

    elif sub == "describe":
        if len(args) < 2:
            templateUsage()
            raise OstrichException("Invalid number of parameters")
        name = args[1]
        templatePath = util.getTemplatePath(name)
        print("====== " + getTemplateBusinessName(name) + " =======")
        describePretty(name)
        print("")
        print("Available tasks:")
        for t in sorted(os.listdir(templatePath)):
            task_dir = os.path.join(templatePath, t)
            if os.path.isdir(task_dir):
                if os.path.isfile(os.path.join(task_dir, f"{t}.py.tmpl")) or os.path.isfile(os.path.join(task_dir, f"{t}.yaml.tmpl")):
                    print("- " + t)
                    desc_path = os.path.join(task_dir, "description.md")
                    if os.path.isfile(desc_path):
                        try:
                            # Try to use glow for pretty printing
                            if run(['glow', '--version'], capture_output=True).returncode == 0:
                                run(['glow', desc_path])
                            else:
                                with open(desc_path, 'r') as f:
                                    print("  " + f.read().replace('\n', '\n  ').strip())
                        except Exception:
                            try:
                                with open(desc_path, 'r') as f:
                                    print("  " + f.read().replace('\n', '\n  ').strip())
                            except Exception:
                                pass
                        print("")

    elif sub == "config":
        if len(args) < 2:
            templateUsage()
            raise OstrichException("Invalid number of parameters")
        name = args[1]
        print("# ====== " + getTemplateBusinessName(name) + " configuration sample =======")
        print(getTemplateConfig(name))

    elif sub == "install":
        if params.skipTlsVerify:
            logging.warning("TLS verification is skipped. This is NOT safe for production!")

        sub_args = args[1:]
        if len(sub_args) == 0:
            templateUsage()
            raise OstrichException("Invalid number of parameters")

        install_dir = None
        link = False
        registry_arg = None
        
        idx = 0
        while idx < len(sub_args):
            arg = sub_args[idx]
            if arg == "--directory":
                if idx + 1 < len(sub_args):
                    install_dir = sub_args[idx+1]
                    idx += 1
                else:
                    raise OstrichException("Missing directory for --directory option")
            elif arg == "--link":
                link = True
            elif not arg.startswith("-"):
                if not install_dir:
                    registry_arg = arg
            idx += 1
        
        if install_dir:
             if not os.path.isdir(install_dir):
                 raise OstrichException(f"{install_dir} does not exist or is not a directory")
             
             # Extract the template name from the directory path
             # Use abspath to correctly handle "." or paths ending with a slash
             name = os.path.basename(os.path.abspath(install_dir))
             logging.info(f"Installing template {name} from {install_dir}")
             
             installTemplateFromDir(name, install_dir, link)
        else:
            if not registry_arg:
                 templateUsage()
                 raise OstrichException("Invalid number of parameters (no registry or directory specified)")
            
            arg = registry_arg
            if "/" not in arg:
                  templateUsage()
                  raise OstrichException("Invalid template reference. Expected <registry>/<template>[:<version>]")

            parts = arg.split("/", 1)
            repo_name = parts[0]
            template_ref = parts[1]
            
            version = None
            if ":" in template_ref:
                template_name, version = template_ref.split(":", 1)
            else:
                template_name = template_ref
            
            registries = registry_op.load_registries()
            repo_url = None
            target_reg = None
            for reg in registries:
                if reg.get('name') == repo_name:
                    repo_url = reg.get('url')
                    target_reg = reg
                    break
            
            if not repo_url:
                logging.error(f"Registry '{repo_name}' not found in configuration.")
                logging.info("To add a registry, use: ost registry add <name> <url>")
                raise OstrichException(f"Registry '{repo_name}' not found")
            
            is_plain_http = repo_url.startswith("http://")
            if repo_url.startswith("http://"):
                oci_repo_url = "oci://" + repo_url[7:]
            elif repo_url.startswith("https://"):
                oci_repo_url = "oci://" + repo_url[8:]
            elif not repo_url.startswith("oci://"):
                oci_repo_url = "oci://" + repo_url
            else:
                oci_repo_url = repo_url

            with tempfile.TemporaryDirectory() as tmpdir:
                logging.info(f"Pulling template {template_name} from {oci_repo_url}")
                helm_args = ["pull", f"{oci_repo_url}/{template_name}", "-d", tmpdir]
                if version:
                    helm_args.extend(["--version", version])
                
                is_insecure = (target_reg and target_reg.get('insecure', False))
                if is_plain_http or is_insecure:
                    helm_args.append("--plain-http")
                
                skip_verify = params.skipTlsVerify or is_insecure
                if skip_verify:
                    helm_args.append("--insecure-skip-tls-verify")
                
                util.helm(*helm_args)
                
                files = os.listdir(tmpdir)
                if not files:
                    raise OstrichException("No files downloaded by helm pull")
                
                archive_path = os.path.join(tmpdir, files[0])
                with tarfile.open(archive_path, "r:gz") as tar:
                    if hasattr(tarfile, 'data_filter'):
                        tar.extractall(path=tmpdir, filter='data')
                    else:
                        # Fallback safe validation for Python < 3.12
                        def is_within_directory(directory, target):
                            abs_directory = os.path.abspath(directory)
                            abs_target = os.path.abspath(target)
                            prefix = os.path.commonpath([abs_directory, abs_target])
                            return prefix == abs_directory

                        for member in tar.getmembers():
                            member_path = os.path.join(tmpdir, member.name)
                            if not is_within_directory(tmpdir, member_path):
                                raise OstrichException(f"Security Error: Tar member {member.name} attempts path traversal outside target directory {tmpdir}")
                        tar.extractall(path=tmpdir)
                
                chart_dir = os.path.join(tmpdir, template_name)
                if not os.path.isdir(chart_dir):
                     raise OstrichException(f"Extracted directory {chart_dir} not found")

                source_template_dir = os.path.join(chart_dir, "template")
                if not os.path.isdir(source_template_dir):
                     raise OstrichException(f"Template directory ('template') not found in extracted archive at {chart_dir}")

                installTemplateFromDir(template_name, source_template_dir, source=repo_name)

    elif sub in ["delete", "rm"]:
        if len(args) < 2:
            templateUsage()
            raise OstrichException("Invalid number of parameters")
        name = args[1]

        try:
            target = util.getTemplatePath(name)
            if not target.startswith(util.extraTemplateRoot()):
                logging.warning(f"Template {name} is a builtin or test template and cannot be deleted")
                return
            
            template_id = os.path.basename(target)
            logging.info(f"Delete template {template_id}")

            if os.path.lexists(target):
                if os.path.islink(target):
                    os.unlink(target)
                else:
                    shutil.rmtree(target)
            else:
                logging.warning("Template does not exist")
        except OstrichException:
            logging.warning(f"Template {name} does not exist")

    elif sub == "package":
        package(params)

    elif sub == "test":
        if len(args) < 2:
            templateUsage()
            raise OstrichException("Invalid number of parameters")

        if args[1] == "info":
            testUsage()
        else:
            if args[1] == "all":
                start_dir = util.root()
            else:
                start_dir = util.getTemplatePath(args[1]) + "/_test"

            test_args = args[2:]
            testFunction = ""
            
            cleaned_args = []
            skip_next = False
            runner_modes = "ost,ostd"
            mode_selected = False
            
            for i in range(len(test_args)):
                if skip_next:
                    skip_next = False
                    continue
                
                if test_args[i] == "--test":
                    if i + 1 < len(test_args):
                        testFunction = test_args[i+1]
                        skip_next = True
                    else:
                        testUsage()
                        return
                elif test_args[i] == "--ost":
                    if mode_selected and runner_modes == "ostd":
                        runner_modes = "ost,ostd"
                    else:
                        runner_modes = "ost"
                        mode_selected = True
                elif test_args[i] == "--ostd":
                    if mode_selected and runner_modes == "ost":
                        runner_modes = "ost,ostd"
                    else:
                        runner_modes = "ostd"
                        mode_selected = True
                else:
                    cleaned_args.append(test_args[i])
            
            os.environ["OST_RUNNER_MODES"] = runner_modes
            test_args = cleaned_args

            if "ostd" in runner_modes:
                logging.info("Building local Docker image for testing (tag: unittest)...")
                build_script_abs = os.path.normpath(os.path.join(util.root(), "..", "docker", "ostrich-sdk", "build.sh"))
                build_script_dir = os.path.dirname(build_script_abs)
                build_script_name = os.path.basename(build_script_abs)
                capture = logging.root.level > logging.DEBUG
                res = run(["bash", build_script_name, "-n", "--skip-ssh", "unittest"], cwd=build_script_dir, capture_output=capture)
                if res.returncode != 0:
                    if capture:
                        logging.error(res.stderr.decode())
                    raise OstrichException("Failed to build local Docker image for testing")
                os.environ["OST_IMAGE_TAG"] = "unittest"

            if "--" in test_args:
                test_args.remove("--")
            
            extraPytestArgs = test_args

            if testFunction:
                start_dir += "/" + testFunction
            
            logging.info(f"Running test for template {args[1]}")
            logging.info(f"Test to run {start_dir}")

            testParams = [start_dir]
            testParams.extend(extraPytestArgs)

            if pytest.main(testParams) != 0:
                raise OstrichException("Test failed")

    elif sub == "publish":
        if len(args) < 3:
            templateUsage()
            raise OstrichException("Invalid number of parameters")
        
        folder = args[1]
        registry_name = args[2]
        
        registries = registry_op.load_registries()
        repo_url = None
        target_reg = None
        for reg in registries:
            if reg.get('name') == registry_name:
                repo_url = reg.get('url')
                target_reg = reg
                break
        
        if not repo_url:
            logging.error(f"Registry '{registry_name}' not found in configuration.")
            logging.info("To add a registry, use: ost registry add <name> <url>")
            raise OstrichException(f"Registry '{registry_name}' not found")

        if not os.path.exists(folder + "/template.yaml"):
            raise OstrichException(f"Template directory {folder} does not contain a template.yaml file")
        
        templateContent = util.safeLoad(folder + "/template.yaml")
        plugin_name = glom(templateContent, "name", default=None)
        version = glom(templateContent, "version", default="0.0")

        if plugin_name is None:
            raise OstrichException(f"Template file {folder}/template.yaml does not define a plugin name")

        with tempfile.TemporaryDirectory() as tmpdir:
            packageAux(folder, tmpdir, False)
            archive_name = f"{plugin_name}-{version}.tgz"
            archive_path = os.path.join(tmpdir, archive_name)
            
            if not os.path.exists(archive_path):
                files = os.listdir(tmpdir)
                if files:
                    archive_path = os.path.join(tmpdir, files[0])
                else:
                    raise OstrichException(f"Failed to generate package in {tmpdir}")

            is_plain_http = repo_url.startswith("http://")
            if repo_url.startswith("http://"):
                oci_repo_url = "oci://" + repo_url[7:]
            elif repo_url.startswith("https://"):
                oci_repo_url = "oci://" + repo_url[8:]
            elif not repo_url.startswith("oci://"):
                oci_repo_url = "oci://" + repo_url
            else:
                oci_repo_url = repo_url
            
            logging.info(f"Publishing {plugin_name} version {version} to {oci_repo_url}")
            try:
                helm_args = ["push", archive_path, oci_repo_url]
                is_insecure = (target_reg and target_reg.get('insecure', False))
                if is_plain_http or is_insecure:
                    helm_args.append("--plain-http")
                
                skip_verify = params.skipTlsVerify or is_insecure
                if skip_verify:
                    helm_args.append("--insecure-skip-tls-verify")
                util.helm(*helm_args)
            except OstrichException as e:
                if "unauthorized" in str(e).lower() or "authentication" in str(e).lower() or "401" in str(e).lower():
                    logging.error("Authentication failed during push.")
                    logging.info(f"Please login to the registry first using: ost registry login {registry_name}")
                raise

    elif sub == "search":
        registry_op.search(params)

    elif sub == "values":
        try:
            params.loadPluginConf()
        except BaseException as e:
            raise OstrichException(f"Error loading plugin configuration: {str(e)}")

        template_kind = params.getPluginConf("template.kind")
        templatePath = util.getTemplatePath(template_kind)

        configAll = util.getMergedConfig(templatePath, params.parsedPluginConfig, params)
        
        # Filter out only top-level internal SDK keys
        displayConfig = configAll.copy()
        displayConfig.pop('_ostrich', None)
        displayConfig.pop('params', None)
        
        print(yaml.dump(displayConfig, sort_keys=False))

    else:
        logging.error("Try \"ost template help\" to know how to use the template command")
        raise OstrichException(f"Unknown subcommand '{sub}'")