import logging
import os
import pytest
import src.test.sdk as sdk
import src.toolkit as toolkit

# Get the runner modes from the environment variable (provided by ost generator test)
# Default to "ost,ostd" to allow double run by default in CI or when run directly
runner_modes = os.environ.get("OST_RUNNER_MODES", "ost,ostd").split(",")

@pytest.mark.parametrize("runner_mode", runner_modes)
class TestUnitTestsRunners:

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
generator:
  kind: unit-tests
  runtime: docker
  runner:
    kind: container
    image: alpine
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

    def test_docker_display(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        sdk.createFile(tmp_path / "unit.txt", "dummy content")
        sdk.ost(["run","docker_display"],0,[
            "this is unit tests",
            "dummy content",
            "syntax with cmd key as string",
            "syntax with cmd key as list",
            "ID=alpine"
        ])

    def test_docker_image(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        sdk.ost(["run","docker_image"],0,[
            "ID=debian"
        ])

    def test_docker_nodefaultimage(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        sdk.ost(["run","docker_nodefaultimage"],0,[
            "ID=debian"
        ])

    def test_docker_noimage(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        sdk.ost(["run","docker_noimage"],1,[
            "No container image defined"
        ])

    def test_docker_env(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        
        logging.info("01: standard args")        
        # Test 1: Standard run with arguments
        # LOGLEVEL=20 (INFO default), DRYRUN=false
        sdk.ost(["run","docker_env","arg1","arg2"],0,[
            "^LOGLEVEL=20$",
            "^DRYRUN=false$",
            "^OPERATION=docker_env$",
            "^ARGC=2$",
            "^ARGV=arg1,arg2$",
            r"^ARGV_JSON=\[\"arg1\", \"arg2\"\]$"
        ],noDebug=True)

        logging.info("02: debug mode")
        # Test 2: Debug mode
        # LOGLEVEL=10 (DEBUG)
        # Note: sdk.ost adds --nologo. We add --debug.
        sdk.ost(["--debug","run","docker_env"],0,"^LOGLEVEL=10$")

        logging.info("03: dry run")
        # Test 3: Dry run
        # DRYRUN=true
        sdk.ost(["run","docker_env","--dry-run","--rm"],0,"^DRYRUN=true$")

        logging.info("04: explicit output dir")
        # Test 4: Explicit Output Dir
        output_dir = tmp_path / "custom_output"
        str_out = str(output_dir)
        sdk.ost(["-o", str_out,"run","docker_env","--rm"],0,f"^TEMPLATE_DIR={toolkit.toUnixPath(str_out)}$")

    def test_docker_vars(self,tmp_path):
        sdk.createEnv(tmp_path,self.ostrichPluginYaml)
        sdk.createFile(tmp_path / "unit.txt", "dummy content")
        sdk.ost(["run","docker_vars"],0)
        