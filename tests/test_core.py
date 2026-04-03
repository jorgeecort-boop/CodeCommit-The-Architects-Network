import pytest
import os
import sys

src_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
sys.path.insert(0, src_path)

os.environ["CODECOMMIT_JWT_SECRET"] = "test-secret-for-tests-only"

from codecommit.auth import create_jwt, decode_jwt, hash_password, verify_password


class TestAuth:
    def test_hash_password(self):
        pwd = "securepassword123"
        hashed = hash_password(pwd)
        assert hashed != pwd
        assert verify_password(pwd, hashed)
        assert not verify_password("wrongpassword", hashed)

    def test_jwt_create_and_verify(self):
        secret = "test-secret-for-tests-only"
        payload = {"sub": "123", "username": "testuser"}
        token = create_jwt(payload, secret, ttl_seconds=3600)
        assert token
        decoded = decode_jwt(token, secret)
        assert decoded["sub"] == "123"
        assert decoded["username"] == "testuser"

    def test_jwt_invalid_token(self):
        secret = "test-secret-for-tests-only"
        with pytest.raises(Exception):
            decode_jwt("invalid.token.here", secret)

    def test_jwt_wrong_secret(self):
        payload = {"sub": "123"}
        token = create_jwt(payload, "secret1", ttl_seconds=3600)
        with pytest.raises(Exception):
            decode_jwt(token, "secret2")


class TestServiceValidation:
    def test_username_validation(self):
        import tempfile
        from codecommit.service import CodeCommitService
        from codecommit.db import Database
        from pathlib import Path
        
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db = Database(Path(f.name))
            service = CodeCommitService(db)
            
            with pytest.raises(Exception, match="username debe tener al menos 3"):
                service.register_user({
                    "username": "ab",
                    "stack": ["Python"],
                    "years": 1,
                    "password_hash": "hash",
                    "puzzle_answer": "1",
                    "prefers_tabs": False,
                    "dark_mode": True
                })

    def test_stack_validation(self):
        import tempfile
        from codecommit.service import CodeCommitService
        from codecommit.db import Database
        from pathlib import Path
        
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db = Database(Path(f.name))
            service = CodeCommitService(db)
            
            with pytest.raises(Exception, match="stack debe ser una lista"):
                service.register_user({
                    "username": "validuser",
                    "stack": [],
                    "years": 1,
                    "password_hash": "hash",
                    "puzzle_answer": "1",
                    "prefers_tabs": False,
                    "dark_mode": True
                })

    def test_years_validation(self):
        import tempfile
        from codecommit.service import CodeCommitService
        from codecommit.db import Database
        from pathlib import Path
        
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db = Database(Path(f.name))
            service = CodeCommitService(db)
            
            with pytest.raises(Exception, match="years fuera de rango"):
                service.register_user({
                    "username": "validuser",
                    "stack": ["Python"],
                    "years": 100,
                    "password_hash": "hash",
                    "puzzle_answer": "1",
                    "prefers_tabs": False,
                    "dark_mode": True
                })


class TestStackMatcher:
    def test_exact_match(self):
        from codecommit.stack_matcher import DevMatcher
        matcher = DevMatcher()
        
        dev1 = {"stack": ["Python", "JavaScript"], "years": 5}
        dev2 = {"stack": ["Python", "JavaScript"], "years": 5}
        
        score = matcher.calculate_compatibility(dev1, dev2)
        assert score >= 50

    def test_no_common_stack(self):
        from codecommit.stack_matcher import DevMatcher
        matcher = DevMatcher()
        
        dev1 = {"stack": ["Python"], "years": 3}
        dev2 = {"stack": ["Rust"], "years": 3}
        
        score = matcher.calculate_compatibility(dev1, dev2)
        assert score < 50

    def test_suggest_matches(self):
        from codecommit.stack_matcher import DevMatcher
        matcher = DevMatcher()
        
        user = {"id": 1, "stack": ["Python", "Go"], "years": 5}
        candidates = [
            {"id": 2, "stack": ["Python"], "years": 5},
            {"id": 3, "stack": ["Rust"], "years": 2},
        ]
        
        results = matcher.suggest_matches(user, candidates, limit=2)
        assert len(results) <= 2
        assert results[0]["id"] == 2


class TestDatabase:
    def test_create_and_get_user(self):
        import tempfile
        from codecommit.db import Database
        from pathlib import Path
        
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db = Database(Path(f.name))
            user_id = db.create_user({
                "username": "testuser",
                "password_hash": "hashed",
                "stack": ["Python", "Go"],
                "years": 5,
                "prefers_tabs": False,
                "dark_mode": True
            })
            
            user = db.get_user(user_id)
            assert user["username"] == "testuser"
            assert user["stack"] == ["Python", "Go"]

    def test_duplicate_username(self):
        import tempfile
        from codecommit.db import Database
        from pathlib import Path
        
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db = Database(Path(f.name))
            db.create_user({
                "username": "duplicate",
                "password_hash": "hash1",
                "stack": ["Python"],
                "years": 3,
                "prefers_tabs": False,
                "dark_mode": True
            })
            
            with pytest.raises(Exception):
                db.create_user({
                    "username": "duplicate",
                    "password_hash": "hash2",
                    "stack": ["Go"],
                    "years": 5,
                    "prefers_tabs": False,
                    "dark_mode": True
                })
        
        with pytest.raises(Exception):
            db.create_user({
                "username": "duplicate",
                "password_hash": "hash2",
                "stack": ["Go"],
                "years": 5,
                "prefers_tabs": False,
                "dark_mode": True
            })


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
