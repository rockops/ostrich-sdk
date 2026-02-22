class OstrichException(RuntimeError):
    """
    Standard exception raised by Ostrich operations.
    Includes an optional exit code for CLI termination.
    """
    def __init__(self, detail_message, status_code=1):
        super().__init__(detail_message)
        self.exit_code = status_code

# End of Exception definition
