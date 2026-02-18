"""Custom exceptions."""

class TecomError(Exception):
    """Base exception for this integration."""

class TecomConnectionError(TecomError):
    """Connection failure."""

class TecomNotSupported(TecomError):
    """Raised when a feature isn't supported in the current mode."""
