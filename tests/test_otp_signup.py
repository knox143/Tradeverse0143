"""
Test 4-Digit OTP Signup Verification Flow
=========================================
Tests that:
1. Registration with an email sends a 4-digit OTP and does NOT create the account yet.
2. An invalid OTP is rejected and the user remains absent from the DB.
3. The valid 4-digit OTP creates the account, provisions starting wallet funds,
   and logs the user in.
"""

import sys
from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import app
from database import get_database_path, get_user_by_email, get_wallet, STARTING_INR_BALANCE, STARTING_USDT_BALANCE


def run_checks():
    client = app.test_client()
    email = "trader_otp@gmail.com"
    pwd = "TraderPassword123!"

    # Clean up test user if left previously
    with sqlite3.connect(str(get_database_path())) as conn:
        conn.execute("DELETE FROM users WHERE email = ?", (email,))
        conn.commit()

    assert get_user_by_email(email) is None

    # Step 1: Submit Registration Form
    res_reg = client.post(
        "/register",
        data={
            "full_name": "OTP Trader",
            "email": email,
            "password": pwd,
            "confirm_password": pwd,
        },
        follow_redirects=False,
    )
    # Must redirect to /verify-otp
    assert res_reg.status_code == 302, f"Expected 302, got {res_reg.status_code}"
    assert "/verify-otp" in res_reg.headers.get("Location", ""), f"Location should be /verify-otp, got {res_reg.headers.get('Location')}"

    # Verify user is NOT yet created in database!
    assert get_user_by_email(email) is None, "CRITICAL: Account must NOT be created before OTP verification!"
    print("SUCCESS Step 1: Registration redirected to /verify-otp and user is NOT yet in DB.")

    # Step 2: Try submitting an incorrect 4-digit OTP
    res_wrong_otp = client.post(
        "/verify-otp",
        data={"otp": "0000"},
        follow_redirects=True,
    )
    assert res_wrong_otp.status_code == 200
    assert b"Invalid 4-digit verification code" in res_wrong_otp.data or b"Invalid" in res_wrong_otp.data
    assert get_user_by_email(email) is None, "Account must NOT be created with invalid OTP!"
    print("SUCCESS Step 2: Invalid OTP was correctly rejected.")

    # Retrieve pending OTP from session
    with client.session_transaction() as sess:
        pending = sess.get("pending_signup")
        assert pending is not None, "Pending signup must exist in session"
        correct_otp = pending.get("otp")
        assert len(correct_otp) == 4, f"OTP must be 4 digits, got {correct_otp}"
        assert correct_otp.isdigit(), f"OTP must be numeric, got {correct_otp}"

    # Step 3: Submit the correct 4-digit OTP
    res_verify = client.post(
        "/verify-otp",
        data={"otp": correct_otp},
        follow_redirects=False,
    )
    assert res_verify.status_code == 302, f"Expected 302 redirect to dashboard, got {res_verify.status_code}"
    assert "/dashboard" in res_verify.headers.get("Location", "")

    # Step 4: Verify user is now created in DB!
    user = get_user_by_email(email)
    assert user is not None, "User should now exist in DB after valid OTP!"
    assert user["full_name"] == "OTP Trader"

    # Step 5: Verify virtual wallet balances were credited
    wallet = get_wallet(user["id"])
    assert wallet["inr"] == STARTING_INR_BALANCE, f"Expected {STARTING_INR_BALANCE}, got {wallet['inr']}"
    assert wallet["usdt"] == STARTING_USDT_BALANCE, f"Expected {STARTING_USDT_BALANCE}, got {wallet['usdt']}"
    print("SUCCESS Step 3-5: Correct OTP created the account and funded INR 10,00,000 & 10,000 USDT.")

    print("\nALL 4-DIGIT OTP SIGNUP CHECKS PASSED 100% PERFECTLY!")


if __name__ == "__main__":
    run_checks()
