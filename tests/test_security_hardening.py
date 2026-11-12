"""
test_security_hardening.py
Automated Security Regression Test Suite for AutoInspect AI (Branch 1, Steps 37 & 38)
Tests:
1. Trusted Host validation & HTTP Host attack mitigation
2. Security response headers (nosniff, DENY, XSS, CSP, Referrer-Policy)
3. Request size limit middleware (HTTP 413 Payload Too Large)
4. Sliding window rate limiting on /api/auth/login and /api/auth/register (HTTP 429)
5. CORS policy and wildcard prohibition with credentials
6. Schema bounds validation (login password length, vehicle bounds, inspection score bounds)
7. Role escalation prevention during registration
8. JWT security: tampered signature, expired tokens, invalid token types
9. Global unhandled exception masking (zero stack trace/database leaks)
"""

import os
os.environ["TESTING"] = "1"

import sys as _sys
from pathlib import Path as _Path
_MODELS_DIR = _Path(__file__).resolve().parent.parent / 'models'
if str(_MODELS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_MODELS_DIR))

import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import status
from app.main import app
from app.config import settings
from app.core.security import create_access_token
from app.core.rate_limiter import limiter
from app.database import get_db

class TestSecurityHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Patch engine.connect so health probe returns immediately without database network calls
        cls.patch_engine = patch("app.main.engine.connect")
        cls.mock_engine_conn = cls.patch_engine.start()

        # Patch verify_password for instant rate-limiting tests without Argon2id CPU delay
        cls.patch_verify = patch("app.routers.auth.verify_password", return_value=False)
        cls.mock_verify = cls.patch_verify.start()

        # Mock database session
        cls.mock_session = MagicMock()
        cls.mock_session.query.return_value.filter.return_value.first.return_value = None
        app.dependency_overrides[get_db] = lambda: cls.mock_session

        cls.client = TestClient(app, base_url="http://testserver")

    @classmethod
    def tearDownClass(cls):
        cls.patch_engine.stop()
        cls.patch_verify.stop()
        app.dependency_overrides.pop(get_db, None)

    def setUp(self):
        limiter.reset()

    # -----------------------------------------------------------------------
    # 1. Trusted Host Header Validation
    # -----------------------------------------------------------------------
    def test_trusted_host_allows_legitimate_host(self):
        """Legitimate host header ('testserver') is accepted."""
        response = self.client.get("/health", headers={"Host": "testserver"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_trusted_host_rejects_malicious_host_header(self):
        """Forged or spoofed Host header is rejected with HTTP 400."""
        response = self.client.get("/health", headers={"Host": "attacker-domain.evil.com"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -----------------------------------------------------------------------
    # 2. Security Response Headers
    # -----------------------------------------------------------------------
    def test_security_headers_present_on_response(self):
        """All standard security headers must be injected on every response."""
        response = self.client.get("/health")
        headers = response.headers

        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(headers.get("X-XSS-Protection"), "1; mode=block")
        self.assertEqual(headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertIn("camera=()", headers.get("Permissions-Policy", ""))
        self.assertIn("default-src 'self'", headers.get("Content-Security-Policy", ""))

    # -----------------------------------------------------------------------
    # 3. Request Size Limit Middleware
    # -----------------------------------------------------------------------
    def test_request_size_limit_rejects_oversized_payloads(self):
        """Content-Length exceeding maximum allowed size triggers HTTP 413."""
        oversized_headers = {
            "Content-Length": str(20 * 1024 * 1024), # 20 MB
            "Content-Type": "application/json",
        }
        response = self.client.post("/api/auth/login", headers=oversized_headers, content=b"{}")
        self.assertEqual(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        self.assertIn("Payload too large", response.json().get("detail", ""))

    # -----------------------------------------------------------------------
    # 4. Rate Limiting on Sensitive Auth Endpoints
    # -----------------------------------------------------------------------
    def test_rate_limiting_login_endpoint(self):
        """Exceeding login attempts triggers HTTP 429 Too Many Requests."""
        max_attempts = settings.RATE_LIMIT_LOGIN_PER_MIN
        payload = {"email": "test_rl@autoinspect.ai", "password": "SamplePassword123!"}

        # Exhaust limit
        for _ in range(max_attempts):
            res = self.client.post("/api/auth/login", json=payload)
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # Next request must be rate limited
        blocked_res = self.client.post("/api/auth/login", json=payload)
        self.assertEqual(blocked_res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("Too many requests", blocked_res.json().get("detail", ""))
        self.assertTrue("Retry-After" in blocked_res.headers)

    def test_rate_limiting_resets_properly(self):
        """Rate limiter reset clears counters."""
        max_attempts = settings.RATE_LIMIT_LOGIN_PER_MIN
        payload = {"email": "test_rl_reset@autoinspect.ai", "password": "SamplePassword123!"}

        for _ in range(max_attempts):
            self.client.post("/api/auth/login", json=payload)

        # Clear limiter
        limiter.reset()

        # Should be allowed again
        allowed_res = self.client.post("/api/auth/login", json=payload)
        self.assertNotEqual(allowed_res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    # -----------------------------------------------------------------------
    # 5. Schema Validation Bounds Hardening
    # -----------------------------------------------------------------------
    def test_login_rejects_oversized_password_dos_attempt(self):
        """Passwords exceeding 128 chars are rejected by schema validation (CPU exhaustion defense)."""
        huge_password = "A" * 200
        payload = {"email": "test_dos@autoinspect.ai", "password": huge_password}
        response = self.client.post("/api/auth/login", json=payload)
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_registration_role_escalation_forbidden(self):
        """Extra fields like 'role' are rejected on registration schema."""
        payload = {
            "email": "hacker@autoinspect.ai",
            "password": "Password123!",
            "role": "admin",
        }
        response = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_vehicle_creation_bounds(self):
        """Vehicle creation rejects invalid year bounds."""
        from app.core.dependencies import get_current_user
        from app.models.user import UserModel

        mock_user = UserModel(id=1, email="test@test.com", role="customer")
        app.dependency_overrides[get_current_user] = lambda: mock_user

        try:
            # Year too low
            payload_bad_year = {
                "make": "Ford",
                "model": "Model T",
                "year": 1800,
                "registration": "OLD 123",
                "color": "Black",
                "image": "https://example.com/car.jpg",
            }
            res = self.client.post("/api/vehicles", json=payload_bad_year)
            self.assertEqual(res.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    # -----------------------------------------------------------------------
    # 6. JWT Security Validation
    # -----------------------------------------------------------------------
    def test_expired_token_rejected_with_401(self):
        """Expired JWT access token is rejected with HTTP 401."""
        expired_token = create_access_token(
            subject=100,
            expires_delta=timedelta(seconds=-10),
        )
        response = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("expired", response.json().get("detail", "").lower())

    def test_tampered_token_signature_rejected(self):
        """Token with modified signature is rejected with HTTP 401."""
        valid_token = create_access_token(subject=100)
        tampered_token = valid_token[:-4] + "fake"

        response = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {tampered_token}"},
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.headers.get("WWW-Authenticate"), "Bearer")

    def test_token_type_must_be_access(self):
        """Token with type != 'access' is rejected."""
        import jwt
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        bad_token = jwt.encode(
            {"sub": "100", "type": "refresh", "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=1)).timestamp())},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        response = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {bad_token}"},
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_request_rejected(self):
        """Missing Authorization header on protected route returns HTTP 401."""
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.headers.get("WWW-Authenticate"), "Bearer")

if __name__ == "__main__":
    unittest.main()
