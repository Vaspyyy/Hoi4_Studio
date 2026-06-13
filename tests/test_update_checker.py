from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import patch, MagicMock

from src.update_checker import _version_greater, UpdateInfo


class TestVersionGreater:
    def test_major_greater(self):
        assert _version_greater("2.0.0", "1.9.9") is True

    def test_minor_greater(self):
        assert _version_greater("1.5.0", "1.4.9") is True

    def test_patch_greater(self):
        assert _version_greater("1.0.2", "1.0.1") is True

    def test_equal(self):
        assert _version_greater("1.0.0", "1.0.0") is False

    def test_less(self):
        assert _version_greater("1.0.0", "2.0.0") is False

    def test_different_lengths(self):
        assert _version_greater("1.0", "1.0.0") is False
        assert _version_greater("1.0.1", "1.0") is True

    def test_two_part_versions(self):
        assert _version_greater("1.1", "1.0") is True

    def test_invalid_returns_false(self):
        assert _version_greater("abc", "1.0.0") is False
        assert _version_greater("1.0.0", "xyz") is False

    def test_empty_returns_false(self):
        assert _version_greater("", "1.0.0") is False


class TestUpdateInfo:
    def test_creation(self):
        info = UpdateInfo(current="0.4.0", latest="v0.5.0", url="https://example.com")
        assert info.current == "0.4.0"
        assert info.latest == "v0.5.0"
        assert info.url == "https://example.com"


class TestFetchUpdate:
    def _make_response(self, status=200, body=None):
        resp = MagicMock()
        resp.status = status
        resp.read.return_value = json.dumps(body or {}).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    def test_newer_version_returns_info(self):
        from src.update_checker import _UpdateWorker

        body = {"tag_name": "v99.0.0", "html_url": "https://example.com/release"}
        resp = self._make_response(200, body)
        worker = _UpdateWorker()
        with patch("urllib.request.urlopen", return_value=resp):
            result = worker._fetch()
        assert result is not None
        assert result.latest == "v99.0.0"

    def test_same_version_returns_none(self):
        from src.update_checker import _UpdateWorker, VERSION

        body = {"tag_name": f"v{VERSION}", "html_url": "https://example.com"}
        resp = self._make_response(200, body)
        worker = _UpdateWorker()
        with patch("urllib.request.urlopen", return_value=resp):
            result = worker._fetch()
        assert result is None

    def test_older_version_returns_none(self):
        body = {"tag_name": "v0.0.1", "html_url": "https://example.com"}
        resp = self._make_response(200, body)
        worker = __import__("src.update_checker", fromlist=["_UpdateWorker"])._UpdateWorker()
        with patch("urllib.request.urlopen", return_value=resp):
            result = worker._fetch()
        assert result is None

    def test_missing_tag_returns_none(self):
        from src.update_checker import _UpdateWorker

        body = {"html_url": "https://example.com"}
        resp = self._make_response(200, body)
        worker = _UpdateWorker()
        with patch("urllib.request.urlopen", return_value=resp):
            result = worker._fetch()
        assert result is None

    def test_non_200_returns_none(self):
        from src.update_checker import _UpdateWorker

        resp = self._make_response(403, {})
        worker = _UpdateWorker()
        with patch("urllib.request.urlopen", return_value=resp):
            result = worker._fetch()
        assert result is None

    def test_network_error_handled(self):
        from src.update_checker import _UpdateWorker

        worker = _UpdateWorker()
        received = []
        worker.result.connect(lambda info: received.append(info))
        with patch("urllib.request.urlopen", side_effect=OSError("no network")):
            worker.run()
        assert received == [None]

    def test_bad_json_handled(self):
        from src.update_checker import _UpdateWorker

        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = b"not json"
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        worker = _UpdateWorker()
        received = []
        worker.result.connect(lambda info: received.append(info))
        with patch("urllib.request.urlopen", return_value=resp):
            worker.run()
        assert received == [None]
