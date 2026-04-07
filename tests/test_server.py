from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path
import unittest
import asyncio
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kindly_web_search_mcp_server.models import WebSearchResult


def _install_fake_mcp() -> None:
    fake_mcp_module = types.ModuleType("mcp")
    fake_server_module = types.ModuleType("mcp.server")
    fake_fastmcp_module = types.ModuleType("mcp.server.fastmcp")
    fake_transport_module = types.ModuleType("mcp.server.transport_security")

    class _FakeFastMCP:
        def __init__(self, *_args, **_kwargs):
            self.settings = types.SimpleNamespace(host=None, port=None, transport_security=None)

        def tool(self):
            def _decorator(func):
                return func

            return _decorator

        def run(self, **_kwargs):
            return None

    class _FakeTransportSecuritySettings:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    fake_fastmcp_module.FastMCP = _FakeFastMCP
    fake_transport_module.TransportSecuritySettings = _FakeTransportSecuritySettings

    sys.modules["mcp"] = fake_mcp_module
    sys.modules["mcp.server"] = fake_server_module
    sys.modules["mcp.server.fastmcp"] = fake_fastmcp_module
    sys.modules["mcp.server.transport_security"] = fake_transport_module


def _import_server_module():
    _install_fake_mcp()
    sys.modules.pop("kindly_web_search_mcp_server.server", None)
    return importlib.import_module("kindly_web_search_mcp_server.server")


