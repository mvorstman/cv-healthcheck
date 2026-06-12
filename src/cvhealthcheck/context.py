"""Typed context errors (ADR-0015 D5 — Context Integrity invariant).

Leaf module (stdlib only) so both the web layer (which raises on missing
explicit selection) and the data layer (which refuses unconditionally) can
share the same vocabulary without db/ importing web/.

The invariant these enforce: a customer-data WRITE may only occur against an
explicitly selected context; absence of explicit selection is an error, never
a silent default.
"""
from __future__ import annotations


class NoExplicitContextError(RuntimeError):
    """No customer/project was explicitly selected — a write may not proceed.

    Raised by ``require_active_context()`` (no session selection) and by
    ``execute_approval`` (no context parameters for an artifact approval).
    Read paths are unaffected: they may still fall back to the Default
    project via ``resolve_default_project``.
    """

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "No customer/project explicitly selected — select a customer "
            "and project before writing customer data."
        )


class UnknownContextError(ValueError):
    """A caller-asserted customer/project id does not exist.

    Caller-asserted context (MCP parameters) is untrusted input: it must
    name existing rows before anything is written against it.
    """


class ContextMismatchError(RuntimeError):
    """A staged row is stamped for one customer but approval was attempted
    under another. Nothing is written; the row is untouched."""
