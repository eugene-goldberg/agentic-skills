"""Retrieval layer: graph + semantic tools for role agents.

Activated when RETRIEVAL_ENABLED=1 in env. Off by default so existing runs
are unaffected.
"""

from .tools import make_retrieval_tools

__all__ = ["make_retrieval_tools"]
