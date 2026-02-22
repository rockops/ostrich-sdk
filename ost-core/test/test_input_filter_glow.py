
import os
import pytest
from src.toolkit import input_filter, setLocation, OstrichError
import src.toolkit as toolkit

@pytest.fixture(autouse=True)
def setup_config():
    toolkit.configAll = {
        'generator': {
            'params': {
                'input': {
                    'src': 'src',
                    'java_path': 'src/java',
                    'empty': ''
                }
            }
        }
    }
    setLocation("/home/ben/test")

def test_input_src_java():
    # [[ "java" | input("src") ]] => /home/ben/test/src/java
    # Key: generator.params.input.src => 'src'
    # base: /home/ben/test/src
    # final: /home/ben/test/src/java
    result = input_filter("java", "src")
    assert result == "/home/ben/test/src/java"

def test_input_empty_value():
    # [[ "" | input("src") ]] => /home/ben/test/src
    result = input_filter("", "src")
    assert result == "/home/ben/test/src"

def test_input_java_path():
    # [[ "MyClass.java" | input("java_path") ]] => /home/ben/test/src/java/MyClass.java
    result = input_filter("MyClass.java", "java_path")
    assert result == "/home/ben/test/src/java/MyClass.java"

def test_input_not_found():
    with pytest.raises(OstrichError) as excinfo:
        input_filter("test", "missing")
    assert "Error in 'input' filter for 'missing'" in str(excinfo.value)
