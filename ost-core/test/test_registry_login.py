import pytest
from unittest.mock import patch, MagicMock
from src.util import Params
from src.ostrichException import OstrichException
import src.registry as registry_op

def test_registry_login_default_interactive():
    params = Params()
    params.operationParams = ["login"]
    
    with patch("src.util.helm") as mock_helm, \
         patch("src.registry.load_registries", return_value=[{'name': 'ostrich', 'url': 'ghcr.io/rockops/osplate'}]):
        registry_op.registry(params)
        mock_helm.assert_called_once_with("registry", "login", "ghcr.io")

def test_registry_login_with_flags():
    params = Params()
    params.operationParams = ["login", "-u", "myuser", "-p", "mypass"]
    
    with patch("src.util.helm") as mock_helm, \
         patch("src.registry.load_registries", return_value=[{'name': 'ostrich', 'url': 'ghcr.io/rockops/osplate'}]):
        registry_op.registry(params)
        mock_helm.assert_called_once_with("registry", "login", "ghcr.io", "-u", "myuser", "-p", "mypass")

def test_registry_login_named_registry_with_flags():
    params = Params()
    params.operationParams = ["login", "myregistry", "-u", "admin", "-p", "secret"]
    
    registries = [
        {'name': 'ostrich', 'url': 'ghcr.io/rockops/osplate'},
        {'name': 'myregistry', 'url': 'registry.example.com/charts'}
    ]
    
    with patch("src.util.helm") as mock_helm, \
         patch("src.registry.load_registries", return_value=registries):
        registry_op.registry(params)
        mock_helm.assert_called_once_with("registry", "login", "registry.example.com", "-u", "admin", "-p", "secret")

def test_registry_login_flags_before_name():
    params = Params()
    params.operationParams = ["login", "-u", "admin", "-p", "secret", "myregistry"]
    
    registries = [
        {'name': 'ostrich', 'url': 'ghcr.io/rockops/osplate'},
        {'name': 'myregistry', 'url': 'registry.example.com/charts'}
    ]
    
    with patch("src.util.helm") as mock_helm, \
         patch("src.registry.load_registries", return_value=registries):
        registry_op.registry(params)
        mock_helm.assert_called_once_with("registry", "login", "registry.example.com", "-u", "admin", "-p", "secret")

def test_registry_login_unknown_flag():
    params = Params()
    params.operationParams = ["login", "--foo"]
    
    with pytest.raises(OstrichException) as exc_info:
        registry_op.registry(params)
    assert "Unknown flag for login" in str(exc_info.value)

def test_registry_login_nonexistent_registry():
    params = Params()
    params.operationParams = ["login", "nonexistent"]
    
    with patch("src.registry.load_registries", return_value=[{'name': 'ostrich', 'url': 'ghcr.io/rockops/osplate'}]):
        with pytest.raises(OstrichException) as exc_info:
            registry_op.registry(params)
        assert "Registry 'nonexistent' not found" in str(exc_info.value)

def test_registry_login_password_stdin():
    params = Params()
    params.operationParams = ["login", "-u", "myuser", "--password-stdin"]
    
    with patch("src.util.helm") as mock_helm, \
         patch("src.registry.load_registries", return_value=[{'name': 'ostrich', 'url': 'ghcr.io/rockops/osplate'}]):
        registry_op.registry(params)
        mock_helm.assert_called_once_with("registry", "login", "ghcr.io", "-u", "myuser", "--password-stdin")

def test_registry_login_conflicting_password_flags():
    params = Params()
    params.operationParams = ["login", "-u", "myuser", "-p", "mypass", "--password-stdin"]
    
    with patch("src.registry.load_registries", return_value=[{'name': 'ostrich', 'url': 'ghcr.io/rockops/osplate'}]):
        with pytest.raises(OstrichException) as exc_info:
            registry_op.registry(params)
        assert "Cannot specify both -p/--password and --password-stdin" in str(exc_info.value)
