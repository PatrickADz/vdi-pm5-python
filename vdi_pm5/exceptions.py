"""Exceptions for the PM5 driver."""


class PM5Error(Exception):
    """Base exception for the PM5 driver."""


class PM5ConnectionError(PM5Error):
    """The serial connection to the PM5 could not be opened or maintained."""


class PM5PortNotFoundError(PM5ConnectionError):
    """The PM5 port could not be detected automatically."""


class PM5CommunicationError(PM5Error):
    """A command was not ACKed or the response arrived malformed."""
