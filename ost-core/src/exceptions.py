class OstrichError(RuntimeError):
    """Base exception class for Ostrich SDK errors."""
    def __init__(self, detail, status=1):
        super().__init__(detail)
        self.status = status
