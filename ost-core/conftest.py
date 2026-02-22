def pytest_configure(config):
    """Registers custom Ostrich test markers for pytest."""
    config.addinivalue_line(
        "markers", "integ: identifies tests that require external environment interaction"
    )