"""Tests for pooled Chromium lifecycle and idle expiry."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kindly_web_search_mcp_server.scrape.chromium_pool import (
    ChromiumSlot,
    _resolve_idle_ttl_seconds,
)


def test_idle_ttl_defaults_to_30_minutes() -> None:
    with patch.dict("os.environ", {}, clear=True):
        assert _resolve_idle_ttl_seconds() == 1800.0


def test_idle_ttl_zero_disables_expiry() -> None:
    with patch.dict("os.environ", {"KINDLY_NODRIVER_IDLE_TTL_SECONDS": "0"}, clear=True):
        assert _resolve_idle_ttl_seconds() == 0.0


def test_idle_ttl_is_bounded() -> None:
    with patch.dict("os.environ", {"KINDLY_NODRIVER_IDLE_TTL_SECONDS": "999999"}, clear=True):
        assert _resolve_idle_ttl_seconds() == 86_400.0


async def test_idle_slot_is_terminated_after_ttl() -> None:
    slot = ChromiumSlot(slot_id=0, idle_ttl_seconds=0.01)
    slot.proc = SimpleNamespace(returncode=None)
    slot.terminate = AsyncMock()

    slot.mark_released()
    await asyncio.sleep(0.03)

    slot.terminate.assert_awaited_once()


async def test_reacquiring_slot_cancels_idle_expiry() -> None:
    slot = ChromiumSlot(slot_id=0, idle_ttl_seconds=0.01)
    slot.proc = SimpleNamespace(returncode=None)
    slot.terminate = AsyncMock()

    slot.mark_released()
    await slot.mark_acquired()
    await asyncio.sleep(0.03)

    slot.terminate.assert_not_awaited()
