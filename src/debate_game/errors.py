class DebateError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(DebateError):
    """Raised when runtime configuration is invalid."""


class ModelAPIError(DebateError):
    """Raised when an OpenAI-compatible endpoint fails."""


class StreamProtocolError(DebateError):
    """Raised when an SSE or debate control protocol is invalid."""
