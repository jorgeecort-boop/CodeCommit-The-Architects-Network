import tempfile
import unittest
from pathlib import Path

from src.codecommit.db import Database
from src.codecommit.service import CodeCommitService


class TestUserImages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "db.sqlite")
        self.service = CodeCommitService(self.db)
        self.user = self.service.register_user(
            {
                "username": "img_dev",
                "stack": ["Python"],
                "years": 2,
                "puzzle_answer": "1",
            }
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_update_user_images(self):
        self.db.update_user_images(self.user["id"], avatar_url="/media/a.png", setup_url="/media/s.png")
        updated = self.db.get_user(self.user["id"])
        self.assertEqual(updated["avatar_url"], "/media/a.png")
        self.assertEqual(updated["setup_url"], "/media/s.png")


if __name__ == "__main__":
    unittest.main()

