import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict


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


def create_jwt(payload: Dict[str, Any], secret: str, ttl_seconds: int = 3600) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    full_payload = dict(payload)
    full_payload["exp"] = int(time.time()) + ttl_seconds

    header_b64 = _b64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    payload_b64 = _b64url_encode(
        json.dumps(full_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    unsigned = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), unsigned, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def decode_jwt(token: str, secret: str) -> Dict[str, Any]:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError as err:
        raise ValueError("Token JWT mal formado.") from err

    unsigned = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(secret.encode("utf-8"), unsigned, hashlib.sha256).digest()
    got_sig = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected_sig, got_sig):
        raise ValueError("Firma JWT invalida.")

    payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    exp = int(payload.get("exp", 0))
    if int(time.time()) >= exp:
        raise ValueError("JWT expirado.")
    return payload

