"""ADR 0004 #35 — live-execution smoke test for the MCP server.

This is the guard the schema/drift test could NOT provide: it spawns the real
server over stdio and actually INVOKES a tool, asserting a returned payload — a
tool can advertise its schema correctly and still hang on execution (the #35
symptom). A second variant holds a concurrent writer on app.db while invoking,
guarding the loop-blocking path (the tool body now runs in a worker thread, and
WAL readers don't block writers, so the transport must stay responsive).

NOTE: these spawn the real server, which on import runs run_migrations against
data/app.db (idempotent; creates+seeds it if absent) and serves over stdio. They
are integration smoke tests, not hermetic units. Each call is wrapped in
anyio.fail_after so a regression FAILS loudly rather than hanging the suite.

This does NOT exercise the user's client->SSH->transport path, so a green run
here does not by itself prove the client hang is fixed — that remains open
pending the client launch config.
"""
import sqlite3
import sys
import threading

import anyio
import pytest

pytest.importorskip("mcp.client.stdio")
from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

from cvhealthcheck.db.migrations import DB_PATH  # noqa: E402

_PARAMS = StdioServerParameters(command=sys.executable, args=["-m", "cvhealthcheck.mcp.server"])


async def _initialize_then_call(hold_writer: bool):
    async with stdio_client(_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            with anyio.fail_after(30):
                await session.initialize()  # startup (incl. run_migrations) complete

            stop = None
            if hold_writer:
                # Hold an IMMEDIATE writer on app.db *after* startup, then invoke
                # the tool. WAL readers don't block writers and the tool runs in a
                # worker thread, so the call must still return promptly.
                started, stop = threading.Event(), threading.Event()

                def _hold():
                    c = sqlite3.connect(str(DB_PATH), timeout=30)
                    c.execute("PRAGMA journal_mode=WAL")
                    c.execute("BEGIN IMMEDIATE")
                    c.execute("UPDATE schema_migrations SET applied_at = applied_at WHERE 0 = 1")
                    started.set()
                    stop.wait(15)
                    c.rollback()
                    c.close()

                t = threading.Thread(target=_hold, daemon=True)
                t.start()
                started.wait(5)

            try:
                with anyio.fail_after(20):
                    return await session.call_tool("list_subjects", {})
            finally:
                if stop is not None:
                    stop.set()
                    t.join(5)


def test_mcp_list_subjects_live_execution():
    res = anyio.run(_initialize_then_call, False)
    assert res.content, "list_subjects returned no content"
    text = "".join(getattr(c, "text", "") for c in res.content)
    assert "subject_id" in text, "expected a real subject payload, not an empty/schema-only result"


def test_mcp_list_subjects_under_concurrent_writer():
    # The #35 loop-blocking guard: a held writer must NOT hang the tool call.
    res = anyio.run(_initialize_then_call, True)
    assert res.content
    text = "".join(getattr(c, "text", "") for c in res.content)
    assert "subject_id" in text
