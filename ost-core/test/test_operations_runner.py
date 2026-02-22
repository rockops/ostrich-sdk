import pytest
import os
import json
from unittest.mock import MagicMock, patch, ANY
import yaml
import logging
from src import engine, toolkit
from src.exceptions import OstrichError

class MockParams:
    def __init__(self):
        self.tmpdir = "/tmp/test"
        self.loglevel = logging.INFO
        self.dryRun = False
        self.operationParams = ["param1", "param2"]
        self.parsedPluginConfig = {}
        self.noDeps = False
        self.skip = []
        self.executedTasks = []
        # Default runtime
        self._plugin_conf = {"generator.runtime": "docker"}

    def getPluginConf(self, key, default=None):
        return self._plugin_conf.get(key, default)

@pytest.fixture
def params():
    return MockParams()

@pytest.fixture
def mock_util_funcs():
    with patch("src.toolkit.safeLoad") as mock_load, \
         patch("src.toolkit.getLocation") as mock_loc:
        mock_loc.return_value = "/current/location"
        yield mock_load, mock_loc

@pytest.fixture
def mock_run():
    with patch("src.engine.run") as mock_r:
        # Default behavior: success (returncode 0), stdout="Docker version..."
        mock_r.return_value = MagicMock(returncode=0, stdout="Docker version 20.10.0")
        yield mock_r

@pytest.fixture
def mock_files():
    with patch("os.path.isfile") as mock_isfile, \
         patch("os.path.abspath") as mock_abspath, \
         patch("os.getuid") as mock_uid, \
         patch("os.getgid") as mock_gid:
        
        mock_isfile.return_value = True
        mock_abspath.side_effect = lambda x: x # Identity for valid dict keys if needed, or simple string
        mock_uid.return_value = 1000
        mock_gid.return_value = 1000
        yield mock_isfile

def test_container_simple_command(params, mock_util_funcs, mock_run, mock_files):
    mock_load, _ = mock_util_funcs
    operation = "op1"
    
    # Mock command file content
    mock_load.return_value = {
        "commands": ["echo hello"],
        "runner": {"image": "busybox"}
    }

    engine.container(operation, params)

    # Verify run call
    # calls[0] is verification (docker -v)
    # calls[1] is execution
    assert mock_run.call_count >= 2
    
    # Check execution call args
    args = mock_run.call_args_list[-1][0][0]
    
    # Basic structure check
    assert args[0] == "docker"
    assert "run" in args
    assert "--rm" in args
    # Check volume mounts
    assert "-v" in args
    assert f"{params.tmpdir}:{params.tmpdir}" in args
    assert "/current/location:/current/location" in args
    # Check user mapping
    assert "--user" in args
    assert "1000:1000" in args
    # Check image and command
    assert "busybox" in args
    assert "sh" in args
    assert "-c" in args
    assert "echo hello" in args

def test_container_list_command(params, mock_util_funcs, mock_run, mock_files):
    mock_load, _ = mock_util_funcs
    operation = "op2"
    
    mock_load.return_value = {
        "commands": [{"cmd": ["ls", "-la"], "image": "alpine"}],
    }

    engine.container(operation, params)
    
    args = mock_run.call_args_list[-1][0][0]
    assert "alpine" in args
    # properly extended
    assert args[-2] == "ls"
    assert args[-1] == "-la"

def test_container_map_command(params, mock_util_funcs, mock_run, mock_files):
    mock_load, _ = mock_util_funcs
    operation = "op3"
    
    # Provide a dictionary command
    # NOTE: In Python < 3.7 dict order isn't guaranteed, but here we assume insertion order (3.7+)
    cmd_dict = {"-n": "5", "--flag": None} 
    mock_load.return_value = {
        "commands": [{"cmd": cmd_dict, "image": "alpine"}],
    }

    # This test might fail if map support isn't implemented as expected!
    engine.container(operation, params)
    
    args = mock_run.call_args_list[-1][0][0]
    assert "alpine" in args
    # Expected: -n 5 --flag
    # If implementation uses .extend(dict), it would just be keys "-n", "--flag"
    # Logic in engine.py needs to handle dict specifically
    
    # Let's inspect what we got
    print(f"DEBUG ARGS: {args}")
    
    # Assertions based on "correct" behavior (which we might need to fix)
    assert "-n" in args
    assert "5" in args
    idx = args.index("-n")
    assert args[idx+1] == "5"
    assert "--flag" in args

def test_container_entrypoint_override(params, mock_util_funcs, mock_run, mock_files):
    mock_load, _ = mock_util_funcs
    operation = "op4"
    
    mock_load.return_value = {
        "runner": {"image": "base", "entrypoint": "/base/entry"},
        "commands": [{"cmd": "run", "entrypoint": "/custom/entry"}]
    }

    engine.container(operation, params)
    args = mock_run.call_args_list[-1][0][0]
    
    assert "--entrypoint" in args
    idx = args.index("--entrypoint")
    assert args[idx+1] == "/custom/entry"

def test_container_podman_runtime(params, mock_util_funcs, mock_run, mock_files):
    params._plugin_conf["generator.runtime"] = "podman"
    mock_load, _ = mock_util_funcs
    mock_load.return_value = {
        "commands": ["echo podman"],
        "runner": {"image": "fedora"}
    }
    
    # Update mock to say "Podman version..."
    mock_run.return_value = MagicMock(returncode=0, stdout="Podman version 3.0")

    engine.container("op_pod", params)
    
    args = mock_run.call_args_list[-1][0][0]
    assert args[0] == "podman"
    assert "--userns=keep-id" in args
    assert "--user" not in args

def test_container_env_vars(params, mock_util_funcs, mock_run, mock_files):
    mock_load, _ = mock_util_funcs
    mock_load.return_value = {
        "commands": ["env"],
        "runner": {"image": "img"},
        "env": {"TEST_VAR": "TEST_VAL"}
    }

    engine.container("op_env", params)
    args = mock_run.call_args_list[-1][0][0]
    
    # Check env var injection
    assert "-e" in args
    assert "TEST_VAR=TEST_VAL" in args
    # Check standard vars
    assert f"LOGLEVEL={logging.INFO}" in args
    assert "DRYRUN=false" in args

def test_container_missing_image(params, mock_util_funcs, mock_run, mock_files):
    mock_load, _ = mock_util_funcs
    mock_load.return_value = {
        "commands": ["oops"],
        # No runner.image and no command image
    }

    with pytest.raises(OstrichError) as excinfo:
        engine.container("op_fail", params)
    
    assert "No container image defined" in str(excinfo.value)
