import hashlib
import hmac
import os
import base64
from typing import Any, Dict

import jwt  # PyJWT


# ─── Password hashing (PBKDF2-SHA256, unchanged) ──────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def hash_password(password: str, iterations: int = 120_000) -> str:
    salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64url_encode(salt)}${_b64url_encode(hashed)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations_raw, salt_b64, hash_b64 = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = _b64url_decode(salt_b64)
        expected = _b64url_decode(hash_b64)
    except (ValueError, TypeError):
        return False

    computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(computed, expected)


# ─── JWT (PyJWT – HS256) ──────────────────────────────────────────────────────

def create_jwt(payload: Dict[str, Any], secret: str, ttl_seconds: int = 3600) -> str:
    """Encode a JWT with HS256 and an 'exp' claim using PyJWT."""
    import time

    full_payload = dict(payload)
    full_payload["exp"] = int(time.time()) + ttl_seconds

    return jwt.encode(full_payload, secret, algorithm="HS256")


def decode_jwt(token: str, secret: str) -> Dict[str, Any]:
    """Decode and verify a JWT. Raises ValueError on any failure."""
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
        return payload
    except jwt.ExpiredSignatureError as err:
        raise ValueError("JWT expirado.") from err
    except jwt.InvalidTokenError as err:
        raise ValueError(f"Token JWT inválido: {err}") from err
