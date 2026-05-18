"""Tests for kerf_firmware.registry_client."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from kerf_firmware.registry_client import (
    ARDUINO_LIBRARY_INDEX_URL,
    PLATFORMIO_REGISTRY_BASE,
    _cache_key,
    _cache_path,
    _fetch_json,
    arduino_library_index,
    search_libraries,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

FAKE_PIO_RESPONSE = {
    "items": [
        {
            "id": "123",
            "name": "ArduinoJson",
            "description": "JSON library for Arduino",
            "version": "7.0.0",
            "authors": [{"name": "Benoit Blanchon"}],
        },
        {
            "id": "456",
            "name": "Adafruit NeoPixel",
            "description": "LED strip driver",
            "version": "1.12.0",
            "authors": [{"name": "Adafruit Industries"}],
        },
    ],
    "total": 2,
}

FAKE_ARDUINO_INDEX = {
    "libraries": [
        {
            "name": "ArduinoJson",
            "version": "7.0.0",
            "author": "Benoit Blanchon",
            "url": "https://arduinojson.org",
        },
        {
            "name": "FastLED",
            "version": "3.6.0",
            "author": "Daniel Garcia",
            "url": "https://fastled.io",
        },
    ]
}


# ── Cache helpers ─────────────────────────────────────────────────────────────

def test_cache_key_is_sha256_hex():
    key = _cache_key("https://example.com/test")
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)


def test_cache_key_is_deterministic():
    url = "https://example.com/stable"
    assert _cache_key(url) == _cache_key(url)


def test_cache_key_differs_for_different_urls():
    assert _cache_key("https://a.com") != _cache_key("https://b.com")


def test_cache_path_ends_with_json(tmp_path):
    path = _cache_path("https://example.com", tmp_path)
    assert path.suffix == ".json"
    assert path.parent == tmp_path


# ── _fetch_json with real cache ────────────────────────────────────────────────

def test_fetch_json_writes_cache(tmp_path):
    fake_data = {"hello": "world"}

    def mock_urlopen(req, timeout):
        class FakeResp:
            def read(self):
                return json.dumps(fake_data).encode()
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
        return FakeResp()

    with patch("urllib.request.urlopen", mock_urlopen):
        result = _fetch_json("https://example.com/data", cache_dir=tmp_path)

    assert result == fake_data
    cache_file = _cache_path("https://example.com/data", tmp_path)
    assert cache_file.exists()


def test_fetch_json_cache_hit_skips_network(tmp_path):
    fake_data = {"cached": True}
    cache_file = _cache_path("https://example.com/cached", tmp_path)
    cache_file.write_text(json.dumps(fake_data))

    call_count = {"n": 0}

    def mock_urlopen(req, timeout):
        call_count["n"] += 1
        raise RuntimeError("Should not reach network")

    with patch("urllib.request.urlopen", mock_urlopen):
        result = _fetch_json("https://example.com/cached", cache_dir=tmp_path)

    assert result == fake_data
    assert call_count["n"] == 0, "Network was hit despite cache presence"


# ── search_libraries ──────────────────────────────────────────────────────────

def test_search_libraries_returns_items():
    def fake_fetcher(url):
        assert "names=ArduinoJson" in url
        return FAKE_PIO_RESPONSE

    result = search_libraries("ArduinoJson", _fetcher=fake_fetcher)
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["name"] == "ArduinoJson"


def test_search_libraries_url_contains_query():
    captured = {}

    def fake_fetcher(url):
        captured["url"] = url
        return {"items": []}

    search_libraries("my query", _fetcher=fake_fetcher)
    assert "my+query" in captured["url"] or "my%20query" in captured["url"] or "my query" in captured["url"]


def test_search_libraries_handles_list_response():
    fake_list = [{"name": "Lib1"}, {"name": "Lib2"}]

    def fake_fetcher(url):
        return fake_list

    result = search_libraries("Lib1", _fetcher=fake_fetcher)
    assert result == fake_list


def test_search_libraries_handles_empty_results():
    def fake_fetcher(url):
        return {"items": []}

    result = search_libraries("nonexistent-library-xyz", _fetcher=fake_fetcher)
    assert result == []


def test_search_libraries_result_shape():
    def fake_fetcher(url):
        return FAKE_PIO_RESPONSE

    result = search_libraries("test", _fetcher=fake_fetcher)
    for item in result:
        assert "name" in item
        assert "version" in item


# ── arduino_library_index ─────────────────────────────────────────────────────

def test_arduino_library_index_returns_list():
    def fake_fetcher(url):
        assert url == ARDUINO_LIBRARY_INDEX_URL
        return FAKE_ARDUINO_INDEX

    result = arduino_library_index(_fetcher=fake_fetcher)
    assert isinstance(result, list)
    assert len(result) == 2


def test_arduino_library_index_result_has_name_field():
    def fake_fetcher(url):
        return FAKE_ARDUINO_INDEX

    result = arduino_library_index(_fetcher=fake_fetcher)
    for lib in result:
        assert "name" in lib


def test_arduino_library_index_handles_list_response():
    flat = [{"name": "A"}, {"name": "B"}]

    def fake_fetcher(url):
        return flat

    result = arduino_library_index(_fetcher=fake_fetcher)
    assert result == flat


# ── Cache integration: second call is a hit ───────────────────────────────────

def test_second_search_call_is_cache_hit(tmp_path):
    call_count = {"n": 0}
    fake_response = {"items": [{"name": "CachedLib", "version": "1.0.0"}]}

    def mock_urlopen(req, timeout):
        call_count["n"] += 1
        class FakeResp:
            def read(self):
                return json.dumps(fake_response).encode()
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
        return FakeResp()

    with patch("urllib.request.urlopen", mock_urlopen):
        r1 = _fetch_json("https://example.com/lib-search", cache_dir=tmp_path)

    with patch("urllib.request.urlopen", mock_urlopen):
        r2 = _fetch_json("https://example.com/lib-search", cache_dir=tmp_path)

    assert r1 == r2
    assert call_count["n"] == 1, "Expected exactly 1 network call; second should hit cache"
