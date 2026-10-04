"""
Unit and Integration Test Suite:
1. Collapsible offcanvas Workspace sidebar drawer & backdrop
2. Authentic vector brand logos for Global & Indian stocks and Crypto coins
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["FLASK_ENV"] = "testing"

from app import app
import engine


class TestSidebarAndBrandSymbols(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        email = "drawer_test@tradeverse.com"
        u = engine.get_user_by_email(email)
        if not u:
            cls.uid = engine.create_user("Drawer Tester", email, "password123")
        else:
            cls.uid = u["id"]
        cls.email = email

    def setUp(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = self.uid
            sess["user_email"] = self.email
            sess["user_profile"] = {"id": self.uid, "email": self.email, "full_name": "Drawer Tester"}

    def test_sidebar_drawer_markup(self):
        """Verify collapsible sidebar drawer elements are present on all core views."""
        for path in ["/dashboard", "/stocks?market=India", "/stocks?market=Global", "/crypto", "/portfolio"]:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200)
            self.assertIn(b"workspace-menu-toggle", res.data)
            self.assertIn(b"sidebar-backdrop", res.data)
            self.assertIn(b"sidebar-close-btn", res.data)
            self.assertIn(b"id=\"sidebar-nav\"", res.data)

    def test_stock_brand_vector_svgs(self):
        """Verify all major Indian and Global stocks have authentic SVG brand symbols."""
        stocks = [
            ("RELIANCE.NS", "stock"),
            ("TCS.NS", "stock"),
            ("INFY.NS", "stock"),
            ("HDFCBANK.NS", "stock"),
            ("ICICIBANK.NS", "stock"),
            ("TATAMOTORS.NS", "stock"),
            ("SBIN.NS", "stock"),
            ("AAPL", "stock"),
            ("MSFT", "stock"),
            ("NVDA", "stock"),
            ("TSLA", "stock"),
            ("AMZN", "stock"),
            ("GOOGL", "stock"),
            ("META", "stock"),
        ]
        for symbol, asset_type in stocks:
            svg = str(engine.get_asset_icon_svg(asset_type, symbol))
            self.assertTrue(svg.startswith("<svg"))
            self.assertIn("viewBox=\"0 0 32 32\"", svg)
            # Ensure generic monogram fallback is NOT used
            self.assertNotIn("rx=\"8\"", svg, f"Fallback monogram returned for {symbol}")

    def test_crypto_brand_vector_svgs(self):
        """Verify cryptocurrencies have authentic SVG coin symbols."""
        cryptos = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "MATIC"]
        for symbol in cryptos:
            svg = str(engine.get_asset_icon_svg("crypto", symbol))
            self.assertTrue(svg.startswith("<svg"))
            self.assertIn("viewBox=\"0 0 32 32\"", svg)
            self.assertNotIn("rx=\"8\"", svg, f"Fallback monogram returned for {symbol}")


if __name__ == "__main__":
    unittest.main()
