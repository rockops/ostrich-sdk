import logging
import os
import pytest
import src.test.sdk as sdk
import src.util as util

# Get the runner modes from the environment variable (provided by ost template test)
# Default to "ost,ostd" to allow double run by default in CI or when run directly
runner_modes = os.environ.get("OST_RUNNER_MODES", "ost,ostd").split(",")

@pytest.mark.parametrize("runner_mode", runner_modes)
class TestUnitTests:

    @pytest.fixture(autouse=True)
    def set_runner_mode(self, runner_mode):
        os.environ["USE_OSTD"] = "true" if runner_mode == "ostd" else "false"
        yield
        if "USE_OSTD" in os.environ:
            del os.environ["USE_OSTD"]


    ostrichPluginYaml = """
plugin:
  name: unit
  version: 0.0.1
  business_name: Unit Test
template:
  kind: unit-tests
  params:
    message: "Hello World"
    folder: "folder"
    valTrue: true
    valFalse: false
    valInt: 123
    valString: string
    sub:
      valSub: "sub"
    dotnet:
      sln: unittest.sln
    input:
      src: "src"
      bin: "bin"
"""


    ostrichPluginYamlNoSubKey = """
plugin:
  name: unit
  version: 0.0.1
  business_name: Unit Test
template:
  kind: unit-tests
  params:
    message: "Hello World"
    folder: "folder"
    valTrue: true
    valFalse: false
    valInt: 123
    valString: string
"""


    ostrichPluginYamlRaise = """
plugin:
  name: unit
  version: 0.0.1
  business_name: Unit Test
template:
  kind: unit-tests
  params:
    message: "Hello World"
    folder: "folder"
    valTrue: true
    valFalse: false
    valInt: 123
    valString: string
    sub:
      valSub: "sub"    
    raise: "Hello World Unit Test"
"""


    def setup_module(module):
        """setup any state specific to the execution of the given module."""


    def teardown_module(module):
        """teardown any state that was previously setup with a setup_module
        method.
        """

    def setup_method(self, method):
        """setup any state tied to the execution of the given method in a
        class. setup_method is invoked for every test method of a class.
        """
        mode = os.environ.get('USE_OSTD', 'false')
        print(f"\n{sdk.RED}{sdk.UNDER}------------ {method.__name__} (mode: {mode}) ------------{sdk.RESET_ALL}",flush=True)

    def teardown_method(self, method):
        """
        teardown any state that was previously setup with a setup_method
        """

    """
    Checks that the template command is working correctly.
    """
    def test_templateAlreadyExist(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        sdk.ost(["template","--rm"],0)
        # Should fail because the folder already exists
        sdk.ost(["template"],1)


    """
    Checks that the template command is working correctly.
    """
    def test_template(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        sdk.ost(["template","--rm"])
        with open("unit/output.txt", "w") as file:
            file.write("Hello World")
        sdk.ost(["template","--rm"])
        # Files added after first call should be deleted
        assert not os.path.exists("unit/output.txt"), "output.txt should not exist"
        # test folder should be present
        assert os.path.exists("unit/test"), "test folder should exist"
        # _test folder should not be in the template
        assert not os.path.exists("unit/_test"), "_test folder should not exist"
        # _doc folder should not be in the template
        assert not os.path.exists("unit/_doc"), "_doc folder should not exist"

    """
    Checks that the template command is working correctly with --force argument
    """
    def test_templateForce(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        sdk.ost(["template","--rm"])
        with open("unit/output.txt", "w") as file:
            file.write("Hello World")

        # With --force, the dorectory is kept, the content is overwritten
        sdk.ost(["template","--force"])
        sdk.checkFileContent("unit/output.txt","^Hello World$")

    """
    Check that a simple variable is properly replaced
    """
    def test_variable(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        sdk.ost(["template","--rm"])
        sdk.checkFileContent("unit/unit/variable.txt","^Hello World$")


    """
    Check the default filters from the src/util.py library
    """
    def test_filters(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        sdk.ost(["template","--rm"])

        filtersPath="unit/unit/filters.txt"

        sdk.cat(filtersPath)

        # here => prefix the path with the location of the source folder
        sdk.checkFileContent(filtersPath, "^here:"+util.toUnixPath(tmp_path / "folder")+"$")
        # noslash => remove the trailing slash if any 
        sdk.checkFileContent(filtersPath, "^noslash1:folder_noslash$")
        sdk.checkFileContent(filtersPath, "^noslash2:folder_slash$")
        # md5hash => compute the md5 hash of the content with 'hashlib.md5(str.encode('utf-8')).hexdigest()'
        sdk.checkFileContent(filtersPath, "^md5hash:16802231b09f155b7a42a5dcaba33a74$")
        # fromTemplate => appends the location of the current template
        # To check, the template location is derived from the location of this current file
        # fromTemplate => appends the location of the template
        sdk.checkFileContent(filtersPath, "^fromTemplate:" + sdk.getSDKPath("test-templates/unit-tests/folder")+"$")
        # fromTemplates => appends the location of the global template folder
        sdk.checkFileContent(filtersPath, "^fromTemplates:" + sdk.getSDKPath("templates/folder")+"$")
        # fromJob => appends the location of the current job
        sdk.checkFileContent(filtersPath, "^fromJob:" + sdk.getSDKPath("test-templates/unit-tests/unit/folder")+"$")
        # nosnapshot => remove the '-xxx' suffix from the snapshot name if any 
        sdk.checkFileContent(filtersPath, "^nosnapshot1:1.2.3$")
        sdk.checkFileContent(filtersPath, "^nosnapshot2:3.4.5$")
        # basename => return the last part of the path
        sdk.checkFileContent(filtersPath, "^basename:file.txt$")
        # dirname => return the path without the last part
        sdk.checkFileContent(filtersPath, "^dirname:folder/sub$")
        # the bool filter it used to convert a boolean to a string, removing the uppercase
        # (in Python, bools are True and False, the filter turns them to true and false respectively,
        # the other data types repain unchanged)
        sdk.checkFileContent(filtersPath, "^bool1:True,true$")
        sdk.checkFileContent(filtersPath, "^bool2:False,false$")
        sdk.checkFileContent(filtersPath, "^bool3:123,123$")
        sdk.checkFileContent(filtersPath, "^bool4:string,string$")

        sdk.checkFileContent(filtersPath, "^input1:"+util.toUnixPath(tmp_path / "src/java")+"$")
        sdk.checkFileContent(filtersPath, "^input2:"+util.toUnixPath(tmp_path / "src")+"$")
        sdk.checkFileContent(filtersPath, "^input3:"+util.toUnixPath(tmp_path / "bin")+"$")


    """ 
    Check the default globals from the src/util.py library
    """
    def test_globals(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        sdk.ost(["template","--rm"])

        globalsPath="unit/unit/globals.txt"

        sdk.cat(globalsPath)
        # get => get a value from the a key
        sdk.checkFileContent(globalsPath, "^get:sub$")
        # _ => get safe. If the key does not exist, return an empty string
        sdk.checkFileContent(globalsPath, "^_:sub$")
        sdk.checkFileContent(globalsPath, "^_2:$")


    """ get a value on non existing key """
    def test_globals_keyNoExist(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYamlNoSubKey)
        sdk.ost(["template","--rm"],1,"Key template.params.sub not defined")


    """ raise an error in the template """
    def test_globals_raise(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYamlRaise)
        sdk.ost(["template","--rm"],1,"Hello World Unit Test")


    """ test isDebugEnabled helper """
    def test_globals_isDebugEnabled(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        sdk.ost(["template","--rm"])
        globalsPath="unit/unit/globals.txt"

        sdk.cat(globalsPath)
        # isDebugEnabled => return true if the log level is DEBUG
        sdk.checkFileContent(globalsPath, f"^debug:{logging.DEBUG >= logging.root.level}$")

    """ test the pretemplate mechanism """
    def test_pretemplate(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        sdk.ost(["template","--rm"])
        pretemplatePath="unit/unit/pretemplate.txt"

        sdk.cat(pretemplatePath)
        # the global pretemplate install the gunit filter and global. Test that they are available
        sdk.checkFileContent(pretemplatePath, "^filter:HelloWorld/unit$")
        sdk.checkFileContent(pretemplatePath, "^global:WorldHello/unit$")
        sdk.checkFileContent(pretemplatePath, "^local_filter:HelloWorld/unitlocal$")
        sdk.checkFileContent(pretemplatePath, "^local_global:WorldHello/unitlocal$")

    """ test the execution of a task with dependencies """
    def test_run(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        # Check that the task + the dependencies are executed
        sdk.ost(["run","display"],0,["dep1 plugin unit","dep2 plugin unit"])
        # Check that the task is executed but the dependencies are skipped
        sdk.ost(["run","display","--skip","dep1"],0,"dep2 plugin unit","dep1 plugin unit")
        # Check that the task is executed but the dependencies are skipped
        sdk.ost(["run","display","--skip","dep1","--skip","dep2"],0,["Skipping dependency dep1","Skipping dependency dep2"],["dep2 plugin unit","dep1 plugin unit"])
        # Check that the task is executed but the dependencies are skipped
        sdk.ost(["run","display","--nodeps"],0,[],["dep2 plugin unit","dep1 plugin unit"])

    """ test the execution of a task with parameters """
    def test_runParams(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        # Check that the task + the dependencies are executed
        sdk.ost(["run","checkparam","--skip","dep1","--","--param1","--param2"],0,"--param1,--param2")


    """ test the execution of a task with parameters """
    def test_runAltConf(self,tmp_path):
        sdk.createEnv(tmp_path)
        sdk.createFile(tmp_path / "ostrich2.yaml",self.ostrichPluginYaml)
        # Check that the task + the dependencies are executed
        sdk.ost(["-f","ostrich2.yaml","run","display"],0,"Dummy step for plugin unit")


    """ test the execution using an out directory """
    def test_runOut(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        # Check that the task + the dependencies are executed
        sdk.ost(["-o","tmpfolder","run","display"],0)
        logging.info("Check that the tmpfolder still exists")
        assert os.path.exists("tmpfolder")


    """ test the colormap """
    def test_colors(self,tmp_path):
        reset = '\033[00m'
        for i in range(256):
            fg = '\033[38;5;' + str(i) + 'm'
            bg = '\033[48;5;' + str(i) + 'm'
            print(bg + reset, end='')
            print(fg + '{:03d}'.format(i) + reset, end=' ')
            if i <= 15 and (i + 1) % 8 == 0:
                print()
            if i > 15 and (i - 15) % 6 == 0:
                print()

    """ test the command line attribute: no attribute """
    def test_cmdlineEmpty(self,tmp_path):
        sdk.ost([],1,"^Usage:")


    """ test the command line attribute """
    def test_cmdlineHelp(self,tmp_path):
        sdk.ost(["--help","--debug","--kubeconfig","config"],0,"^Usage:")


    """ test version display """
    def test_cmdlineVersion(self,tmp_path):
        sdk.ost(["--version"],0,"^ost")


    """ test bad argument """
    def test_cmdlineBadArg(self,tmp_path):
        sdk.ost(["--badarg"],1,"^ERROR")


    """ test check config: ath template config """
    def test_cmdlineConfig(self,tmp_path):
        conf,_=sdk.ost(["template","config","unit-tests"],0,noDebug=True)
        confYaml=sdk.parseYaml(conf)
        sdk.checkEntry(confYaml,"plugin.name","unit")

    """ test the execution of a task with dependencies """
    def test_runError(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        # Check that the task + the dependencies are executed
        sdk.ost(["run""error"],1)
   
    """ test the execution of a task with dependencies """
    def test_runCalledProcessError(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        # Check that the task + the dependencies are executed
        sdk.ost(["run","calledProcessError"],1)

    """ exec with an unexisting ostrich.yaml """
    def test_runConfNoExist(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        sdk.ost(["-f","not_exist.yaml","run","display"],1)
   

    """ exec with bas YAML file as plugin conf """
    def test_runBadConfig(self,tmp_path):
        ostrichPluginYamlBad = """
dashboard "Variables example":
  - h1 text: Variables Example
  -       dropdown my_var=pie:
    - {"value": pie, "text": "Pie chart"}
    - {"value": bar, "text": "Bar chart"}
   p text: "Selected chart type: ${my_var}"
"""
        sdk.createEnv(tmp_path,ostrichPluginYamlBad)
        sdk.ost(["run""display"],1)

    """ test usage """
    def test_cmdlineTestBadArg(self,tmp_path):
        sdk.ost(["template","test"],1,"^Usage")
        sdk.ost(["template","test","info"],0,"ost template test")

    """ test decription """
    def test_description(self,tmp_path):
        sdk.ost(["template","describe","unit-tests"],0,["Description in markdown"])

    """ test decription with no parameter """
    def test_descriptionBad(self,tmp_path):
        sdk.ost(["template","describe"],1,["Invalid number of parameters"])


    """ test list """
    def test_templateList(self,tmp_path):
        sdk.ost(["template","list"],0,["Available plugins"])

    """ test install bad parameters """
    def test_templateInstall(self,tmp_path):
        sdk.ost(["template","install"],1,["Invalid number of parameters"])


    """ test config: bad command line"""
    def test_configBadCommandLine(self,tmp_path):
        sdk.ost(["config"],1,"^Usage:")
        sdk.ost(["config","set"],1,"Invalid number of parameters")
        sdk.ost(["config","unset"],1,"Invalid number of parameters")
        sdk.ost(["config","login"],1,"Invalid number of parameters")
        sdk.ost(["config","token"],1,"Invalid number of parameters")
        sdk.ost(["config","logout"],1,"Invalid number of parameters")


    """ test config """
    def test_config(self,tmp_path):
        sdk.ost(["config","set","unit","value"],0,"Configuration updated for key unit")
        sdk.ost(["config","list"],0,"unit=value")
        sdk.ost(["config","get","unit"],0,"^value$")
        sdk.ost(["config","unset","unit"],0,"Configuration key unit deleted")
        sdk.ost(["config","get","unit"],1,"Key unit not found")

    """ test config login for a Helm repo """
    def test_configHelm(self,tmp_path):
        sdk.ost(["config","login","helm","http://unit-registry.com","myuser","mypassword"],0,"Credential registered for helm server http://unit-registry.com")
        sdk.ost(["config","login","list"],0,"^helm: http://unit-registry.com=myuser:\\*\\*\\*$")
        sdk.ost(["config","login","helm","list"],0,"^helm: http://unit-registry.com=myuser:\\*\\*\\*$")
        sdk.ost(["config","logout","helm","http://unit-registry.com"],0,"Credential deleted for helm server http://unit-registry.com")
        sdk.ost(["config","login","list"],0,[],"^helm: http://unit-registry.com=myuser:\\*\\*\\*$")

    """ test config login for a Sonarqube (token based) """
    def test_configSonar(self,tmp_path):
        sdk.ost(["config","token","sonar","http://sonar-unit.com","mytoken"],0,"Token registered for sonar server http://sonar-unit.com")
        sdk.ost(["config","login","list"],0,"^sonar: http://sonar-unit.com=\\*\\*\\*$")
        sdk.ost(["config","token","list"],0,"^sonar: http://sonar-unit.com=\\*\\*\\*$")
        sdk.ost(["config","login","sonar","list"],0,"^sonar: http://sonar-unit.com=\\*\\*\\*$")
        sdk.ost(["config","logout","sonar","http://sonar-unit.com"],0,"Credential deleted for sonar server http://sonar-unit.com")
        sdk.ost(["config","login","list"],0,[],"^sonar: http://sonar-unit.com=\\*\\*\\*$")

    """
    Checks that the "test" operation works
    """
    def test_testOperation(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        sdk.ost(["run","test"],0,"^Test task$")


    """
    Checks env substitution
    """
    def test_testEnvSubstitution(self,tmp_path):
        ostrichPluginYamlExpand = """
plugin:
    name: unit
    version: 0.0.1
    business_name: Unit Test
template:
    kind: unit-tests
    params:
        folder: "folder"
        message: "$TEST_VALUE"
        expand:
            v1: ${TEST_VALUE}
            v2: ${TEST_VALUE_NO_EXIST:-"TEST_VALUE_NO_EXIST_DEFAULT"}
            v3: ${TEST_VALUE_NO_EXIST:-$TEST_VALUE}
            v4: ${TEST_VALUE:-$TEST_VALUE2}
            v5: [[ env.TEST_VALUE_NO_EXIST or env.TEST_VALUE_NO_EXIST or "TEST_VALUE_NO_EXIST_DEFAULT" ]]
            v6: [[ env.TEST_VALUE_NO_EXIST or env.TEST_VALUE_NO_EXIST or env.TEST_VALUE ]]
            v7: [[ env.TEST_VALUE_NO_EXIST or env.TEST_VALUE or "It should not be this value" ]]
            v8: [[ env.TEST_VALUE or env.TEST_VALUE_NO_EXIST or "It should not be this value" ]]
            v9: [[ env.TEST_VALUE or env.TEST_VALUE_NO_EXIST or 'It should not be this value' ]]
            v10: ${TEST_VALUE_NO_EXIST:-'TEST_VALUE_NO_EXIST_DEFAULT'}
            v11: ${TEST_VALUE_NO_EXIST:-'Value with "quotes"'}
            v12: '${TEST_VALUE_NO_EXIST:-Value with \"double quotes\"}'
            v13: 'No substitution but \"quoted\"'
            v14: "No substitution but 'quoted' or $TEST_VALUE"
            v15: ${TEST_VALUE_NO_EXIST:-"Value with \'quotes\'"}
            v16: ${QUOTE_VALUE}
        sub:
        valSub: "sub"
        input:
            src: "src"
            bin: "bin"
"""
        sdk.createEnv(tmp_path,ostrichPluginYamlExpand)

        logging.info("ostrich.yaml")
        sdk.cat("ostrich.yaml")

        os.environ["TEST_VALUE"]="test value"
        os.environ["TEST_VALUE2"]="test value2"
        os.environ["QUOTE_VALUE"]="a value with \"quotes\""

        sdk.ost(["template","--rm"],0)
        sdk.cat("unit/unit/expand.txt")

        sdk.checkFileContent("unit/unit/expand.txt",[
            "^01:test value$",
            "^02:TEST_VALUE_NO_EXIST_DEFAULT$",
            "^03:test value$",
            "^04:test value$",
            "^05:TEST_VALUE_NO_EXIST_DEFAULT$",
            "^06:test value$",
            "^07:test value$",
            "^08:test value$",
            "^09:test value$",
            "^10:TEST_VALUE_NO_EXIST_DEFAULT$",
            '^11:Value with "quotes"$',
            '^12:Value with "double quotes"$',
            '^13:No substitution but "quoted"$',
            "^14:No substitution but 'quoted' or test value$",
            "^15:Value with 'quotes'$",
            '^16:a value with "quotes"$'])

    # Test version check, with values equals the limit
    def test_versionsEqual(self,tmp_path):

        updatedYaml = sdk.updateYaml(self.ostrichPluginYaml,"template.params.minVersion","1.1.0")
        updatedYaml = sdk.updateYaml(updatedYaml,"template.params.maxVersion","1.2.0")

        sdk.createEnv(tmp_path,updatedYaml)
        sdk.ost(["run","version"],0,["minVersion: 1.1.0 >= 1.1.0, maxVersion: 1.2.0 <= 1.2.0"])


    # Test version check, with values equals the limit, with DEV version
    def test_versionsEqualDev(self,tmp_path):

        updatedYaml = sdk.updateYaml(self.ostrichPluginYaml,"template.params.minVersion","1.1.1-test")
        updatedYaml = sdk.updateYaml(updatedYaml,"template.params.maxVersion","1.2.0-test")

        sdk.createEnv(tmp_path,updatedYaml)
        sdk.ost(["run","version"],0,["minVersion: 1.1.1-test >= 1.1.0, maxVersion: 1.2.0-test <= 1.2.0"])


    # Test version check, with values above the limit (but correct)
    def test_versionsMoreLess(self,tmp_path):

        updatedYaml = sdk.updateYaml(self.ostrichPluginYaml,"template.params.minVersion","1.1.1")
        updatedYaml = sdk.updateYaml(updatedYaml,"template.params.maxVersion","1.1.0")

        sdk.createEnv(tmp_path,updatedYaml)
        sdk.ost(["run","version"],0,["minVersion: 1.1.1 >= 1.1.0, maxVersion: 1.1.0 <= 1.2.0"])


    # Test version check, with values incorrect minVersion
    def test_versionsBadMin(self,tmp_path):

        updatedYaml = sdk.updateYaml(self.ostrichPluginYaml,"template.params.minVersion","1.0.0")
        updatedYaml = sdk.updateYaml(updatedYaml,"template.params.maxVersion","1.1.0")

        sdk.createEnv(tmp_path,updatedYaml)
        sdk.ost(["run","version"],1,["Version 1.0.0 defined in template.params.minVersion must be greater than 1.1.0"])


    # Test version check, with values incorrect minVersion
    def test_versionsBadMax(self,tmp_path):

        updatedYaml = sdk.updateYaml(self.ostrichPluginYaml,"template.params.minVersion","1.1.0")
        updatedYaml = sdk.updateYaml(updatedYaml,"template.params.maxVersion","2.0.0")

        sdk.createEnv(tmp_path,updatedYaml)
        sdk.ost(["run","version"],1,["Version 2.0.0 defined in template.params.maxVersion must be lower than 1.2.0"])
