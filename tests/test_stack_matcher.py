import unittest

from src.codecommit.stack_matcher import DevMatcher


class TestDevMatchLogic(unittest.TestCase):
    def setUp(self):
        self.matcher = DevMatcher()
        self.dev_principal = {
            "stack": ["Python", "JavaScript", "SQL"],
            "years": 3,
            "prefers_tabs": False,
            "dark_mode": True,
        }

    def test_high_compatibility(self):
        dev_compatible = {
            "stack": ["Python", "JavaScript"],
            "years": 4,
            "prefers_tabs": False,
            "dark_mode": True,
        }
        score = self.matcher.calculate_compatibility(self.dev_principal, dev_compatible)
        self.assertGreater(score, 60.0)

    def test_zero_compatibility(self):
        dev_opuesto = {
            "stack": ["COBOL", "Fortran"],
            "years": 30,
            "prefers_tabs": True,
            "dark_mode": False,
        }
        score = self.matcher.calculate_compatibility(self.dev_principal, dev_opuesto)
        self.assertLess(score, 20.0)


if __name__ == "__main__":
    unittest.main()

