import pytest
import os
import yaml
from unittest.mock import patch
from src.util import Params, OstrichException

def test_load_default_ostrich_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "ostrich.yaml"
    config_file.write_text("""
kind: App
template:
  kind: test-tpl
name: default-app
port: 8080
""")

    params = Params()
    with patch("src.util.getTemplatePath", return_value=str(tmp_path)):
        params.loadPluginConf()

    assert params.parsedPluginConfig["name"] == "default-app"
    assert params.parsedPluginConfig["port"] == 8080

def test_load_file_without_ostrich_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    custom_file = tmp_path / "custom.yaml"
    custom_file.write_text("""
template:
  kind: test-tpl
name: custom-app
port: 9000
""")

    params = Params()
    params.pluginFiles = [str(custom_file)]
    with patch("src.util.getTemplatePath", return_value=str(tmp_path)):
        params.loadPluginConf()

    assert params.parsedPluginConfig["name"] == "custom-app"
    assert params.parsedPluginConfig["port"] == 9000

def test_load_file_merging_with_ostrich_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ostrich_file = tmp_path / "ostrich.yaml"
    ostrich_file.write_text("""
template:
  kind: test-tpl
  params:
    docker:
      image: my-image
      port: 8080
    k8s:
      namespace: default
name: base-app
""")

    override_file = tmp_path / "override.yaml"
    override_file.write_text("""
template:
  params:
    docker:
      port: 9090
    k8s:
      replicas: 3
""")

    params = Params()
    params.pluginFiles = [str(override_file)]
    with patch("src.util.getTemplatePath", return_value=str(tmp_path)):
        params.loadPluginConf()

    # Verify merge: base properties preserved, override applied, new properties added
    assert params.parsedPluginConfig["name"] == "base-app"
    assert params.parsedPluginConfig["template"]["params"]["docker"]["image"] == "my-image"
    assert params.parsedPluginConfig["template"]["params"]["docker"]["port"] == 9090
    assert params.parsedPluginConfig["template"]["params"]["k8s"]["namespace"] == "default"
    assert params.parsedPluginConfig["template"]["params"]["k8s"]["replicas"] == 3

def test_multiple_files_merge_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f1 = tmp_path / "f1.yaml"
    f1.write_text("""
template:
  kind: test-tpl
val1: "f1"
val2: "f1"
val3: "f1"
""")

    f2 = tmp_path / "f2.yaml"
    f2.write_text("""
val2: "f2"
val3: "f2"
""")

    f3 = tmp_path / "f3.yaml"
    f3.write_text("""
val3: "f3"
""")

    params = Params()
    params.pluginFiles = [str(f1), str(f2), str(f3)]
    with patch("src.util.getTemplatePath", return_value=str(tmp_path)):
        params.loadPluginConf()

    assert params.parsedPluginConfig["val1"] == "f1"
    assert params.parsedPluginConfig["val2"] == "f2"
    assert params.parsedPluginConfig["val3"] == "f3"

def test_file_merge_with_set_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ostrich_file = tmp_path / "ostrich.yaml"
    ostrich_file.write_text("""
template:
  kind: test-tpl
port: 8080
tag: v1.0
""")

    override_file = tmp_path / "override.yaml"
    override_file.write_text("""
port: 9000
tag: v2.0
""")

    params = Params()
    params.pluginFiles = [str(override_file)]
    params.setValues = ["port=9999"]
    with patch("src.util.getTemplatePath", return_value=str(tmp_path)):
        params.loadPluginConf()

    assert params.parsedPluginConfig["tag"] == "v2.0"
    assert params.parsedPluginConfig["port"] == 9999
