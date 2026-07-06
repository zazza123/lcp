"""Module whose __all__ selects one of two re-exports."""

from .core import CoreClass, core_function  # noqa: F401

__all__ = ["CoreClass"]
