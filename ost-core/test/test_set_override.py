import pytest
import os
import yaml
from unittest.mock import patch, MagicMock
from src.util import Params, OstrichException

def test_set_override_flat_key(tmp_path):
    config_file = tmp_path / "ostrich.yaml"
    config_file.write_text("""
kind: App
template:
  kind: test-tpl
name: original-name
port: 8080
enabled: false
""")
    
    params = Params()
    params.pluginFile = str(config_file)
    params.setValues = ["name=overridden-name", "port=9090", "enabled=true"]
    
    with patch("src.util.getTemplatePath", return_value=str(tmp_path)):
        params.loadPluginConf()
        
    assert params.parsedPluginConfig["name"] == "overridden-name"
    assert params.parsedPluginConfig["port"] == 9090
    assert params.parsedPluginConfig["enabled"] is True

def test_set_override_nested_keys(tmp_path):
    config_file = tmp_path / "ostrich.yaml"
    config_file.write_text("""
template:
  kind: test-tpl
  params:
    input:
      src: "old/src"
      count: 1
""")
    
    params = Params()
    params.pluginFile = str(config_file)
    params.setValues = [
        "template.params.input.src=new/src",
        "template.params.input.count=42",
        "template.params.input.nested.deep.flag=true",
        "image.repository=myrepo/image",
        "image.tag=v1.2.3"
    ]
    
    with patch("src.util.getTemplatePath", return_value=str(tmp_path)):
        params.loadPluginConf()
        
    assert params.parsedPluginConfig["template"]["params"]["input"]["src"] == "new/src"
    assert params.parsedPluginConfig["template"]["params"]["input"]["count"] == 42
    assert params.parsedPluginConfig["template"]["params"]["input"]["nested"]["deep"]["flag"] is True
    assert params.parsedPluginConfig["image"]["repository"] == "myrepo/image"
    assert params.parsedPluginConfig["image"]["tag"] == "v1.2.3"

def test_set_override_complex_yaml_values(tmp_path):
    config_file = tmp_path / "ostrich.yaml"
    config_file.write_text("""
template:
  kind: test-tpl
items: []
env: {}
""")
    
    params = Params()
    params.pluginFile = str(config_file)
    params.setValues = [
        "items=[a, b, c]",
        "env={FOO: bar, BAZ: 123}",
        "nullable=null"
    ]
    
    with patch("src.util.getTemplatePath", return_value=str(tmp_path)):
        params.loadPluginConf()
        
    assert params.parsedPluginConfig["items"] == ["a", "b", "c"]
    assert params.parsedPluginConfig["env"] == {"FOO": "bar", "BAZ": 123}
    assert params.parsedPluginConfig["nullable"] is None

def test_set_override_invalid_format():
    params = Params()
    params.setValues = ["invalid_no_equal_sign"]
    target = {}
    with pytest.raises(OstrichException) as exc_info:
        params.applySetOverrides(target)
    assert "Invalid --set format" in str(exc_info.value)

def test_set_override_empty_key():
    params = Params()
    params.setValues = ["=value"]
    target = {}
    with pytest.raises(OstrichException) as exc_info:
        params.applySetOverrides(target)
    assert "key cannot be empty" in str(exc_info.value)

def test_collect_standard_args_set():
    params = Params()
    params.operationParams = [
        "deploy",
        "--set", "foo=bar",
        "--set=nested.key=123",
        "--set", "baz=true",
        "-d"
    ]
    params.collectStandardArgs()
    
    assert params.operationParams == ["deploy"]
    assert params.setValues == ["foo=bar", "nested.key=123", "baz=true"]
    assert params.loglevel == 10  # logging.DEBUG
