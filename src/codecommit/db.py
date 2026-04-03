import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import IntegrityError
from typing import Any, Dict, Iterable, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: Path):
        self.db_path = str(db_path)
        self._ensure_schema()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def ensure_schema(self):
        self._ensure_schema()

    def _ensure_schema(self):
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL DEFAULT '',
                    stack_json TEXT NOT NULL,
                    years INTEGER NOT NULL,
                    prefers_tabs INTEGER NOT NULL DEFAULT 0,
                    dark_mode INTEGER NOT NULL DEFAULT 1,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    github_username TEXT,
                    last_github_activity TEXT,
                    usd_balance REAL NOT NULL DEFAULT 100.0,
                    karma_score INTEGER NOT NULL DEFAULT 0,
                    avatar_url TEXT,
                    setup_url TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            columns = {
                row["name"] for row in cur.execute("PRAGMA table_info(users)").fetchall()
            }
            if "password_hash" not in columns:
                cur.execute(
                    "ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''"
                )
            if "avatar_url" not in columns:
                cur.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
            if "setup_url" not in columns:
                cur.execute("ALTER TABLE users ADD COLUMN setup_url TEXT")
            if "last_github_activity" not in columns:
                cur.execute("ALTER TABLE users ADD COLUMN last_github_activity TEXT")
            if "is_admin" not in columns:
                cur.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
            if "usd_balance" not in columns:
                cur.execute("ALTER TABLE users ADD COLUMN usd_balance REAL NOT NULL DEFAULT 100.0")
            if "karma_score" not in columns:
                cur.execute("ALTER TABLE users ADD COLUMN karma_score INTEGER NOT NULL DEFAULT 0")
            if "current_streak" not in columns:
                cur.execute("ALTER TABLE users ADD COLUMN current_streak INTEGER NOT NULL DEFAULT 0")
            if "longest_streak" not in columns:
                cur.execute("ALTER TABLE users ADD COLUMN longest_streak INTEGER NOT NULL DEFAULT 0")
            if "last_active_date" not in columns:
                cur.execute("ALTER TABLE users ADD COLUMN last_active_date TEXT")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pull_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id INTEGER NOT NULL,
                    to_user_id INTEGER NOT NULL,
                    bounty_id INTEGER,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    merged_at TEXT,
                    UNIQUE(from_user_id, to_user_id),
                    FOREIGN KEY(from_user_id) REFERENCES users(id),
                    FOREIGN KEY(to_user_id) REFERENCES users(id),
                    FOREIGN KEY(bounty_id) REFERENCES bounties(id)
                )
                """
            )
            pr_columns = {
                row["name"] for row in cur.execute("PRAGMA table_info(pull_requests)").fetchall()
            }
            if "bounty_id" not in pr_columns:
                cur.execute("ALTER TABLE pull_requests ADD COLUMN bounty_id INTEGER")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_a_id INTEGER NOT NULL,
                    user_b_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_a_id, user_b_id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    sender_id INTEGER NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(chat_id) REFERENCES chats(id),
                    FOREIGN KEY(sender_id) REFERENCES users(id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_scratchpads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL UNIQUE,
                    content TEXT NOT NULL DEFAULT '',
                    updated_by INTEGER,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(chat_id) REFERENCES chats(id),
                    FOREIGN KEY(updated_by) REFERENCES users(id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS bounties (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creator_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    reward_amount REAL NOT NULL,
                    reward_currency TEXT NOT NULL DEFAULT 'USD',
                    tech_stack TEXT NOT NULL,
                    status TEXT NOT NULL,
                    assigned_user_id INTEGER,
                    escrow_locked INTEGER NOT NULL DEFAULT 0,
                    paid_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(creator_id) REFERENCES users(id),
                    FOREIGN KEY(assigned_user_id) REFERENCES users(id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS news_feed (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS showcase (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    price REAL,
                    demo_url TEXT,
                    image_url TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS resources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    link TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    helpful_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS snippets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    language TEXT NOT NULL,
                    code TEXT NOT NULL,
                    likes_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS endorsements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id INTEGER NOT NULL,
                    to_user_id INTEGER NOT NULL,
                    skill TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(from_user_id) REFERENCES users(id),
                    FOREIGN KEY(to_user_id) REFERENCES users(id),
                    UNIQUE(from_user_id, to_user_id, skill)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS clusters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL,
                    creator_id INTEGER NOT NULL,
                    min_karma_required INTEGER NOT NULL DEFAULT 0,
                    tech_stack_focus TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(creator_id) REFERENCES users(id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cluster_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    joined_at TEXT NOT NULL,
                    UNIQUE(cluster_id, user_id),
                    FOREIGN KEY(cluster_id) REFERENCES clusters(id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS feed_interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id INTEGER NOT NULL,
                    interaction_type TEXT NOT NULL,
                    fork_cluster_id INTEGER,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, target_type, target_id, interaction_type),
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(fork_cluster_id) REFERENCES clusters(id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS feed_threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id INTEGER NOT NULL,
                    parent_thread_id INTEGER,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(parent_thread_id) REFERENCES feed_threads(id)
                )
                """
            )

    def create_user(self, payload: Dict[str, Any]) -> int:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO users (
                    username, password_hash, stack_json, years, prefers_tabs, dark_mode, is_admin,
                    github_username, last_github_activity, usd_balance, karma_score, avatar_url, setup_url, created_at,
                    current_streak, longest_streak, last_active_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["username"],
                    payload.get("password_hash", ""),
                    json.dumps(payload["stack"]),
                    payload["years"],
                    int(payload["prefers_tabs"]),
                    int(payload["dark_mode"]),
                    int(bool(payload.get("is_admin", False))),
                    payload.get("github_username"),
                    payload.get("last_github_activity"),
                    float(payload.get("usd_balance", 100.0)),
                    int(payload.get("karma_score", 0)),
                    payload.get("avatar_url"),
                    payload.get("setup_url"),
                    payload.get("created_at", datetime.now().isoformat()),
                    0, 0, None
                ),
            )
            return int(cur.lastrowid)

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                return None
            return self._row_to_user(row)

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                return None
            return self._row_to_user(row)

    def get_user_by_github_username(self, github_username: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE github_username = ? LIMIT 1",
                (github_username,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_user(row)

    def get_user_auth_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            return dict(row) if row else None

    def list_users(self, exclude_user_id: Optional[int] = None) -> Iterable[Dict[str, Any]]:
        with self.connect() as conn:
            if exclude_user_id is None:
                rows = conn.execute("SELECT * FROM users ORDER BY id ASC").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM users WHERE id != ? ORDER BY id ASC", (exclude_user_id,)
                ).fetchall()
            return [self._row_to_user(r) for r in rows]

    def update_user_stack(self, user_id: int, stack: list[str]):
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET stack_json = ? WHERE id = ?",
                (json.dumps(stack), user_id),
            )

    def update_user_streak(self, user_id: int):
        from datetime import date
        today = date.today().isoformat()
        with self.connect() as conn:
            user = conn.execute("SELECT current_streak, longest_streak, last_active_date FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                return
            current = user["current_streak"] or 0
            longest = user["longest_streak"] or 0
            last_date = user["last_active_date"]
            
            if last_date == today:
                return
            
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            if last_date == yesterday:
                new_streak = current + 1
            else:
                new_streak = 1
            
            new_longest = max(longest, new_streak)
            conn.execute(
                "UPDATE users SET current_streak = ?, longest_streak = ?, last_active_date = ? WHERE id = ?",
                (new_streak, new_longest, today, user_id),
            )

    def update_user_images(
        self, user_id: int, avatar_url: Optional[str] = None, setup_url: Optional[str] = None
    ):
        updates = []
        params = []
        if avatar_url is not None:
            updates.append("avatar_url = ?")
            params.append(avatar_url)
        if setup_url is not None:
            updates.append("setup_url = ?")
            params.append(setup_url)
        if not updates:
            return
        params.append(user_id)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                tuple(params),
            )

    def create_pull_request(self, from_user_id: int, to_user_id: int, bounty_id: Optional[int] = None) -> int:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO pull_requests (from_user_id, to_user_id, bounty_id, status, created_at)
                VALUES (?, ?, ?, 'open', ?)
                """,
                (from_user_id, to_user_id, bounty_id, now_iso()),
            )
            return int(cur.lastrowid)

    def get_pull_request_between(self, from_user_id: int, to_user_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM pull_requests
                WHERE from_user_id = ? AND to_user_id = ?
                """,
                (from_user_id, to_user_id),
            ).fetchone()
            return dict(row) if row else None

    def create_or_get_pull_request(self, from_user_id: int, to_user_id: int) -> Dict[str, Any]:
        try:
            pr_id = self.create_pull_request(from_user_id, to_user_id)
            pr = self.get_pull_request(pr_id)
            return pr or {}
        except IntegrityError:
            pr = self.get_pull_request_between(from_user_id, to_user_id)
            return pr or {}

    def create_or_get_pull_request_with_bounty(
        self, from_user_id: int, to_user_id: int, bounty_id: Optional[int] = None
    ) -> Dict[str, Any]:
        try:
            pr_id = self.create_pull_request(from_user_id, to_user_id, bounty_id=bounty_id)
            pr = self.get_pull_request(pr_id)
            return pr or {}
        except IntegrityError:
            pr = self.get_pull_request_between(from_user_id, to_user_id)
            if pr and bounty_id and not pr.get("bounty_id"):
                with self.connect() as conn:
                    conn.execute("UPDATE pull_requests SET bounty_id = ? WHERE id = ?", (bounty_id, pr["id"]))
                pr = self.get_pull_request(pr["id"])
            return pr or {}

    def get_pull_request(self, pr_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM pull_requests WHERE id = ?", (pr_id,)).fetchone()
            return dict(row) if row else None

    def list_pull_requests_for_user(
        self,
        user_id: int,
        direction: str = "incoming",
        status: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        if direction not in {"incoming", "outgoing"}:
            raise ValueError("direction invalido")
        column = "to_user_id" if direction == "incoming" else "from_user_id"
        params: list[Any] = [user_id]
        query = f"SELECT * FROM pull_requests WHERE {column} = ?"
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY id DESC"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def merge_pull_request(self, pr_id: int):
        with self.connect() as conn:
            conn.execute(
                "UPDATE pull_requests SET status = 'merged', merged_at = ? WHERE id = ?",
                (now_iso(), pr_id),
            )

    def get_bounty(self, bounty_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM bounties WHERE id = ?", (bounty_id,)).fetchone()
            return dict(row) if row else None

    def create_bounty(
        self,
        creator_id: int,
        title: str,
        description: str,
        reward_amount: float,
        reward_currency: str,
        tech_stack: str,
        status: str,
        escrow_locked: bool,
    ) -> int:
        ts = now_iso()
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO bounties (
                    creator_id, title, description, reward_amount, reward_currency,
                    tech_stack, status, escrow_locked, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    creator_id,
                    title,
                    description,
                    reward_amount,
                    reward_currency,
                    tech_stack,
                    status,
                    int(escrow_locked),
                    ts,
                    ts,
                ),
            )
            return int(cur.lastrowid)

    def list_bounties(self, status: Optional[str] = None) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT b.*, u.username AS creator_username
                    FROM bounties b
                    JOIN users u ON u.id = b.creator_id
                    WHERE b.status = ?
                    ORDER BY b.id DESC
                    """,
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT b.*, u.username AS creator_username
                    FROM bounties b
                    JOIN users u ON u.id = b.creator_id
                    ORDER BY b.id DESC
                    """
                ).fetchall()
            return [dict(r) for r in rows]

    def count_merged_bounties_by_user(self, user_id: int) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM bounties
                WHERE assigned_user_id = ? AND status = 'Merged'
                """,
                (user_id,),
            ).fetchone()
            return int(row["total"]) if row else 0

    def update_bounty_assignment(self, bounty_id: int, assigned_user_id: int, status: str):
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE bounties
                SET assigned_user_id = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (assigned_user_id, status, now_iso(), bounty_id),
            )

    def mark_bounty_merged_and_paid(self, bounty_id: int):
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE bounties
                SET status = 'Merged', paid_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now_iso(), now_iso(), bounty_id),
            )

    def adjust_user_balance(self, user_id: int, delta: float):
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET usd_balance = usd_balance + ? WHERE id = ?",
                (delta, user_id),
            )

    def get_user_balance(self, user_id: int) -> float:
        with self.connect() as conn:
            row = conn.execute("SELECT usd_balance FROM users WHERE id = ?", (user_id,)).fetchone()
            return float(row["usd_balance"]) if row else 0.0

    def update_last_github_activity(self, user_id: int, timestamp_iso: str):
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET last_github_activity = ? WHERE id = ?",
                (timestamp_iso, user_id),
            )

    def list_top_karma_users(self, limit: int = 10) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM users
                ORDER BY karma_score DESC, years DESC, id ASC
                LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()
            return [self._row_to_user(r) for r in rows]

    def get_global_stats(self) -> Dict[str, Any]:
        with self.connect() as conn:
            karma_row = conn.execute(
                "SELECT COALESCE(SUM(karma_score), 0) AS total_karma FROM users"
            ).fetchone()
            resources_row = conn.execute(
                "SELECT COUNT(*) AS resources_count FROM resources"
            ).fetchone()
            return {
                "total_karma": int(karma_row["total_karma"]) if karma_row else 0,
                "resources_count": int(resources_row["resources_count"]) if resources_row else 0,
            }

    def get_or_create_chat(self, user_a_id: int, user_b_id: int) -> int:
        a, b = sorted([user_a_id, user_b_id])
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM chats WHERE user_a_id = ? AND user_b_id = ?",
                (a, b),
            ).fetchone()
            if row:
                return int(row["id"])
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO chats (user_a_id, user_b_id, created_at)
                VALUES (?, ?, ?)
                """,
                (a, b, now_iso()),
            )
            return int(cur.lastrowid)

    def create_message(self, chat_id: int, sender_id: int, body: str) -> int:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO messages (chat_id, sender_id, body, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, sender_id, body, now_iso()),
            )
            return int(cur.lastrowid)

    def list_messages(self, chat_id: int) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, chat_id, sender_id, body, created_at FROM messages WHERE chat_id = ? ORDER BY id ASC",
                (chat_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_chat_scratchpad(self, chat_id: int) -> Dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT chat_id, content, updated_by, updated_at FROM chat_scratchpads WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            if row:
                return dict(row)
            return {"chat_id": chat_id, "content": "", "updated_by": None, "updated_at": None}

    def upsert_chat_scratchpad(self, chat_id: int, content: str, updated_by: int) -> Dict[str, Any]:
        ts = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_scratchpads (chat_id, content, updated_by, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    content = excluded.content,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (chat_id, content, updated_by, ts),
            )
        return self.get_chat_scratchpad(chat_id)

    def create_feed_post(self, user_id: int, title: str, content: str, category: str) -> int:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO news_feed (user_id, title, content, category, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, title, content, category, now_iso()),
            )
            return int(cur.lastrowid)

    def list_feed_posts(self, limit: int = 20) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT nf.id, nf.user_id, u.username, nf.title, nf.content, nf.category, nf.created_at
                FROM news_feed nf
                JOIN users u ON u.id = nf.user_id
                ORDER BY nf.id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_feed_post(self, post_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM news_feed WHERE id = ?", (post_id,)).fetchone()
            return dict(row) if row else None

    def create_cluster(
        self,
        name: str,
        description: str,
        creator_id: int,
        min_karma_required: int,
        tech_stack_focus: Optional[str],
    ) -> int:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO clusters (name, description, creator_id, min_karma_required, tech_stack_focus, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    description,
                    creator_id,
                    int(min_karma_required),
                    tech_stack_focus,
                    now_iso(),
                ),
            )
            cluster_id = int(cur.lastrowid)
            cur.execute(
                """
                INSERT INTO cluster_members (cluster_id, user_id, joined_at)
                VALUES (?, ?, ?)
                """,
                (cluster_id, creator_id, now_iso()),
            )
            return cluster_id

    def get_cluster(self, cluster_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT c.*, u.username AS creator_username
                FROM clusters c
                JOIN users u ON u.id = c.creator_id
                WHERE c.id = ?
                """,
                (cluster_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_clusters(self, query: Optional[str] = None, limit: int = 50) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            if query:
                like = f"%{query.strip()}%"
                rows = conn.execute(
                    """
                    SELECT
                        c.id, c.name, c.description, c.creator_id, c.min_karma_required,
                        c.tech_stack_focus, c.created_at, u.username AS creator_username,
                        COALESCE(m.members_count, 0) AS members_count
                    FROM clusters c
                    JOIN users u ON u.id = c.creator_id
                    LEFT JOIN (
                        SELECT cluster_id, COUNT(*) AS members_count
                        FROM cluster_members
                        GROUP BY cluster_id
                    ) m ON m.cluster_id = c.id
                    WHERE c.name LIKE ? OR c.description LIKE ? OR COALESCE(c.tech_stack_focus, '') LIKE ?
                    ORDER BY c.id DESC
                    LIMIT ?
                    """,
                    (like, like, like, max(1, min(limit, 200))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT
                        c.id, c.name, c.description, c.creator_id, c.min_karma_required,
                        c.tech_stack_focus, c.created_at, u.username AS creator_username,
                        COALESCE(m.members_count, 0) AS members_count
                    FROM clusters c
                    JOIN users u ON u.id = c.creator_id
                    LEFT JOIN (
                        SELECT cluster_id, COUNT(*) AS members_count
                        FROM cluster_members
                        GROUP BY cluster_id
                    ) m ON m.cluster_id = c.id
                    ORDER BY c.id DESC
                    LIMIT ?
                    """,
                    (max(1, min(limit, 200)),),
                ).fetchall()
            return [dict(r) for r in rows]

    def is_cluster_member(self, cluster_id: int, user_id: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM cluster_members WHERE cluster_id = ? AND user_id = ?",
                (cluster_id, user_id),
            ).fetchone()
            return bool(row)

    def add_cluster_member(self, cluster_id: int, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO cluster_members (cluster_id, user_id, joined_at)
                VALUES (?, ?, ?)
                """,
                (cluster_id, user_id, now_iso()),
            )

    def create_feed_interaction(
        self,
        user_id: int,
        target_type: str,
        target_id: int,
        interaction_type: str,
        fork_cluster_id: Optional[int] = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT OR IGNORE INTO feed_interactions (
                    user_id, target_type, target_id, interaction_type, fork_cluster_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    target_type,
                    target_id,
                    interaction_type,
                    fork_cluster_id,
                    now_iso(),
                ),
            )
            if cur.lastrowid:
                return int(cur.lastrowid)
            row = conn.execute(
                """
                SELECT id FROM feed_interactions
                WHERE user_id = ? AND target_type = ? AND target_id = ? AND interaction_type = ?
                """,
                (user_id, target_type, target_id, interaction_type),
            ).fetchone()
            return int(row["id"]) if row else 0

    def list_feed_interactions(
        self, target_type: str, target_id: int, limit: int = 200
    ) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    fi.id, fi.user_id, u.username, fi.target_type, fi.target_id, fi.interaction_type,
                    fi.fork_cluster_id, c.name AS fork_cluster_name, fi.created_at
                FROM feed_interactions fi
                JOIN users u ON u.id = fi.user_id
                LEFT JOIN clusters c ON c.id = fi.fork_cluster_id
                WHERE fi.target_type = ? AND fi.target_id = ?
                ORDER BY fi.id DESC
                LIMIT ?
                """,
                (target_type, target_id, max(1, min(limit, 500))),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_feed_thread(self, thread_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM feed_threads WHERE id = ?", (thread_id,)).fetchone()
            return dict(row) if row else None

    def create_feed_thread(
        self,
        user_id: int,
        target_type: str,
        target_id: int,
        content: str,
        parent_thread_id: Optional[int] = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO feed_threads (user_id, target_type, target_id, parent_thread_id, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, target_type, target_id, parent_thread_id, content, now_iso()),
            )
            return int(cur.lastrowid)

    def list_feed_threads(
        self, target_type: str, target_id: int, limit: int = 200
    ) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    ft.id, ft.user_id, u.username, ft.target_type, ft.target_id,
                    ft.parent_thread_id, ft.content, ft.created_at
                FROM feed_threads ft
                JOIN users u ON u.id = ft.user_id
                WHERE ft.target_type = ? AND ft.target_id = ?
                ORDER BY ft.id ASC
                LIMIT ?
                """,
                (target_type, target_id, max(1, min(limit, 500))),
            ).fetchall()
            return [dict(r) for r in rows]

    def create_showcase_project(
        self,
        user_id: int,
        title: str,
        description: str,
        price: Optional[float],
        demo_url: Optional[str],
        image_url: Optional[str],
    ) -> int:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO showcase (user_id, title, description, price, demo_url, image_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, title, description, price, demo_url, image_url, now_iso()),
            )
            return int(cur.lastrowid)

    def list_showcase_projects(self, limit: int = 30) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.id, s.user_id, u.username, s.title, s.description, s.price, s.demo_url, s.image_url, s.created_at
                FROM showcase s
                JOIN users u ON u.id = s.user_id
                ORDER BY s.id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
            return [dict(r) for r in rows]

    def create_resource(self, user_id: int, link: str, topic: str) -> int:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO resources (user_id, link, topic, helpful_count, created_at)
                VALUES (?, ?, ?, 0, ?)
                """,
                (user_id, link, topic, now_iso()),
            )
            return int(cur.lastrowid)

    def get_resource(self, resource_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM resources WHERE id = ?", (resource_id,)).fetchone()
            return dict(row) if row else None

    def increment_resource_helpful(self, resource_id: int):
        with self.connect() as conn:
            conn.execute(
                "UPDATE resources SET helpful_count = helpful_count + 1 WHERE id = ?",
                (resource_id,),
            )

    def list_resources(self, topic: Optional[str] = None, limit: int = 50) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            if topic:
                rows = conn.execute(
                    """
                    SELECT r.id, r.user_id, u.username, r.link, r.topic, r.helpful_count, r.created_at
                    FROM resources r
                    JOIN users u ON u.id = r.user_id
                    WHERE LOWER(r.topic) = LOWER(?)
                    ORDER BY r.helpful_count DESC, r.id DESC
                    LIMIT ?
                    """,
                    (topic, max(1, min(limit, 200))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT r.id, r.user_id, u.username, r.link, r.topic, r.helpful_count, r.created_at
                    FROM resources r
                    JOIN users u ON u.id = r.user_id
                    ORDER BY r.helpful_count DESC, r.id DESC
                    LIMIT ?
                    """,
                    (max(1, min(limit, 200)),),
                ).fetchall()
            return [dict(r) for r in rows]

    def create_snippet(self, user_id: int, title: str, language: str, code: str) -> int:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO snippets (user_id, title, language, code, likes_count, created_at)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (user_id, title, language, code, now_iso()),
            )
            return int(cur.lastrowid)

    def list_snippets(self, limit: int = 50) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.id, s.user_id, u.username, s.title, s.language, s.code, s.likes_count, s.created_at
                FROM snippets s
                JOIN users u ON u.id = s.user_id
                ORDER BY s.likes_count DESC, s.id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
            return [dict(r) for r in rows]

    def create_endorsement(self, from_user_id: int, to_user_id: int, skill: str) -> int:
        with self.connect() as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO endorsements (from_user_id, to_user_id, skill, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (from_user_id, to_user_id, skill, now_iso()),
                )
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                return -1

    def get_user_endorsements(self, user_id: int) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.skill, u.username as from_username, e.created_at
                FROM endorsements e
                JOIN users u ON u.id = e.from_user_id
                WHERE e.to_user_id = ?
                ORDER BY e.created_at DESC
                """,
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_user_endorsement_count(self, user_id: int) -> Dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT skill, COUNT(*) as count
                FROM endorsements
                WHERE to_user_id = ?
                GROUP BY skill
                """,
                (user_id,),
            ).fetchall()
            return {r["skill"]: r["count"] for r in rows}

    def get_showcase_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM showcase WHERE id = ?", (project_id,)).fetchone()
            return dict(row) if row else None

    def adjust_user_karma(self, user_id: int, delta: int):
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET karma_score = karma_score + ? WHERE id = ?",
                (int(delta), user_id),
            )

    def chat_has_user(self, chat_id: int, user_id: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM chats
                WHERE id = ? AND (user_a_id = ? OR user_b_id = ?)
                """,
                (chat_id, user_id, user_id),
            ).fetchone()
            return bool(row)

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data.pop("password_hash", None)
        data["stack"] = json.loads(data.pop("stack_json"))
        data["prefers_tabs"] = bool(data["prefers_tabs"])
        data["dark_mode"] = bool(data["dark_mode"])
        data["is_admin"] = bool(data.get("is_admin", 0))
        return data
