"""
Unit and Integration Test Suite:
1. Default Demo Credentials (admin / admin@123)
2. Logout option in topbar and profile
3. Sensitive data redaction in logs
4. Dependency vulnerability hardening
"""
import os
import sys
import unittest
import logging
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["FLASK_ENV"] = "testing"

from app import app
import engine


class TestDemoAuthLogoutSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine.init_db()
        engine.seed_demo_user()
        cls.client = app.test_client()

    def test_admin_demo_credentials_login(self):
        """Verify username 'admin' with password 'admin@123' logs in successfully."""
        res = self.client.post("/login", data={
            "email": "admin",
            "password": "admin@123"
        }, follow_redirects=False)

        self.assertEqual(res.status_code, 302)
        self.assertIn("/dashboard", res.headers.get("Location", ""))

        # Verify admin wallet balance
        admin_user = engine.get_user_by_email("admin")
        self.assertIsNotNone(admin_user)
        wallet = engine.get_wallet(admin_user["id"])
        self.assertEqual(wallet["inr"], 1000000.0)
        self.assertEqual(wallet["usdt"], 10000.0)

    def test_admin_email_alias_login(self):
        """Verify 'admin@tradeverse.com' with password 'admin@123' also works."""
        res = self.client.post("/login", data={
            "email": "admin@tradeverse.com",
            "password": "admin@123"
        }, follow_redirects=False)

        self.assertEqual(res.status_code, 302)
        self.assertIn("/dashboard", res.headers.get("Location", ""))

    def test_logout_option_and_route(self):
        """Verify /logout clears session and cookies, and topbar contains logout button."""
        # 1. Login first
        login_res = self.client.post("/login", data={
            "email": "admin",
            "password": "admin@123"
        }, follow_redirects=True)
        self.assertEqual(login_res.status_code, 200)

        # 2. Check topbar has logout button
        self.assertIn(b"topbar-logout-btn", login_res.data)
        self.assertIn(b"href=\"/logout\"", login_res.data)

        # 3. Check profile page has signout option
        prof_res = self.client.get("/profile")
        self.assertEqual(prof_res.status_code, 200)
        self.assertIn(b"Sign out of TradeVerse", prof_res.data)
        self.assertIn(b"href=\"/logout\"", prof_res.data)

        # 4. Perform logout
        logout_res = self.client.get("/logout", follow_redirects=False)
        self.assertEqual(logout_res.status_code, 302)
        self.assertIn("/login", logout_res.headers.get("Location", ""))

        # Confirm session is cleared
        dash_res = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(dash_res.status_code, 302)
        self.assertIn("/login", dash_res.headers.get("Location", ""))

    def test_sensitive_data_log_redaction(self):
        """Verify sensitive information is scrubbed out of logs."""
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.addFilter(engine.SensitiveDataFilter())

        test_logger = logging.getLogger("test.sensitive")
        test_logger.setLevel(logging.INFO)
        test_logger.addHandler(handler)

        # Emit log messages with secrets
        test_logger.info("User login attempt with password='secretPassword123' and token='db17ushr01qhkqh8lr2g'")
        test_logger.info("Verification code: 8492 sent to user@example.com")
        test_logger.info("Connected to postgres://user:myDbPassword123@localhost:5432/db")

        output = log_stream.getvalue()
        self.assertNotIn("secretPassword123", output)
        self.assertNotIn("db17ushr01qhkqh8lr2g", output)
        self.assertNotIn("8492", output)
        self.assertNotIn("myDbPassword123", output)
        self.assertIn("[REDACTED]", output)


if __name__ == "__main__":
    unittest.main()
