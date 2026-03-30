import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from src.codecommit.github_client import fetch_top_languages


class FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestGithubClient(unittest.TestCase):
    def test_fetch_top_languages_success(self):
        body = (
            b'[{"language":"Python"},{"language":"Python"},{"language":"JavaScript"},{"language":null}]'
        )
        with patch("src.codecommit.github_client.request.urlopen", return_value=FakeResponse(body)):
            langs = fetch_top_languages("alice")
            self.assertEqual(langs[0], "Python")
            self.assertIn("JavaScript", langs)

    def test_fetch_top_languages_403(self):
        err = HTTPError(
            url="https://api.github.com/users/alice/repos",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=BytesIO(b"{}"),
        )
        with patch("src.codecommit.github_client.request.urlopen", side_effect=err):
            with self.assertRaisesRegex(RuntimeError, "403"):
                fetch_top_languages("alice")


if __name__ == "__main__":
    unittest.main()

