"""
Unit Tests for Redis Caching Integration in TradeVerse
======================================================
Tests resilient Redis caching layer, Cache-Aside pattern, key schemas,
TTL expiration, and graceful fallback when Redis is offline or unreachable.
Run via:
    python -m unittest tests/test_redis_cache.py
"""

import os
import sys
import time
import json
import unittest
from unittest.mock import patch, MagicMock

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ["FLASK_ENV"] = "testing"

import engine
from app import app


class InMemoryMockRedis:
    """In-memory Redis mock replicating connection, TTL expiration, and JSON storage."""
    def __init__(self):
        self.data = {}
        self.expirations = {}

    def ping(self):
        return True

    def get(self, key):
        if key in self.data:
            exp = self.expirations.get(key)
            if exp is not None and time.time() > exp:
                del self.data[key]
                del self.expirations[key]
                return None
            return self.data[key]
        return None

    def setex(self, key, time_seconds, value):
        self.data[key] = str(value)
        self.expirations[key] = time.time() + float(time_seconds)
        return True

    def ttl(self, key):
        if key in self.data and key in self.expirations:
            rem = self.expirations[key] - time.time()
            return int(rem) if rem > 0 else -2
        return -2

    def delete(self, *keys):
        c = 0
        for k in keys:
            if k in self.data:
                del self.data[k]
                self.expirations.pop(k, None)
                c += 1
        return c


class BrokenMockRedis:
    """Mock simulating a disconnected, offline or hanging Redis instance."""
    def ping(self):
        raise ConnectionError("Connection refused by mock target")

    def get(self, key):
        raise ConnectionError("Connection reset by peer")

    def setex(self, key, time_seconds, value):
        raise ConnectionError("Timeout writing to socket")


