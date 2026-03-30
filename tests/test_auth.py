import time
import unittest

from src.codecommit.auth import create_jwt, decode_jwt, hash_password, verify_password


class TestAuth(unittest.TestCase):
    def test_password_hash_and_verify(self):
        encoded = hash_password("myS3cretPass!")
        self.assertTrue(verify_password("myS3cretPass!", encoded))
        self.assertFalse(verify_password("wrong-pass", encoded))

    def test_jwt_create_and_decode(self):
        token = create_jwt({"sub": 10, "username": "ana"}, "secret", ttl_seconds=5)
        payload = decode_jwt(token, "secret")
        self.assertEqual(payload["sub"], 10)
        self.assertEqual(payload["username"], "ana")

    def test_jwt_expired(self):
        token = create_jwt({"sub": 10}, "secret", ttl_seconds=1)
        time.sleep(1.1)
        with self.assertRaisesRegex(ValueError, "expirado"):
            decode_jwt(token, "secret")


if __name__ == "__main__":
    unittest.main()