class TestWebSearchTool(unittest.IsolatedAsyncioTestCase):
    def test_tool_timeout_budget_can_exceed_55_seconds(self) -> None:
        server = _import_server_module()
        _resolve_tool_total_timeout_seconds = server._resolve_tool_total_timeout_seconds

        with patch.dict(
            os.environ,
            {
                "KINDLY_TOOL_TOTAL_TIMEOUT_SECONDS": "120",
                "KINDLY_TOOL_TOTAL_TIMEOUT_MAX_SECONDS": "600",
            },
            clear=False,
        ):
            self.assertEqual(_resolve_tool_total_timeout_seconds(), 120.0)

        with patch.dict(
            os.environ,
            {
                "KINDLY_TOOL_TOTAL_TIMEOUT_SECONDS": "120",
                "KINDLY_TOOL_TOTAL_TIMEOUT_MAX_SECONDS": "100",
            },
            clear=False,
        ):
            self.assertEqual(_resolve_tool_total_timeout_seconds(), 100.0)

        with patch.dict(
            os.environ,
            {"KINDLY_TOOL_TOTAL_TIMEOUT_SECONDS": "abc"},
            clear=False,
        ):
            self.assertEqual(_resolve_tool_total_timeout_seconds(), 120.0)

        with patch.dict(
            os.environ,
            {"KINDLY_TOOL_TOTAL_TIMEOUT_MAX_SECONDS": "abc"},
            clear=False,
        ):
            self.assertEqual(_resolve_tool_total_timeout_seconds(), 120.0)

        with patch.dict(
            os.environ,
            {"KINDLY_TOOL_TOTAL_TIMEOUT_MAX_SECONDS": "90"},
            clear=False,
        ):
            self.assertEqual(_resolve_tool_total_timeout_seconds(), 90.0)

    def test_web_search_concurrency_defaults_on_windows(self) -> None:
        server = _import_server_module()
        _resolve_web_search_max_concurrency = server._resolve_web_search_max_concurrency

        with patch.dict(os.environ, {}, clear=True), patch(
            "kindly_web_search_mcp_server.server.os.name", "nt"
        ):
            self.assertEqual(_resolve_web_search_max_concurrency(3), 3)

        with patch.dict(
            os.environ,
            {"KINDLY_WEB_SEARCH_MAX_CONCURRENCY": "3"},
            clear=True,
        ), patch("kindly_web_search_mcp_server.server.os.name", "nt"):
            self.assertEqual(_resolve_web_search_max_concurrency(3), 3)

        with patch.dict(
            os.environ,
            {"KINDLY_WEB_SEARCH_MAX_CONCURRENCY": "abc"},
            clear=True,
        ), patch("kindly_web_search_mcp_server.server.os.name", "nt"):
            self.assertEqual(_resolve_web_search_max_concurrency(3), 3)

        with patch.dict(
            os.environ,
            {"KINDLY_WEB_SEARCH_MAX_CONCURRENCY": "0"},
            clear=True,
        ), patch("kindly_web_search_mcp_server.server.os.name", "nt"):
            self.assertEqual(_resolve_web_search_max_concurrency(3), 3)

        with patch.dict(
            os.environ,
            {"KINDLY_WEB_SEARCH_MAX_CONCURRENCY": "-2"},
            clear=True,
        ), patch("kindly_web_search_mcp_server.server.os.name", "nt"):
            self.assertEqual(_resolve_web_search_max_concurrency(3), 3)

    def test_web_search_concurrency_limited_by_num_results_on_windows(self) -> None:
        server = _import_server_module()
        _resolve_web_search_max_concurrency = server._resolve_web_search_max_concurrency

        with patch.dict(
            os.environ,
            {"KINDLY_WEB_SEARCH_MAX_CONCURRENCY": "10"},
            clear=True,
        ), patch("kindly_web_search_mcp_server.server.os.name", "nt"):
            self.assertEqual(_resolve_web_search_max_concurrency(3), 3)

    def test_web_search_concurrency_defaults_on_non_windows(self) -> None:
        server = _import_server_module()
        _resolve_web_search_max_concurrency = server._resolve_web_search_max_concurrency

        with patch.dict(os.environ, {}, clear=True), patch(
            "kindly_web_search_mcp_server.server.os.name", "posix"
        ):
            self.assertEqual(_resolve_web_search_max_concurrency(3), 3)

        with patch.dict(
            os.environ,
            {"KINDLY_WEB_SEARCH_MAX_CONCURRENCY": "5"},
            clear=True,
        ), patch("kindly_web_search_mcp_server.server.os.name", "posix"):
            self.assertEqual(_resolve_web_search_max_concurrency(3), 3)

        with patch.dict(
            os.environ,
            {"KINDLY_WEB_SEARCH_MAX_CONCURRENCY": "7"},
            clear=True,
        ), patch("kindly_web_search_mcp_server.server.os.name", "posix"):
            self.assertEqual(_resolve_web_search_max_concurrency(5), 5)

        with patch.dict(
            os.environ,
            {"KINDLY_WEB_SEARCH_MAX_CONCURRENCY": "abc"},
            clear=True,
        ), patch("kindly_web_search_mcp_server.server.os.name", "posix"):
            self.assertEqual(_resolve_web_search_max_concurrency(3), 3)

    def test_tool_timeout_defaults_to_120_seconds(self) -> None:
        server = _import_server_module()
        _resolve_tool_total_timeout_seconds = server._resolve_tool_total_timeout_seconds

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_resolve_tool_total_timeout_seconds(), 120.0)

    async def test_web_search_returns_results(self) -> None:
        server = _import_server_module()
        web_search = server.web_search

        mocked_results = [
            WebSearchResult(title="T", link="https://example.com", snippet="S", page_content="")
        ]

        with patch(
            "kindly_web_search_mcp_server.server.search_web", new_callable=AsyncMock
        ) as mock_search, patch(
            "kindly_web_search_mcp_server.server.resolve_page_content_markdown",
            new_callable=AsyncMock,
        ) as mock_resolve:
            mock_search.return_value = mocked_results
            mock_resolve.return_value = "# Title\n\nHello"

            out = await web_search("hello", num_results=1)

        self.assertIsInstance(out, dict)
        self.assertIn("results", out)
        self.assertEqual(len(out["results"]), 1)
        self.assertEqual(out["results"][0]["title"], "T")
        self.assertEqual(out["results"][0]["link"], "https://example.com")
        self.assertEqual(out["results"][0]["snippet"], "S")
        self.assertIn("page_content", out["results"][0])
        self.assertIn("Hello", out["results"][0]["page_content"])

    async def test_get_content_returns_markdown(self) -> None:
        server = _import_server_module()
        get_content = server.get_content

        with patch(
            "kindly_web_search_mcp_server.server.resolve_page_content_markdown",
            new_callable=AsyncMock,
        ) as mock_resolve:
            mock_resolve.return_value = "# Title\n\nHello"
            out = await get_content("https://example.com")

        self.assertEqual(out["url"], "https://example.com")
        self.assertIn("page_content", out)
        self.assertIn("Hello", out["page_content"])

    async def test_get_content_handles_none(self) -> None:
        server = _import_server_module()
        get_content = server.get_content

        with patch(
            "kindly_web_search_mcp_server.server.resolve_page_content_markdown",
            new_callable=AsyncMock,
        ) as mock_resolve:
            mock_resolve.return_value = None
            out = await get_content("https://example.com/file.pdf")

        self.assertEqual(out["url"], "https://example.com/file.pdf")
        self.assertIn("Could not retrieve content", out["page_content"])

    async def test_get_content_returns_timeout_note_on_timeout(self) -> None:
        server = _import_server_module()
        get_content = server.get_content

        with patch(
            "kindly_web_search_mcp_server.server.resolve_page_content_markdown",
            new_callable=AsyncMock,
        ) as mock_resolve:
            mock_resolve.side_effect = asyncio.TimeoutError()
            out = await get_content("https://example.com")

        self.assertIn("TimeoutError", out["page_content"])
        self.assertIn("Source: https://example.com", out["page_content"])

    async def test_web_search_returns_timeout_note_on_timeout(self) -> None:
        server = _import_server_module()
        web_search = server.web_search

        mocked_results = [
            WebSearchResult(
                title="T",
                link="https://example.com",
                snippet="S",
                page_content="",
            )
        ]

        with patch(
            "kindly_web_search_mcp_server.server.search_web", new_callable=AsyncMock
        ) as mock_search, patch(
            "kindly_web_search_mcp_server.server.resolve_page_content_markdown",
            new_callable=AsyncMock,
        ) as mock_resolve:
            mock_search.return_value = mocked_results
            mock_resolve.side_effect = asyncio.TimeoutError()
            out = await web_search("hello", num_results=1)

        self.assertIn("TimeoutError", out["results"][0]["page_content"])
        self.assertIn("Source: https://example.com", out["results"][0]["page_content"])


if __name__ == "__main__":
    unittest.main()
