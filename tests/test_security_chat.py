import unittest

from src.codecommit.security import sanitize_chat_message


class TestChatSecurity(unittest.TestCase):
    def test_xss_sanitization(self):
        payload = '<script>alert("pwnd")</script><b>hola</b>'
        cleaned = sanitize_chat_message(payload)
        self.assertNotIn("<script>", cleaned.lower())
        self.assertIn("&lt;b&gt;hola&lt;/b&gt;", cleaned)

    def test_sql_injection_pattern_cleaning(self):
        payload = "' OR 1=1; DROP TABLE users; --"
        cleaned = sanitize_chat_message(payload)
        self.assertNotIn("DROP TABLE", cleaned.upper())
        self.assertNotIn("--", cleaned)


if __name__ == "__main__":
    unittest.main()

