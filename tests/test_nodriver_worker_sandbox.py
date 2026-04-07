from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, patch


def _fetch_html_defaults() -> dict[str, object]:
    return {
        "reuse_browser": False,
        "remote_host": None,
        "remote_port": None,
        "user_data_dir": None,
        "overall_timeout_seconds": 60.0,
    }


class _FakeNavigateCommand:
    def __init__(self, url: str):
        self.url = url


def _fake_nodriver_module(start):
    return type(
        "X",
        (),
        {
            "start": start,
            "cdp": type(
                "CDP",
                (),
                {
                    "page": type(
                        "Page",
                        (),
                        {"navigate": staticmethod(lambda url: _FakeNavigateCommand(url))},
                    ),
                    "target": type(
                        "Target",
                        (),
                        {
                            "create_target": staticmethod(
                                lambda url, new_window=False, enable_begin_frame_control=True: (
                                    "create_target",
                                    url,
                                    new_window,
                                    enable_begin_frame_control,
                                )
                            )
                        },
                    ),
                },
            ),
        },
    )


class TestNodriverWorkerSandbox(unittest.IsolatedAsyncioTestCase):
    async def test_devtools_probe_ignores_proxy_env(self) -> None:
        from kindly_web_search_mcp_server.scrape import nodriver_worker

        captured: dict[str, object] = {}

        class _Resp:
            status_code = 200

        class _AsyncClient:
            def __init__(self, *args, **kwargs):
                captured.update(kwargs)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, _url: str, timeout: float | None = None):
                return _Resp()

        fake_httpx = type("httpx", (), {"AsyncClient": _AsyncClient})

        class _Proc:
            returncode = None

        with patch.dict("sys.modules", {"httpx": fake_httpx}), patch.dict(
            "os.environ",
            {"HTTP_PROXY": "http://proxy.invalid:8080", "HTTPS_PROXY": "http://proxy.invalid:8080"},
            clear=False,
        ):
            await nodriver_worker._wait_for_devtools_ready(
                host="127.0.0.1",
                port=9222,
                proc=_Proc(),
                timeout_seconds=1.0,
            )

        self.assertIn("trust_env", captured)
        self.assertFalse(captured["trust_env"])

    async def test_uses_ignore_cleanup_errors_for_profile_dir(self) -> None:
        from kindly_web_search_mcp_server.scrape import nodriver_worker

        class _FakePage:
            def get_content(self):
                return "<html><body>ok</body></html>"

            async def close(self):
                return None

        class _FakeBrowser:
            async def get(self, _url: str):
                return _FakePage()

            async def stop(self):
                return None

        fake_start = AsyncMock(return_value=_FakeBrowser())
        captured: dict[str, object] = {}
        fake_launch = AsyncMock()
        fake_wait_devtools = AsyncMock()
        fake_terminate = AsyncMock()

        class _TempDir:
            def __init__(self, *args, **kwargs):
                captured["kwargs"] = dict(kwargs)

            def __enter__(self):
                return "/tmp/kindly-nodriver-test"

            def __exit__(self, exc_type, exc, tb):
                return False

        with (
            patch.dict("sys.modules", {"nodriver": _fake_nodriver_module(fake_start)}),
            patch.dict("os.environ", {}, clear=False),
            patch("shutil.which", return_value="/usr/bin/chromium"),
            patch.object(nodriver_worker.tempfile, "TemporaryDirectory", _TempDir),
            patch.object(nodriver_worker.asyncio, "sleep", AsyncMock()),
            patch.object(nodriver_worker, "_pick_free_port", return_value=9222),
            patch.object(nodriver_worker, "_launch_chromium", fake_launch),
            patch.object(nodriver_worker, "_wait_for_devtools_ready", fake_wait_devtools),
            patch.object(nodriver_worker, "_terminate_process", fake_terminate),
        ):
            html = await nodriver_worker._fetch_html(
                "https://example.com",
                referer=None,
                user_agent="ua",
                wait_seconds=0.0,
                browser_executable_path=None,
                **_fetch_html_defaults(),
            )

        self.assertIn("ok", html)
        kwargs = captured.get("kwargs") or {}
        self.assertTrue(kwargs.get("ignore_cleanup_errors"))

    async def test_disables_sandbox_by_default(self) -> None:
        from kindly_web_search_mcp_server.scrape.nodriver_worker import _fetch_html

        class _FakePage:
            def get_content(self):
                return "<html><body>ok</body></html>"

            async def close(self):
                return None

        class _FakeBrowser:
            async def get(self, _url: str):
                return _FakePage()

            async def stop(self):
                return None

        fake_start = AsyncMock(return_value=_FakeBrowser())
        fake_launch = AsyncMock()

        with patch.dict("sys.modules", {"nodriver": _fake_nodriver_module(fake_start)}), patch.dict(
            "os.environ", {}, clear=False
        ), patch(
            "shutil.which", return_value="/usr/bin/chromium"
        ), patch(
            "kindly_web_search_mcp_server.scrape.nodriver_worker._pick_free_port", return_value=9222
        ), patch(
            "kindly_web_search_mcp_server.scrape.nodriver_worker._launch_chromium", fake_launch
        ), patch(
            "kindly_web_search_mcp_server.scrape.nodriver_worker._wait_for_devtools_ready", AsyncMock()
        ), patch(
            "kindly_web_search_mcp_server.scrape.nodriver_worker._terminate_process", AsyncMock()
        ), patch(
            "kindly_web_search_mcp_server.scrape.nodriver_worker.asyncio.sleep", AsyncMock()
        ):
            html = await _fetch_html(
                "https://example.com",
                referer=None,
                user_agent="ua",
                wait_seconds=0.0,
                browser_executable_path=None,
                **_fetch_html_defaults(),
            )

        self.assertIn("ok", html)
        args, _kwargs = fake_launch.call_args
        self.assertEqual(args[0], "/usr/bin/chromium")
        self.assertIn("--no-sandbox", args[1])

    async def test_allows_enabling_sandbox_via_env(self) -> None:
        from kindly_web_search_mcp_server.scrape.nodriver_worker import _fetch_html

        class _FakePage:
            def get_content(self):
                return "<html><body>ok</body></html>"

            async def close(self):
                return None

        class _FakeBrowser:
            async def get(self, _url: str):
                return _FakePage()

            async def stop(self):
                return None

        fake_start = AsyncMock(return_value=_FakeBrowser())
        fake_launch = AsyncMock()

        with patch.dict("sys.modules", {"nodriver": _fake_nodriver_module(fake_start)}), patch.dict(
            "os.environ", {"KINDLY_NODRIVER_SANDBOX": "1"}, clear=False
        ), patch(
            "shutil.which", return_value="/usr/bin/chromium"
        ), patch(
            "kindly_web_search_mcp_server.scrape.nodriver_worker._pick_free_port", return_value=9222
        ), patch(
            "kindly_web_search_mcp_server.scrape.nodriver_worker._launch_chromium", fake_launch
        ), patch(
            "kindly_web_search_mcp_server.scrape.nodriver_worker._wait_for_devtools_ready", AsyncMock()
        ), patch(
            "kindly_web_search_mcp_server.scrape.nodriver_worker._terminate_process", AsyncMock()
        ), patch(
            "kindly_web_search_mcp_server.scrape.nodriver_worker.asyncio.sleep", AsyncMock()
        ):
            await _fetch_html(
                "https://example.com",
                referer=None,
                user_agent="ua",
                wait_seconds=0.0,
                browser_executable_path=None,
                **_fetch_html_defaults(),
            )

        args, _kwargs = fake_launch.call_args
        self.assertEqual(args[0], "/usr/bin/chromium")
        self.assertNotIn("--no-sandbox", args[1])

    async def test_forces_sandbox_off_when_running_as_root(self) -> None:
        if os.name == "nt":
            self.skipTest("os.geteuid is not available on Windows")

        from kindly_web_search_mcp_server.scrape.nodriver_worker import _fetch_html

        class _FakePage:
            def get_content(self):
                return "<html><body>ok</body></html>"

            async def close(self):
                return None

        class _FakeBrowser:
            async def get(self, _url: str):
                return _FakePage()

            async def stop(self):
                return None

        fake_start = AsyncMock(return_value=_FakeBrowser())
        fake_launch = AsyncMock()

        with (
            patch.dict("sys.modules", {"nodriver": _fake_nodriver_module(fake_start)}),
            patch.dict("os.environ", {"KINDLY_NODRIVER_SANDBOX": "1"}, clear=False),
            patch("os.geteuid", return_value=0),
            patch("shutil.which", return_value="/usr/bin/chromium"),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._pick_free_port", return_value=9222),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._launch_chromium", fake_launch),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._wait_for_devtools_ready", AsyncMock()),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._terminate_process", AsyncMock()),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker.asyncio.sleep", AsyncMock()),
        ):
            await _fetch_html(
                "https://example.com",
                referer=None,
                user_agent="ua",
                wait_seconds=0.0,
                browser_executable_path=None,
                **_fetch_html_defaults(),
            )

        args, _kwargs = fake_launch.call_args
        self.assertEqual(args[0], "/usr/bin/chromium")
        self.assertIn("--no-sandbox", args[1])

    async def test_resolves_browser_executable_from_path(self) -> None:
        from kindly_web_search_mcp_server.scrape.nodriver_worker import _fetch_html

        class _FakePage:
            def get_content(self):
                return "<html><body>ok</body></html>"

            async def close(self):
                return None

        class _FakeBrowser:
            async def get(self, _url: str):
                return _FakePage()

            async def stop(self):
                return None

        fake_start = AsyncMock(return_value=_FakeBrowser())

        with (
            patch.dict("sys.modules", {"nodriver": _fake_nodriver_module(fake_start)}),
            patch.dict("os.environ", {}, clear=False),
            patch("shutil.which", return_value="/usr/bin/chromium"),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._pick_free_port", return_value=9222),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._launch_chromium", AsyncMock()),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._wait_for_devtools_ready", AsyncMock()),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._terminate_process", AsyncMock()),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker.asyncio.sleep", AsyncMock()),
        ):
            await _fetch_html(
                "https://example.com",
                referer=None,
                user_agent="ua",
                wait_seconds=0.0,
                browser_executable_path=None,
                **_fetch_html_defaults(),
            )

        _, kwargs = fake_start.call_args
        self.assertEqual(kwargs.get("browser_executable_path"), "/usr/bin/chromium")

    async def test_errors_when_no_browser_found(self) -> None:
        from kindly_web_search_mcp_server.scrape.nodriver_worker import _fetch_html

        fake_start = AsyncMock()

        with (
            patch.dict("sys.modules", {"nodriver": _fake_nodriver_module(fake_start)}),
            patch.dict("os.environ", {}, clear=False),
            patch("shutil.which", return_value=None),
        ):
            with self.assertRaisesRegex(RuntimeError, "KINDLY_BROWSER_EXECUTABLE_PATH"):
                await _fetch_html(
                    "https://example.com",
                    referer=None,
                    user_agent="ua",
                    wait_seconds=0.0,
                    browser_executable_path=None,
                    **_fetch_html_defaults(),
                )

    async def test_retries_on_failed_to_connect_to_browser(self) -> None:
        from kindly_web_search_mcp_server.scrape.nodriver_worker import _fetch_html

        class _FakePage:
            def get_content(self):
                return "<html><body>ok</body></html>"

            async def close(self):
                return None

        class _FakeBrowser:
            async def get(self, _url: str):
                return _FakePage()

            async def stop(self):
                return None

        fake_start = AsyncMock(side_effect=[RuntimeError("Failed to connect to browser"), _FakeBrowser()])

        fake_terminate = AsyncMock()
        with (
            patch.dict("sys.modules", {"nodriver": _fake_nodriver_module(fake_start)}),
            patch.dict("os.environ", {"KINDLY_NODRIVER_RETRY_ATTEMPTS": "2"}, clear=False),
            patch("shutil.which", return_value="/snap/bin/chromium"),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._pick_free_port", return_value=9222),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._launch_chromium", AsyncMock()),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._wait_for_devtools_ready", AsyncMock()),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._terminate_process", fake_terminate),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker.asyncio.sleep", AsyncMock()),
        ):
            html = await _fetch_html(
                "https://example.com",
                referer=None,
                user_agent="ua",
                wait_seconds=0.0,
                browser_executable_path=None,
                **_fetch_html_defaults(),
            )

        self.assertIn("ok", html)
        self.assertEqual(fake_start.call_count, 2)
        # One termination for the failed attempt, one for the successful attempt cleanup.
        self.assertEqual(fake_terminate.call_count, 2)

    async def test_retries_and_terminates_on_devtools_timeout(self) -> None:
        from kindly_web_search_mcp_server.scrape.nodriver_worker import _fetch_html

        fake_start = AsyncMock()
        fake_launch = AsyncMock()
        fake_wait = AsyncMock(side_effect=RuntimeError("DevTools endpoint did not become ready in time"))
        fake_terminate = AsyncMock()

        with (
            patch.dict("sys.modules", {"nodriver": _fake_nodriver_module(fake_start)}),
            patch.dict("os.environ", {"KINDLY_NODRIVER_RETRY_ATTEMPTS": "2"}, clear=False),
            patch("shutil.which", return_value="/snap/bin/chromium"),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._pick_free_port", return_value=9222),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._launch_chromium", fake_launch),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._wait_for_devtools_ready", fake_wait),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker._terminate_process", fake_terminate),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker.asyncio.sleep", AsyncMock()),
        ):
            with self.assertRaisesRegex(RuntimeError, "Failed to connect to browser after 2 attempt"):
                await _fetch_html(
                    "https://example.com",
                    referer=None,
                    user_agent="ua",
                    wait_seconds=0.0,
                    browser_executable_path=None,
                    **_fetch_html_defaults(),
                )

        self.assertEqual(fake_launch.call_count, 2)
        self.assertEqual(fake_terminate.call_count, 2)
        self.assertEqual(fake_start.call_count, 0)

    async def test_reused_page_is_reset_to_about_blank_during_cleanup(self) -> None:
        from kindly_web_search_mcp_server.scrape.nodriver_worker import _fetch_html

        navigated_urls: list[str] = []

        class _FakeTab:
            target_id = "tab-1"
            frame_id = None
            type_ = "page"

            async def send(self, command):
                navigated_urls.append(getattr(command, "url", None))
                return ("frame-1",)

            def get_content(self):
                return "<html><body>ok</body></html>"

        class _FakeConnection:
            async def send(self, _command):
                return "target-1"

        class _FakeBrowser:
            def __init__(self):
                self.connection = _FakeConnection()
                self.targets = [_FakeTab()]

            async def update_targets(self):
                return None

        fake_start = AsyncMock(return_value=_FakeBrowser())

        with (
            patch.dict("sys.modules", {"nodriver": _fake_nodriver_module(fake_start)}),
            patch("kindly_web_search_mcp_server.scrape.nodriver_worker.asyncio.sleep", AsyncMock()),
        ):
            html = await _fetch_html(
                "https://example.com/page",
                referer=None,
                user_agent="ua",
                wait_seconds=0.0,
                browser_executable_path="/usr/bin/chromium",
                reuse_browser=True,
                remote_host="127.0.0.1",
                remote_port=9222,
                user_data_dir="/tmp/kindly-nodriver-pool-test",
                overall_timeout_seconds=60.0,
            )

        self.assertIn("ok", html)
        self.assertEqual(navigated_urls, ["https://example.com/page", "about:blank"])

    def test_worker_stdout_write_uses_utf8_bytes(self) -> None:
        """
        Regression: on Windows, sys.stdout may be configured with a legacy codepage (e.g., cp1252),
        so writing HTML as text can raise UnicodeEncodeError. The worker must emit UTF-8 bytes.
        """
        import io

        from kindly_web_search_mcp_server.scrape import nodriver_worker

        class _BadTextIO(io.TextIOBase):
            def __init__(self) -> None:
                self.buffer = io.BytesIO()

            def write(self, _s: str) -> int:  # pragma: no cover
                raise UnicodeEncodeError("charmap", "x", 0, 1, "cannot encode")

        stream = _BadTextIO()
        payload = "Hello — 世界".encode("utf-8", errors="strict")
        nodriver_worker._safe_write_bytes(stream, payload)
        self.assertIn(b"Hello", stream.buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