class TestRedisCacheIntegration(unittest.TestCase):
    """Test suite covering Redis caching, resilience, TTLs, and API responses."""

    def setUp(self):
        self.app = app
        self.client = app.test_client()
        # Save original state
        self._orig_redis_client = engine._REDIS_CLIENT
        self._orig_price_cache = engine._PRICE_CACHE.copy()
        self._orig_candle_cache = engine._CANDLE_CACHE.copy()
        # Clean caches for isolated test runs
        engine._PRICE_CACHE.clear()
        engine._CANDLE_CACHE.clear()

    def tearDown(self):
        engine._REDIS_CLIENT = self._orig_redis_client
        engine._PRICE_CACHE = self._orig_price_cache
        engine._CANDLE_CACHE = self._orig_candle_cache

    def test_cache_key_schemas(self):
        """Verify exact cache key schemas for stocks, crypto, and history."""
        # Stock key schema: quote:stock:{SYMBOL}
        self.assertEqual(engine.get_stock_cache_key("AAPL"), "quote:stock:AAPL")
        self.assertEqual(engine.get_stock_cache_key("reliance.ns"), "quote:stock:RELIANCE.NS")
        self.assertEqual(engine.get_stock_cache_key("  msft "), "quote:stock:MSFT")

        # Crypto key schema: quote:crypto:{COIN_ID}
        self.assertEqual(engine.get_crypto_cache_key("BTC"), "quote:crypto:bitcoin")
        self.assertEqual(engine.get_crypto_cache_key("ETH"), "quote:crypto:ethereum")
        self.assertEqual(engine.get_crypto_cache_key("SOL"), "quote:crypto:solana")
        self.assertEqual(engine.get_crypto_cache_key("bitcoin"), "quote:crypto:bitcoin")

        # History key schema: history:{SYMBOL}:{INTERVAL}
        self.assertEqual(engine.get_history_cache_key("AAPL", "1y"), "history:AAPL:1y")
        self.assertEqual(engine.get_history_cache_key("BTC", "1d"), "history:BTC:1d")
        self.assertEqual(engine.get_history_cache_key("RELIANCE.NS", "15m"), "history:RELIANCE.NS:15m")

    def test_redis_connection_or_fallback(self):
        """Test is_redis_available() returns bool and never throws unhandled exceptions."""
        # With active mock
        engine._REDIS_CLIENT = InMemoryMockRedis()
        self.assertTrue(engine.is_redis_available())

        # With broken mock
        engine._REDIS_CLIENT = BrokenMockRedis()
        self.assertFalse(engine.is_redis_available())

        # With None
        engine._REDIS_CLIENT = None
        with patch.dict(os.environ, {"REDIS_URL": ""}):
            self.assertFalse(engine.is_redis_available())

    def test_setex_get_serialization(self):
        """Test JSON serialization and deserialization using redis_setex and redis_get."""
        mock_redis = InMemoryMockRedis()
        engine._REDIS_CLIENT = mock_redis

        payload = {
            "symbol": "AAPL",
            "name": "Apple",
            "price": 217.96,
            "change": 1.42,
            "currency": "USDT",
            "market": "Global",
        }
        key = "quote:stock:AAPL"
        success = engine.redis_setex(key, 30, payload)
        self.assertTrue(success)

        retrieved = engine.redis_get(key)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["symbol"], "AAPL")
        self.assertAlmostEqual(retrieved["price"], 217.96)
        self.assertEqual(retrieved["currency"], "USDT")

    def test_ttl_expiration(self):
        """Test that keys expire correctly after the designated TTL."""
        mock_redis = InMemoryMockRedis()
        engine._REDIS_CLIENT = mock_redis

        test_key = "test:ttl:sample"
        # Set 1-second TTL
        engine.redis_setex(test_key, 1, {"status": "active"})
        self.assertIsNotNone(engine.redis_get(test_key))

        # Advance expiration manually in mock
        mock_redis.expirations[test_key] = time.time() - 1
        self.assertIsNone(engine.redis_get(test_key))

    def test_cache_aside_quote_workflow(self):
        """Test complete Cache-Aside pattern for quotes: miss -> fetch & setex -> hit (<20ms)."""
        mock_redis = InMemoryMockRedis()
        engine._REDIS_CLIENT = mock_redis

        # 1. Stock Quote (TTL: 30s)
        # First call: cache miss
        quote1 = engine.fetch_custom_quote("AAPL", "stock")
        self.assertIn("price", quote1)
        self.assertFalse(quote1.get("cached", False))

        # Verify Redis key was created with SETEX
        cached_raw = mock_redis.get("quote:stock:AAPL")
        self.assertIsNotNone(cached_raw)
        parsed = json.loads(cached_raw)
        self.assertEqual(parsed["symbol"], "AAPL")

        # Second call: cache hit
        start = time.perf_counter()
        quote2 = engine.fetch_custom_quote("AAPL", "stock")
        duration_ms = (time.perf_counter() - start) * 1000
        self.assertTrue(quote2.get("cached"))
        self.assertAlmostEqual(quote2["price"], quote1["price"])
        self.assertLess(duration_ms, 20.0, f"Cache hit response too slow: {duration_ms:.2f}ms")

        # 2. Crypto Quote (TTL: 15s)
        quote_c1 = engine.fetch_custom_quote("BTC", "crypto")
        self.assertIn("price", quote_c1)
        self.assertFalse(quote_c1.get("cached", False))

        # Check key quote:crypto:bitcoin was created
        cached_crypto = mock_redis.get("quote:crypto:bitcoin")
        self.assertIsNotNone(cached_crypto)

        # Second call: cache hit
        quote_c2 = engine.fetch_custom_quote("BTC", "crypto")
        self.assertTrue(quote_c2.get("cached"))

    def test_cache_aside_candles_workflow(self):
        """Test Cache-Aside pattern for chart candles (history:{SYMBOL}:{INTERVAL} TTL: 300s)."""
        mock_redis = InMemoryMockRedis()
        engine._REDIS_CLIENT = mock_redis

        # First call: miss
        candles1 = engine.get_market_candles("AAPL", "stock", "1y")
        self.assertIsInstance(candles1, list)
        self.assertGreater(len(candles1), 0)
        self.assertFalse(getattr(candles1, "cached", False))

        # Verify Redis key was created
        cached_hist = mock_redis.get("history:AAPL:1y")
        self.assertIsNotNone(cached_hist)

        # Second call: hit (<20ms)
        start = time.perf_counter()
        candles2 = engine.get_market_candles("AAPL", "stock", "1y")
        duration_ms = (time.perf_counter() - start) * 1000
        self.assertTrue(getattr(candles2, "cached", False))
        self.assertEqual(len(candles2), len(candles1))
        self.assertLess(duration_ms, 20.0, f"Candles cache hit too slow: {duration_ms:.2f}ms")

    def test_graceful_fallback_when_redis_offline(self):
        """Test application gracefully falls back to API/baseline without crashing when Redis is down."""
        engine._REDIS_CLIENT = BrokenMockRedis()

        # Should NOT raise ConnectionError; should return valid quote
        quote = engine.fetch_custom_quote("AAPL", "stock")
        self.assertIsNotNone(quote)
        self.assertIn("price", quote)
        self.assertEqual(quote["symbol"], "AAPL")

        # Should NOT raise ConnectionError for candles
        candles = engine.get_market_candles("BTC", "crypto", "1y")
        self.assertIsNotNone(candles)
        self.assertGreater(len(candles), 0)

    def test_api_health_and_quote_endpoints(self):
        """Test /api/health, /api/cache/status, and authenticated /api/market/quote routes."""
        engine._REDIS_CLIENT = InMemoryMockRedis()

        # Health endpoint
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["redis_available"])

        # Cache status endpoint
        res_status = self.client.get("/api/cache/status")
        self.assertEqual(res_status.status_code, 200)
        st = res_status.get_json()
        self.assertTrue(st["redis_available"])

        # Authenticated market quote endpoint
        email = "redistest@tradeverse.com"
        user = engine.get_user_by_email(email)
        uid = user["id"] if user else engine.create_user("Redis Tester", email, "password123")

        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
            sess["user_email"] = email
            sess["user_profile"] = {"id": uid, "email": email, "full_name": "Redis Tester"}

        # First request (sets cache)
        r1 = self.client.get("/api/market/quote?symbol=AAPL&type=stock")
        self.assertEqual(r1.status_code, 200)
        d1 = r1.get_json()
        self.assertTrue(d1["ok"])

        # Second request (cache hit)
        r2 = self.client.get("/api/market/quote?symbol=AAPL&type=stock")
        self.assertEqual(r2.status_code, 200)
        d2 = r2.get_json()
        self.assertTrue(d2["ok"])
        self.assertTrue(d2.get("cached"))


if __name__ == "__main__":
    unittest.main()
