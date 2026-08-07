import json
from jsonpath_ng.ext import parse
from kubernetes import config, client
import logging
import os
from pathlib import Path
import re
import requests
import selectors
import subprocess
import sys
import time
import yaml



def getSDKPath(relative_path):
    """
    Get the absolute path of a file/directory within the SDK, 
    matching the environment (host or ostd container).
    """
    if os.getenv("USE_OSTD", "false").lower() == "true":
        return os.path.normpath("/sdk/src/" + relative_path).replace("\\", "/")
    else:
        # Get the path on host
        # This file is in src/test/sdk.py, so ../ is src/
        script_dir = os.path.dirname(os.path.abspath(__file__))
        src_root = os.path.abspath(script_dir + "/../")
        return os.path.abspath(os.path.join(src_root, relative_path)).replace("\\", "/")


RESET_ALL='\033[0;m'
YELLOW='\033[38;5;11m'
GREY='\033[38;5;8m'
RED='\033[38;5;9m'
GREEN='\033[38;5;10m'
BLUE='\033[38;5;12m'
MAGENTA='\033[38;5;13m'
CYAN='\033[38;5;14m'

UNDER='\033[4m'


""" Print indented text """
def printIndent(lines: str):
  for line in lines.splitlines():
    if(len(line)>0):
      print("  "+line.rstrip("\r\n ")+"\r\n",end="",flush=True)
    

""" Display a message (sample helper function) """
def display():
    print("Sample helper function")


"""
sets a value in a yaml content.
Args:
    yamlContent: the yaml content as a dictionnary
    key: the key to set
    value: the value to set
    yamlValue: if True, the value is a yaml content (as string). In this case it is parsed as yaml
Returns:
    the updated yaml content as a dict
"""
def updateYamlDict(yamlContent: dict, key: str, value: str, yamlValue: bool=False) -> dict :

    keys = key.split('.')
    d = yamlContent

    # Create all intermediate dictionaries
    for k in keys[:-1]:
        if k not in d:
            d[k] = {}
        d = d[k]
    # Set the value
    if yamlValue:
        d[keys[-1]] = yaml.safe_load(value)
    else:
        d[keys[-1]] = value

    return yamlContent




"""
sets a value in a yaml content.
Args:
    yamlContent: the yaml content as a string
    key: the key to set
    value: the value to set
    yamlValue: if True, the value is a yaml content (as string). In this case it is parsed as yaml
Returns:
    the updated yaml content as a string
"""
def updateYaml(yamlContent, key, value, yamlValue=False):
    data = yaml.safe_load(yamlContent)

    updatedYaml = updateYamlDict(data, key, value, yamlValue)

    return yaml.dump(updatedYaml)


"""
sets a value in a yaml file
Args:
    yamlFile: the yaml file to update
    key: the key to set
    value: the value to set
    yamlValue: if True, the value is a yaml content (as string). In this case it is parsed as yaml
"""
def updateYamlFile(yamlFile, key, value, yamlValue=False):
    
    with open(yamlFile, 'r') as file:
      yamlContent = file.read()

    updatedYaml = updateYaml(yamlContent, key, value, yamlValue)

    with open(yamlFile, 'w') as file:
      file.write(updatedYaml)


"""
Checks the content of a string using a regex
Args:
    content: the content to check
    regex: the regex to check
"""
def checkContentRegex(content: str, regex: str):
  logging.info("Checking content for regex %s", regex)
  for line in content.splitlines():
    if(re.match(regex, line)):
      logging.info("Match: %s", line)
      return
  assert False, "Content does not match the regex: %s" % regex  
  #assert re.match(regex, content), "Content does not match the regex: %s" % regex



