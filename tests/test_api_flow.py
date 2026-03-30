import tempfile
import unittest
from pathlib import Path

from src.codecommit.db import Database
from src.codecommit.service import CodeCommitService


class TestCodeCommitFlow(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "test.db"
        self.db = Database(db_path)
        self.service = CodeCommitService(self.db)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_register_pr_merge_chat(self):
        ana = self.service.register_user(
            {
                "username": "ana_dev",
                "stack": ["Python", "FastAPI"],
                "years": 4,
                "prefers_tabs": False,
                "dark_mode": True,
                "puzzle_answer": "1",
            }
        )
        bob = self.service.register_user(
            {
                "username": "bob_js",
                "stack": ["JavaScript", "Python"],
                "years": 3,
                "prefers_tabs": False,
                "dark_mode": True,
                "github_username": "bob",
            }
        )

        match = self.service.compatibility(ana["id"], bob["id"])
        self.assertGreater(match["score"], 40.0)

        pr = self.service.send_pull_request(ana["id"], bob["id"])
        merged = self.service.merge_pull_request(pr["id"])
        self.assertEqual(merged["status"], "merged")

        msg = self.service.send_message(
            chat_id=merged["chat_id"],
            sender_id=ana["id"],
            body="<script>hack()</script>hola",
        )
        self.assertNotIn("<script>", msg["body"].lower())

        messages = self.service.list_messages(merged["chat_id"])
        self.assertEqual(len(messages), 1)


if __name__ == "__main__":
    unittest.main()

