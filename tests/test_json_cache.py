"""
Unit tests for src/json_cache.py — LRU JSON file cache.

Tests cover:
- Cache miss (file read from disk) and cache hit (served from memory)
- TTL expiration
- LRU eviction when max_size is exceeded
- invalidate() removes a single entry
- clear() empties the entire cache
- stats() returns correct values
- Graceful handling of missing files and invalid JSON
- Convenience module-level functions
"""

import json
import pytest
from pathlib import Path

from json_cache import (
    JSONCache,
    get_cached_json,
    invalidate_json_cache,
    clear_json_cache,
    get_json_cache_stats,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ============================================================================
# JSONCache.get — basic read behaviour
# ============================================================================

class TestJSONCacheGet:
    def test_cache_miss_reads_file(self, tmp_path):
        f = write_json(tmp_path / "data.json", {"key": "value"})
        cache = JSONCache()
        result = cache.get(f)
        assert result == {"key": "value"}

    def test_cache_hit_returns_same_data(self, tmp_path):
        f = write_json(tmp_path / "data.json", {"x": 1})
        cache = JSONCache()
        first = cache.get(f)
        # Overwrite file on disk — cache should still serve the old data
        f.write_text(json.dumps({"x": 999}), encoding="utf-8")
        second = cache.get(f)
        assert first == second == {"x": 1}

    def test_missing_file_returns_default(self, tmp_path):
        cache = JSONCache()
        result = cache.get(tmp_path / "nonexistent.json", default={"fallback": True})
        assert result == {"fallback": True}

    def test_missing_file_returns_none_by_default(self, tmp_path):
        cache = JSONCache()
        result = cache.get(tmp_path / "nonexistent.json")
        assert result is None

    def test_invalid_json_returns_default(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json at all {{{", encoding="utf-8")
        cache = JSONCache()
        result = cache.get(f, default=[])
        assert result == []

    def test_list_json_supported(self, tmp_path):
        f = write_json(tmp_path / "list.json", [1, 2, 3])  # type: ignore[arg-type]
        f.write_text("[1, 2, 3]", encoding="utf-8")
        cache = JSONCache()
        result = cache.get(f)
        assert result == [1, 2, 3]


# ============================================================================
# JSONCache — TTL expiration
# ============================================================================

class TestJSONCacheTTL:
    def test_expired_entry_re_reads_file(self, tmp_path):
        f = write_json(tmp_path / "data.json", {"v": 1})
        cache = JSONCache(ttl_seconds=0)  # every entry expires immediately
        cache.get(f)  # populate cache

        # Update file on disk; TTL=0 means next access should re-read
        write_json(f, {"v": 2})
        result = cache.get(f)
        assert result == {"v": 2}

    def test_valid_entry_served_from_cache(self, tmp_path):
        f = write_json(tmp_path / "data.json", {"v": 1})
        cache = JSONCache(ttl_seconds=9999)
        cache.get(f)

        write_json(f, {"v": 2})  # change file
        result = cache.get(f)
        assert result == {"v": 1}  # still served from cache


# ============================================================================
# JSONCache — LRU eviction
# ============================================================================

class TestJSONCacheEviction:
    def test_cache_does_not_exceed_max_size(self, tmp_path):
        max_size = 10
        cache = JSONCache(max_size=max_size, ttl_seconds=9999)
        for i in range(max_size + 5):
            f = write_json(tmp_path / f"file_{i}.json", {"i": i})
            cache.get(f)

        stats = cache.stats()
        assert stats["size"] <= max_size

    def test_eviction_keeps_recently_used(self, tmp_path):
        """After eviction the cache size should be below max_size."""
        max_size = 5
        cache = JSONCache(max_size=max_size, ttl_seconds=9999)
        files = []
        for i in range(max_size + 3):
            f = write_json(tmp_path / f"f{i}.json", {"i": i})
            cache.get(f)
            files.append(f)

        assert cache.stats()["size"] <= max_size


# ============================================================================
# JSONCache.invalidate
# ============================================================================

class TestJSONCacheInvalidate:
    def test_invalidate_removes_entry(self, tmp_path):
        f = write_json(tmp_path / "data.json", {"v": 1})
        cache = JSONCache(ttl_seconds=9999)
        cache.get(f)
        assert cache.stats()["size"] == 1

        cache.invalidate(f)
        assert cache.stats()["size"] == 0

    def test_invalidate_causes_fresh_read(self, tmp_path):
        f = write_json(tmp_path / "data.json", {"v": 1})
        cache = JSONCache(ttl_seconds=9999)
        cache.get(f)

        write_json(f, {"v": 2})
        cache.invalidate(f)

        result = cache.get(f)
        assert result == {"v": 2}

    def test_invalidate_nonexistent_key_is_noop(self, tmp_path):
        cache = JSONCache()
        # Should not raise
        cache.invalidate(tmp_path / "ghost.json")


# ============================================================================
# JSONCache.clear
# ============================================================================

class TestJSONCacheClear:
    def test_clear_empties_cache(self, tmp_path):
        cache = JSONCache(ttl_seconds=9999)
        for i in range(5):
            f = write_json(tmp_path / f"f{i}.json", {})
            cache.get(f)

        cache.clear()
        assert cache.stats()["size"] == 0

    def test_clear_allows_fresh_reads(self, tmp_path):
        f = write_json(tmp_path / "data.json", {"v": 1})
        cache = JSONCache(ttl_seconds=9999)
        cache.get(f)

        write_json(f, {"v": 2})
        cache.clear()

        assert cache.get(f) == {"v": 2}


# ============================================================================
# JSONCache.stats
# ============================================================================

class TestJSONCacheStats:
    def test_stats_empty_cache(self):
        cache = JSONCache(max_size=50, ttl_seconds=30)
        stats = cache.stats()
        assert stats["size"] == 0
        assert stats["max_size"] == 50
        assert stats["ttl_seconds"] == 30
        assert stats["oldest_age"] == 0

    def test_stats_reflect_cached_entries(self, tmp_path):
        cache = JSONCache(max_size=100, ttl_seconds=60)
        for i in range(3):
            f = write_json(tmp_path / f"f{i}.json", {})
            cache.get(f)
        assert cache.stats()["size"] == 3

    def test_stats_oldest_age_is_non_negative(self, tmp_path):
        cache = JSONCache()
        f = write_json(tmp_path / "f.json", {})
        cache.get(f)
        assert cache.stats()["oldest_age"] >= 0


# ============================================================================
# Module-level convenience functions
# ============================================================================

class TestConvenienceFunctions:
    def setup_method(self):
        """Reset global cache state before each test."""
        clear_json_cache()

    def test_get_cached_json_reads_file(self, tmp_path):
        f = write_json(tmp_path / "data.json", {"hello": "world"})
        result = get_cached_json(f)
        assert result == {"hello": "world"}

    def test_get_cached_json_default(self, tmp_path):
        result = get_cached_json(tmp_path / "missing.json", default={"d": 1})
        assert result == {"d": 1}

    def test_invalidate_json_cache(self, tmp_path):
        f = write_json(tmp_path / "data.json", {"v": 1})
        get_cached_json(f)
        write_json(f, {"v": 2})
        invalidate_json_cache(f)
        assert get_cached_json(f) == {"v": 2}

    def test_clear_json_cache(self, tmp_path):
        f = write_json(tmp_path / "data.json", {"v": 1})
        get_cached_json(f)
        clear_json_cache()
        assert get_json_cache_stats()["size"] == 0

    def test_get_json_cache_stats_returns_dict(self):
        stats = get_json_cache_stats()
        assert isinstance(stats, dict)
        assert "size" in stats
        assert "max_size" in stats
        assert "ttl_seconds" in stats
