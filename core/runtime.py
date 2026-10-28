"""Dependency-free runtime gate, parseable on older Python interpreters."""

import sys


def require_supported_python(version=None):
    """Fail clearly before importing modules that require Python 3.12 syntax."""
    current = sys.version_info if version is None else version
    if tuple(current[:2]) < (3, 12):
        raise RuntimeError("Tabular Intelligence requires Python 3.12 or newer.")
