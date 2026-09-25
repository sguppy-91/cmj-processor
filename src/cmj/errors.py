"""Error types for the CMJ analysis pipeline."""


class CMJError(Exception):
    """Base class for all cmj-processor errors."""


class FormatError(CMJError):
    """A file does not match the expected vendor export format."""


class UnknownFormatError(FormatError):
    """No reader recognises the file's export format."""


class WeighingWindowError(CMJError):
    """The analyst-specified weighing window is unusable (e.g. too short)."""


class OnsetError(CMJError):
    """No movement onset could be detected from the weighing window."""


class PhaseError(CMJError):
    """Jump phase boundaries could not be identified."""


class TakeoffError(CMJError):
    """Take-off could not be detected from the force trace."""
