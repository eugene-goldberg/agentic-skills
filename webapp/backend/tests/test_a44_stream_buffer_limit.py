"""A44 — the agent subprocess stream reader must not die on large stream-json
lines.

Root cause of the intelligent_kanban sprint abort at BL-0004: the `claude` CLI
emits `--output-format stream-json` as one newline-delimited JSON event per
line. A `Read` tool_result echoes the file content twice (the cat -n render in
message.content[].tool_result AND the raw file in a top-level
tool_use_result.file field), ~2.3x inflation, so a ~29 KB+ source file produces
a >64 KiB line. `proc.stdout.readline()` on a StreamReader built with asyncio's
DEFAULT 64 KiB limit (2**16) raises — note StreamReader.readline() converts the
underlying asyncio.LimitOverrunError into `ValueError("Separator is found, but
chunk is longer than limit")`, the exact string in the BL-0004 trace. The broad
`except Exception` then SIGTERM-killed the agent (exit 143) mid-read, before it
wrote any code. boards.py had grown to 32 KB by BL-0004 → a ~73 KB line.

Fix: spawn the subprocess with `limit=STREAM_READER_LIMIT` (64 MiB).

These tests pin the mechanism (default limit DOES raise on the BL-0004-shaped
line) and the fix (the raised limit reads it intact), and assert the production
spawn actually passes the constant.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from app.services import claude_agent
from app.services.claude_agent import STREAM_READER_LIMIT

# The empirically reconstructed BL-0004 boards.py Read line size (~73 KB),
# confirmed to within 0.4% by two independent methods.
BL0004_LINE_BYTES = 73_254
ASYNCIO_DEFAULT_LIMIT = 2 ** 16  # 65536 — asyncio.streams._DEFAULT_LIMIT


async def _readline_at_limit(limit: int, line_bytes: int) -> bytes:
    """Feed one `line_bytes`-long newline-terminated line into a StreamReader
    constructed with `limit`, then read it back the way claude_agent does."""
    reader = asyncio.StreamReader(limit=limit)
    reader.feed_data(b"x" * line_bytes + b"\n")
    reader.feed_eof()
    return await reader.readline()


# ─── 1. Regression: the default 64 KiB limit reproduces the BL-0004 failure ──


def test_default_limit_raises_on_bl0004_sized_line():
    """At asyncio's 64 KiB default, readline() raises ValueError with the exact
    BL-0004 message on the ~73 KB boards.py line. This is the bug."""
    with pytest.raises(ValueError) as exc_info:
        asyncio.run(_readline_at_limit(ASYNCIO_DEFAULT_LIMIT, BL0004_LINE_BYTES))
    # The exact string the orchestrator saw in the _error event.
    assert "chunk is longer than limit" in str(exc_info.value)


# ─── 2. Fix: the raised limit reads the same line intact ──────────────────────


def test_raised_limit_reads_bl0004_sized_line_intact():
    """With STREAM_READER_LIMIT, the ~73 KB line is returned whole — no raise,
    no truncation."""
    line = asyncio.run(_readline_at_limit(STREAM_READER_LIMIT, BL0004_LINE_BYTES))
    assert len(line) == BL0004_LINE_BYTES + 1  # +1 for the trailing newline


def test_raised_limit_handles_multi_megabyte_line():
    """Headroom check: a 10 MiB line (large multi-file diff / tool_result) still
    reads without raising under the 64 MiB ceiling."""
    big = 10 * 1024 * 1024
    line = asyncio.run(_readline_at_limit(STREAM_READER_LIMIT, big))
    assert len(line) == big + 1


# ─── 3. The constant is sane and the production spawn actually uses it ────────


def test_stream_reader_limit_is_well_above_default():
    assert STREAM_READER_LIMIT > ASYNCIO_DEFAULT_LIMIT
    assert STREAM_READER_LIMIT >= 16 * 1024 * 1024  # generous headroom
    assert STREAM_READER_LIMIT > BL0004_LINE_BYTES


def test_spawn_passes_the_limit_to_create_subprocess_exec():
    """Bind the test to the real code path: the source of stream_agent_task must
    pass limit=STREAM_READER_LIMIT to create_subprocess_exec. Guards against a
    future refactor silently dropping the kwarg and reintroducing A44."""
    src = inspect.getsource(claude_agent.stream_agent_task)
    assert "create_subprocess_exec" in src
    assert "limit=STREAM_READER_LIMIT" in src
