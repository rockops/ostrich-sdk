import pytest
from src.test import sdk
import logging

class TestSdkSimple:
    def test_sdk_help(self):
        # Implement just 1 test using ost in sdk.py, run "ost help"
        logging.info("Running ost help test")
        sdk.ost(["help"])
