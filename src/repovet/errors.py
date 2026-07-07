"""Exceptions that map directly to CLI exit codes.

InputError  -> exit code 2 (bad target, repo not found, malformed batch file)
NetworkError -> exit code 3 (API rate limit, network failure, unexpected API error)
"""


class RepovetError(Exception):
    """Base class for errors that should produce a clean CLI message (no traceback)."""


class InputError(RepovetError):
    """The user gave us something we can't act on."""


class NetworkError(RepovetError):
    """We couldn't reach GitHub, or GitHub refused the request (rate limit, 5xx, ...)."""
