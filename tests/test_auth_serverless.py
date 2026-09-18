"""Ponytail runnable check: Verify serverless session restoration, vault cookies, and 401 API guards."""

import sys
from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import app
from database import get_database_path, get_user_by_email


def run_checks():
    client = app.test_client()

    # 1. Unauthenticated API returns 401 JSON, not HTML redirect
    res = client.get("/api/chart/crypto/BTC", headers={"Accept": "application/json"})
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"
    json_data = res.get_json()
    assert json_data and json_data.get("error") == "unauthorized", f"Invalid json: {json_data}"

    # 2. Register account and verify vault cookie
    email = "test_autocheck@example.com"
    pwd = "CheckPassword123"
    res = client.post("/register", data={
        "full_name": "Autocheck User",
        "email": email,
        "password": pwd,
        "confirm_password": pwd,
    }, follow_redirects=False)
    assert res.status_code == 302, f"Expected 302 on register, got {res.status_code}"
    assert "tv_account_vault" in res.headers.get("Set-Cookie", "")

    # 3. Simulate container switch by clearing user from SQLite
    with sqlite3.connect(str(get_database_path())) as conn:
        conn.execute("DELETE FROM users WHERE email = ?", (email,))
        conn.commit()

    assert get_user_by_email(email) is None, "User should be absent in simulated fresh container"

    # 4. Tab switch / request on new container automatically restores session
    res = client.get("/dashboard")
    assert res.status_code == 200, f"Expected 200 on tab switch, got {res.status_code}"
    assert get_user_by_email(email) is not None, "User should be auto-restored in DB"

    # 5. Logout and simulate login on fresh container from vault cookie
    client.get("/logout")
    with sqlite3.connect(str(get_database_path())) as conn:
        conn.execute("DELETE FROM users WHERE email = ?", (email,))
        conn.commit()

    assert get_user_by_email(email) is None

    res = client.post("/login", data={"email": email, "password": pwd}, follow_redirects=False)
    assert res.status_code == 302, f"Expected 302 on login, got {res.status_code}"
    assert res.headers["Location"] == "/dashboard"
    assert get_user_by_email(email) is not None, "User should be restored from vault cookie on login"

    # Clean up test user
    with sqlite3.connect(str(get_database_path())) as conn:
        conn.execute("DELETE FROM users WHERE email = ?", (email,))
        conn.commit()

    print("All serverless auth checks passed successfully.")


if __name__ == "__main__":
    run_checks()
