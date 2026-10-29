class AppException(Exception):
    """Base for errors the application raises on purpose."""


class AppValidationException(AppException):
    """The request is well-formed but not acceptable."""


class NotFoundException(AppException):
    """The requested entity does not exist."""


class MediaProcessingException(AppException):
    """ffmpeg/ffprobe failed or the media is unusable."""


class DownloadException(AppException):
    """The source URL could not be downloaded."""


class TranscriptionException(AppException):
    """The speech-to-text engine failed."""


class LLMException(AppException):
    """The LLM provider could not be reached or rejected the request."""


class InvalidLLMOutputException(LLMException):
    """The LLM answered, but not with the JSON that was asked for."""
