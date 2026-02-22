import logging

# Log configuration
STRATEGY_LOG_FORMAT = '%(levelname)-8s %(message)s'
DEBUG_STRATEGY_LOG_FORMAT = '%(levelname)-8s [%(filename)s:%(lineno)d] %(message)s'

def apply_logging_defaults():
    logging.basicConfig(level=logging.INFO, format=STRATEGY_LOG_FORMAT)

USER_AGENT = "Ostrich-SDK-Core/2.0"
DEFAULT_RUNTIME = "docker"
SCRATCH_PREFIX = "ost-build-"