"""
Executes a command and checks the return code and the output
Args:
    cmd: the command to execute as an array
    expectedReturnCode: the expected return code
    outputContent: the expected content in the output as a regex
    noOutputContent: the content that should not be in the output as a regex
"""
def run(cmd: str, expectedReturnCode: int = None, outputContent: str = None, noOutputContent: str = None):
  logging.info("Executing command %s", cmd)


  if os.name == 'nt':
    p = subprocess.Popen(tabParams, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    
    if stdout:
        decoded = stdout.decode('utf-8', errors='replace')
        printIndent(decoded)
        result += decoded
    
    if stderr:
        decoded = stderr.decode('utf-8', errors='replace')
        printIndent(decoded)
        result += decoded
        
    return_code = p.returncode
  else:
    p = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    sel = selectors.DefaultSelector()
    sel.register(p.stdout, selectors.EVENT_READ)
    sel.register(p.stderr, selectors.EVENT_READ)

    result=""

    open_streams = 2
    print(YELLOW, flush=True)
    while open_streams > 0:
      for key, _ in sel.select():
        data = key.fileobj.read1().decode()
        if not data:
            sel.unregister(key.fileobj)
            open_streams -= 1
        else:
          if key.fileobj is p.stdout:
              printIndent(data)
              result += data
          else:
              printIndent(RED+data+YELLOW)
              result += data

    print(RESET_ALL, flush=True)

    p.wait()
    return_code = p.returncode

  logging.info("Return code: %s", return_code)
  if expectedReturnCode != None:
    assert p.returncode == expectedReturnCode, f"Command {str(cmd)} exit code should be {expectedReturnCode} but is {p.returncode}"

  if outputContent:
    logging.info("Checking for %s", outputContent)
    assert re.search(outputContent, result), "Output does not match regex: '%s'" % outputContent

  if noOutputContent:
    logging.info("Checking for %s", noOutputContent)
    assert not re.search(noOutputContent, result), "Output should not match regex: '%s'" % noOutputContent

  return result, p.returncode


""" 
Execute the ost command 
Args:
    params: the parameters to pass to the command
    expectedReturnCode: the expected return code
    outputContent: the expected content in the output
        If a list, each element is checked
        Else the content is checked as a whole
    noOutputContent: the content that should not be in the output
Returns: the output of the command + the return code as a tuple
"""
def ost(params=[], expectedReturnCode=0, outputContent=None, noOutputContent=None, noDebug=False):
  
  script_dir = os.path.dirname(os.path.abspath(__file__))
  
  # Check if we should use ostd (Docker) instead of ost (Python)
  use_ostd = os.getenv("USE_OSTD", "false").lower() == "true"
  
  if use_ostd:
    import platform
    system = platform.system().lower()
    if system == "linux":
        ostd_path = script_dir+"/../../../bin/linux/ostd"
    elif system == "darwin":
        ostd_path = script_dir+"/../../../bin/darwin/ostd"
    elif system == "windows":
        ostd_path = script_dir+"/../../../bin/windows/ostd.exe"
    else:
        raise Exception(f"Unsupported OS: {system}")
        
    tabParams=[ostd_path, "--nologo"]
    custom_tag = os.getenv("OST_IMAGE_TAG")
    if custom_tag:
      tabParams.extend(["--image", "ostrich-sdk", "--tag", custom_tag])
    # Pass environment variables starting with TEST_ or QUOTE_ to ostd
    for k, v in os.environ.items():
        if k.startswith("TEST_") or k.startswith("QUOTE_"):
            tabParams.extend(["-e", f"{k}={v}"])
  else:
    ost_path = os.path.normpath(os.path.join(script_dir, "..", "..", "ost"))
    tabParams=[sys.executable, ost_path, "--nologo"]

  if logging.root.level <= logging.DEBUG and not noDebug:
    tabParams.append("--debug")      

  tabParams.extend(params)

  logging.info("Executing command %s", " ".join(tabParams))
  result=""

  if os.name == 'nt':
    p = subprocess.Popen(tabParams, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    
    if stdout:
        decoded = stdout.decode('utf-8', errors='replace')
        printIndent(decoded)
        result += decoded.replace("\r", "")
    
    if stderr:
        decoded = stderr.decode('utf-8', errors='replace')
        printIndent(decoded)
        result += decoded.replace("\r","")

  else:
    p = subprocess.Popen(
        tabParams, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    sel = selectors.DefaultSelector()
    sel.register(p.stdout, selectors.EVENT_READ)
    sel.register(p.stderr, selectors.EVENT_READ)

    open_streams = 2
    print(CYAN, flush=True)
    while open_streams > 0:
      for key, _ in sel.select():
        data = key.fileobj.read1().decode()
        if not data:
            sel.unregister(key.fileobj)
            open_streams -= 1
        else:
          printIndent(data)
          result += data

    print(RESET_ALL, flush=True)

  p.wait()
  return_code = p.returncode

  logging.info("Return code: %s", return_code)

  assert return_code == expectedReturnCode, f"ost command exit code should be {expectedReturnCode} but is {return_code}"

  logging.debug("Result:----- \n%s\n-----:End Result", result)

  if outputContent:
    if isinstance(outputContent, list):
      for expected in outputContent:
        logging.info("Checking for: %s", expected)
        assert re.search(expected, result,re.MULTILINE), "File content does not contain: '%s'" % expected
    else:
      logging.info("Checking for: %s", outputContent)
      assert re.search(outputContent, result,re.MULTILINE), "File content does not contain: '%s'" % outputContent

  if noOutputContent:
    if isinstance(noOutputContent, list):
      for unexpected in noOutputContent:
        logging.info("Checking for NOT: %s", unexpected)
        assert not re.search(unexpected, result,re.MULTILINE), "File content should not contain: '%s'" % unexpected
    else:
      logging.info("Checking for NOT: %s", noOutputContent)
      assert not re.search(noOutputContent, result,re.MULTILINE), "File content should not contain: '%s'" % noOutputContent

  return result, return_code


"""
Extracts the Helm template from a dry-run output
Args:
    output: the output of the dry-run command
Returns:
    the Helm template as a dictionary. the key is the name of the object (metadata.name)
"""
def extractHelmTemplateFromDryRun(output: str) -> dict:
  inTemplate: bool=False
  ret: str=""

  for line in output.splitlines():
    if(inTemplate and "=== END TEMPLATE ===" not in line):
      ret+=line+"\n"
    else:
      if("=== TEMPLATE ===" in line):
        inTemplate=True
      elif("=== END TEMPLATE ===" in line):
        return parseYamlMultiDoc(ret)
  return {}


""" Create a temporary environment """
def createEnv(tmp_path, content=None):
  temp_file_path = tmp_path / "ostrich.yaml"
  logging.info("Created temporary file: %s", temp_file_path)
  os.chdir(tmp_path)
  if content:
    with open(temp_file_path, "w") as file:
        file.write(content)


""" 
Change the current directory to a sample application 
Args:
  location: the location of the calling file (use __file__)
  name: the name of the sample application
"""
def sampleEnv(location: str, name: str):
  os.chdir(getSampleAppPath(location)+ "/"+name)
  logging.info("Changed directory to %s", os.getcwd())


""" Create a file with a specific content """
def createFile(filePath, content):  
  with open(filePath, "w") as file:
      file.write(content)


""" Check the content of a file 
    Args:
        filePath: the path of the file to check
        expectedContent: the expected content as a regex or a list of regex
        unexpectedContent: the content that should not be in the file
        partial: if True, the expected content is a part of the file content
"""
def checkFileContent(filePath, expectedContent, unexpectedContent=None):
  logging.info("Checking file content %s for file %s", expectedContent, os.path.abspath(filePath))
  with open(filePath, "r") as file:
      content = file.read()
      logging.debug("File content: %s", content)
      if isinstance(expectedContent, list):
        for expected in expectedContent:
          assert re.search(expected, content,re.MULTILINE), "File content does not contain the expected content: %s" % expected
      else:
        assert re.search(expectedContent, content,re.MULTILINE), "File content does not contain the expected content: %s" % expectedContent

      if unexpectedContent:
        if isinstance(unexpectedContent, list):
          for unexpected in unexpectedContent:
            assert not re.search(unexpected, content,re.MULTILINE), "File content should not contain: '%s'" % unexpected
        else:
          assert not re.search(unexpectedContent, content,re.MULTILINE), "File content should not contain: '%s'" % unexpectedContent


""" Display the content of a file """
def cat(filePath: str):
  with open(filePath, "r", encoding="utf-8") as file:
      content = file.read()
      logging.info("Content of %s (len=%d):", os.path.abspath(filePath), len(content))
      logging.debug("Raw content: %s", repr(content))
      printIndent(GREEN+content+RESET_ALL)
      print("")


def catFilePath(filePath: Path):
  cat(str(filePath))  


""" Get the sample configuration """
def getSampleConfig(file: str):
  with open(os.path.dirname(file)+"/../_doc/ostrich.yaml", "r") as file:
    return file.read()


""" Get the path to the sample applications (for integration test) """
def getSampleAppPath(file: str):
  return os.path.normpath(os.path.dirname(file)+"/../_samples")


""" Get the template configuration """
def getTemplateConfig(file: str):
  with open(os.path.dirname(file)+"/../config.yaml", "r") as file:
    return yaml.safe_load(file.read())


""" Execute a helm template on a specific file 
    Returns the parsed YAML content as a dictionary
    Args:
        folder: the folder where the helm chart is located
        file: the file to template
        namespace: the namespace to set
        values: the values to pass to the helm template as ["key1=value1", "key2=value2"]
        valueFiles: the value files to pass to the helm template as ["file1.yaml", "file2.yaml"]
        helmOptions: the additional options to pass to the helm template as ["--set","key1=value1"]
        aslist: if True, the result is a list of dictionaries.
                If False, the result is a single dictionary. Function will fail if the result is not a single YAML document
        display: if True, the output is displayed 
"""
def helmTemplate(folder: str, file: str="", namespace: str="", values=[], valueFiles=[], helmOptions=[], aslist=False,check=True,display=True) -> any :
  result: str = helmTemplateAsString(folder, file, namespace, values, valueFiles, helmOptions, check, display)
  reslist=list(yaml.safe_load_all(result))

  logging.info("Found %s objects", len(reslist))

  if(aslist):
    return reslist
  else:
    if(len(reslist)==1):
      return reslist[0]
    else:
      assert False, "The result is not a single YAML document"


""" Execute a helm template on a specific file 
    Returns the parsed YAML content as a raw string
    Args:
        folder: the folder where the helm chart is located
        file: the file to template
        namespace: the namespace to set
        values: the values to pass to the helm template as ["key1=value1", "key2=value2"]
        valueFiles: the value files to pass to the helm template as ["file1.yaml", "file2.yaml"]
        helmOptions: the additional options to pass to the helm template as ["--set","key1=value1"]
        display: if True, the output is displayed 
"""
def helmTemplateAsString(folder: str, file: str="", namespace: str="", values=[], valueFiles=[], helmOptions=[],check=True, display=True) -> str :

  if(len(file)==0):
    logging.info("Helm template folder %s", folder)
    tabParams=["helm", "template"]
  else:
    logging.info("Helm template folder %s for file %s", folder, file)
    tabParams=["helm", "template", "-s", file]

  tabParams.extend(helmOptions)

  for value in values:
    tabParams.append("--set")
    tabParams.append(value)

  for valueFile in valueFiles:
    tabParams.append("-f")
    tabParams.append(valueFile)

  if len(namespace) > 0:
    tabParams.append("--namespace")
    tabParams.append(namespace)
    tabParams.append("--set")
    tabParams.append("global.namespace="+namespace)

  tabParams.append(folder)
  logging.info("Executing command %s", " ".join(tabParams))
  result=""
  
  p = subprocess.Popen(
      tabParams, stdout=subprocess.PIPE, stderr=subprocess.PIPE
  )

  if os.name == 'nt':
    out, err = p.communicate()
    if display:
      if out:
        printIndent(out.decode(errors='replace'))
      if err:
        printIndent(RED + err.decode(errors='replace') + YELLOW)
    result = out.decode(errors='replace')
    if display:
      print(RESET_ALL,flush=True)
  else:
    sel = selectors.DefaultSelector()
    sel.register(p.stdout, selectors.EVENT_READ)
    sel.register(p.stderr, selectors.EVENT_READ)

    toRead=True

    if display:
      print(YELLOW,flush=True)
    while toRead:
      for key, _ in sel.select():
        data = key.fileobj.read1().decode()
        if not data:
            toRead=False
        else:
          if key.fileobj is p.stdout:
              if display:
                printIndent(data)
              result += data
          else:
              if display:
                printIndent(RED+data+YELLOW)

    if display:
      print(RESET_ALL,flush=True)


    p.wait()
  if check:
    assert p.returncode == 0, "Helm template command failed"

  return result


""" 
Check the content of a dictionary
Args:
  data: the dictionary to check
  expr: the expression to check as a JSON path
  expected: the expected value
  regex: if True, the expected value is a regex
"""
def checkEntry(data: dict, expr: str, expected: str, regex: bool = False):
  logging.info('Checking that expression "%s" %s "%s"', expr, ("~" if regex else "="), expected)

  jsonpath_expr = parse(expr)
  results = [match.value for match in jsonpath_expr.find(data)]

  assert len(results) > 0, f"Expression {expr} returns no result"

  logging.info("Found %s match%s", len(results), "es" if len(results) > 1 else "")
  logging.info("Results: %s", results)

  found=False
  for result in results:
    if(regex):
      if(re.match(expected, str(result))):
        found=True
        break
    else:
      if str(result) == expected:
        found=True
        break

  assert found, f"Expression {expr} does not match. Expected: {expected} but was {results}"


""" 
Get the content of a dictionary
Args:
  data: the dictionary to check
  expr: the expression to check as a JSON path
"""
def getEntry(data: dict, expr: str):
  jsonpath_expr = parse(expr)
  ret=[match.value for match in jsonpath_expr.find(data)]

  assert len(ret) <= 1, f"Expression {expr} returns multiple entries. Expected 1 but was {len(ret)}. Use getEntries instead"
  if(len(ret)==0):
    return None

  return [match.value for match in jsonpath_expr.find(data)][0]


""" 
Get the content of a dictionary
Args:
  data: the dictionary to check
  expr: the expression to check as a JSON path
"""
def getEntries(data: dict, expr: str):
  jsonpath_expr = parse(expr)
  ret=[match.value for match in jsonpath_expr.find(data)]
  return [match.value for match in jsonpath_expr.find(data)]


""" 
Loads a JSON file and returns the content as a dictionary
"""
def loadJson(filePath: str):
  with open(filePath, "r") as file:
    return json.load(file)

""" 
Loads a YAML file and returns the content as a dictionary
"""
def loadYaml(filePath: str):
  with open(filePath, "r") as file:
    return yaml.safe_load(file)

""" 
Parse a YAML string and returns the content as a dictionary
"""
def parseYaml(content: str):
  return yaml.safe_load(content)

"""
Parse a YAML string with multiple documents and returns the content as a list of dictionaries
"""
def parseYamlMultiDoc(content: str) -> dict :
  l=list(yaml.safe_load_all(content))
  ret: dict={}

  for i in range(len(l)):
    if l[i] and l[i]['metadata'] and l[i]['metadata']['name']:
      assert "kind" in l[i], f"kind not found in document {i}"
      name=l[i]['metadata']['name']
      kind=l[i]['kind']
      ret[name]=l[i]
      assert kind+"/"+name not in ret, f"Duplicate key {kind}/{name}"
      ret[kind+"/"+name]=l[i]
  return ret

"""
Get an environment variable
Args:
    name: the name of the environment variable
    default: the default value if the environment variable is not set
"""
def getenv(name: str, default: str = None):
  ret=os.getenv(name)
  if(ret==None and default==None):
    assert False, f"Environment variable {name} is not set"
  
  if(ret==None):
    return default
  else:
    return ret


"""
Execute a HTTP GET request
Args:
    url: the URL to request
    expectedReturnCode: the expected return code
"""
def httpGet(url: str, expectedReturnCode: int = None, showOutput=False, retries=0):

  logging.info(f"Executing HTTP GET request to {url} with {retries} retries")
  attempts=retries+1
  success: bool=False

  for i in range(attempts):
    response = requests.get(url,verify=False)
    if showOutput:
      print(GREY,flush=True)  
      logging.info(f"Response from {url}: {response.text}")
      print(RESET_ALL,flush=True)  

    logging.info("Response code: %d", response.status_code)

    if expectedReturnCode == None:
       break
    else:
      if response.status_code == expectedReturnCode:
        success=True
        break
      else:
        logging.error(f"Expected status code {expectedReturnCode} but got {response.status_code}, retrying ({i})...")
        time.sleep(1)

  assert success, f"Expected status code {expectedReturnCode} but got {response.status_code} after {attempts} attempts"


"""
Deletes a namespace and wait for the deletion to be effective
"""
def deleteNs(namespace: str):
    # Load kube config
    config.load_kube_config()

    # Create a Kubernetes API client
    v1 = client.CoreV1Api()

    # Delete the namespace
    try:
        v1.delete_namespace(namespace,async_req=False)
        logging.info(f"Namespace {namespace} deleted successfully.")
    except client.exceptions.ApiException as e:
        logging.error(f"Failed to delete namespace {namespace}: {e}")

    # Wait for the namespace to be actually deleted
    logging.info(f"Waiting for namespace {namespace} to be deleted...")
    while True:
        try:
            v1.read_namespace(namespace)
            print(".", end="", flush=True)
            time.sleep(2)
        except client.exceptions.ApiException as e:
            if e.status == 404:
                print("\n", end="", flush=True)
                logging.info(f"Namespace {namespace} deleted successfully.")
                break
            else:
                logging.error(f"Error while waiting for namespace {namespace} to be deleted: {e}")
                raise


"""
Gets a secret
"""
def getSecret(namespace: str, name: str) -> client.V1Secret:
    # Load kube config
    config.load_kube_config()

    # Create a Kubernetes API client
    v1 = client.CoreV1Api()

    try:
      secret = v1.read_namespaced_secret(name, namespace)
      logging.info(f"Secret {name} retrieved successfully.")
      return secret
    except client.exceptions.ApiException as e:
      logging.error(f"Failed to get secret {name} in namespace {namespace}: {e}")
      raise

