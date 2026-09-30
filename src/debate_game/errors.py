class DebateError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(DebateError):
    """Raised when runtime configuration is invalid."""


class ModelAPIError(DebateError):
    """Raised when an OpenAI-compatible endpoint fails."""


class StreamProtocolError(DebateError):
    """Raised when an SSE or debate control protocol is invalid."""


class DebateCancelled(DebateError):
    """Raised when a running debate is cancelled by its user."""
