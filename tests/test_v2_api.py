import importlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


def _load_test_client(tmp_dir: str):
    db_path = Path(tmp_dir) / "test_v25.db"
    media_dir = Path(tmp_dir) / "media"
    os.environ["CODECOMMIT_DB_PATH"] = str(db_path)
    os.environ["CODECOMMIT_MEDIA_DIR"] = str(media_dir)
    os.environ["CODECOMMIT_ADMIN_DASH_SECRET"] = "test-admin-secret"
    os.environ["CODECOMMIT_ADMIN_BOOTSTRAP_KEY"] = "test-bootstrap-key"
    os.environ["CODECOMMIT_RATE_LIMIT_MAX"] = "10000"
    os.environ["CODECOMMIT_RATE_LIMIT_WINDOW_SECONDS"] = "60"
    os.environ.setdefault("CODECOMMIT_JWT_SECRET", "test-jwt-secret")

    import src.codecommit.config as config_module
    import src.codecommit.app_v2 as app_module

    importlib.reload(config_module)
    importlib.reload(app_module)
    return TestClient(app_module.app)


class TestV25Api(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = _load_test_client(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("CODECOMMIT_DB_PATH", None)
        os.environ.pop("CODECOMMIT_MEDIA_DIR", None)
        os.environ.pop("CODECOMMIT_ADMIN_DASH_SECRET", None)
        os.environ.pop("CODECOMMIT_ADMIN_BOOTSTRAP_KEY", None)
        os.environ.pop("CODECOMMIT_RATE_LIMIT_MAX", None)
        os.environ.pop("CODECOMMIT_RATE_LIMIT_WINDOW_SECONDS", None)
        os.environ.pop("CODECOMMIT_JWT_SECRET", None)

    def _register(
        self,
        username: str,
        password: str = "CodeCommit123!",
        stack: list[str] | None = None,
        years_exp: int = 4,
        is_admin: bool = False,
    ):
        return self.client.post(
            "/v2/auth/register",
            json={
                "username": username,
                "password": password,
                "stack": stack or ["Python", "Docker"],
                "years_exp": years_exp,
                "tabs_vs_spaces": True,
                "dark_mode": True,
                "puzzle_answer": "1",
                "is_admin": is_admin,
                "admin_bootstrap_key": "test-bootstrap-key" if is_admin else "",
            },
        )

    def _login_token(self, username: str, password: str = "CodeCommit123!"):
        res = self.client.post(
            "/v2/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["access_token"]

    def test_register_with_image_upload(self):
        reg = self._register("img_user")
        self.assertEqual(reg.status_code, 200, reg.text)
        token = self._login_token("img_user")

        up = self.client.post(
            "/v2/me/avatar",
            headers={"Authorization": f"Bearer {token}"},
            files={"image": ("avatar.png", b"\x89PNG\r\n\x1a\ncontent", "image/png")},
        )
        self.assertEqual(up.status_code, 200, up.text)
        self.assertTrue(up.json()["avatar_url"].startswith("/media/"))

        me = self.client.get("/v2/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.status_code, 200)
        self.assertTrue(me.json().get("avatar_url", "").startswith("/media/"))

    def test_pr_to_merge_flow(self):
        self.assertEqual(self._register("dev_a").status_code, 200)
        self.assertEqual(self._register("dev_b").status_code, 200)
        token_a = self._login_token("dev_a")
        token_b = self._login_token("dev_b")

        pr = self.client.post(
            "/v2/pull-requests",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"to_user_id": 2},
        )
        self.assertEqual(pr.status_code, 200, pr.text)
        self.assertFalse(pr.json()["matched"])

        inbox = self.client.get(
            "/v2/pull-requests/incoming",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        self.assertEqual(inbox.status_code, 200, inbox.text)
        pr_id = inbox.json()["pull_requests"][0]["id"]

        merged = self.client.post(
            f"/v2/pull-requests/{pr_id}/merge",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        self.assertEqual(merged.status_code, 200, merged.text)
        self.assertEqual(merged.json()["status"], "merged")
        self.assertTrue(int(merged.json()["chat_id"]) > 0)

    def test_websocket_connection_with_jwt(self):
        self.assertEqual(self._register("ws_a").status_code, 200)
        self.assertEqual(self._register("ws_b").status_code, 200)
        token_a = self._login_token("ws_a")
        token_b = self._login_token("ws_b")

        self.client.post(
            "/v2/pull-requests",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"to_user_id": 2},
        )
        reverse = self.client.post(
            "/v2/pull-requests",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"to_user_id": 1},
        )
        self.assertEqual(reverse.status_code, 200, reverse.text)
        self.assertTrue(reverse.json()["matched"])
        chat_id = reverse.json()["chat_id"]

        with self.client.websocket_connect(f"/v2/ws/chat/{chat_id}?token={token_a}") as ws:
            ws.send_text(json.dumps({"body": "hola realtime"}))
            event = ws.receive_json()
            self.assertEqual(event["type"], "chat.message")
            self.assertIn("hola realtime", event["message"]["body"])

    def test_stress_auto_match_persists_messages(self):
        self.assertEqual(self._register("owner_dev").status_code, 200)
        self.assertEqual(self._register("stress_bot_x").status_code, 200)
        token_owner = self._login_token("owner_dev")

        pr = self.client.post(
            "/v2/pull-requests",
            headers={"Authorization": f"Bearer {token_owner}"},
            json={"to_user_id": 2},
        )
        self.assertEqual(pr.status_code, 200, pr.text)
        self.assertTrue(pr.json()["matched"])
        chat_id = pr.json()["chat_id"]

        msg = self.client.post(
            f"/v2/chat/{chat_id}/messages",
            headers={"Authorization": f"Bearer {token_owner}"},
            json={"body": "mensaje persistente"},
        )
        self.assertEqual(msg.status_code, 200, msg.text)

        history = self.client.get(
            f"/v2/chat/{chat_id}/messages",
            headers={"Authorization": f"Bearer {token_owner}"},
        )
        self.assertEqual(history.status_code, 200, history.text)
        bodies = [m["body"] for m in history.json().get("messages", [])]
        self.assertTrue(any("mensaje persistente" in b for b in bodies))

    def test_profiles_filter_by_stack(self):
        self.assertEqual(
            self.client.post(
                "/v2/auth/register",
                json={
                    "username": "py_dev",
                    "password": "CodeCommit123!",
                    "stack": ["Python", "FastAPI"],
                    "years_exp": 5,
                    "tabs_vs_spaces": True,
                    "dark_mode": True,
                    "puzzle_answer": "1",
                },
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/v2/auth/register",
                json={
                    "username": "go_dev",
                    "password": "CodeCommit123!",
                    "stack": ["Go", "Docker"],
                    "years_exp": 5,
                    "tabs_vs_spaces": True,
                    "dark_mode": True,
                    "puzzle_answer": "1",
                },
            ).status_code,
            200,
        )

        token = self._login_token("py_dev")
        filtered = self.client.get(
            "/v2/profiles?stack=Go",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(filtered.status_code, 200, filtered.text)
        usernames = [p["username"] for p in filtered.json().get("profiles", [])]
        self.assertIn("go_dev", usernames)
        self.assertNotIn("py_dev", usernames)

    def test_user_can_publish_feed_and_persist(self):
        self.assertEqual(self._register("feed_author").status_code, 200)
        token = self._login_token("feed_author")

        create = self.client.post(
            "/v2/feed",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "title": "Nuevo release del motor matcher",
                "content": "Mejoramos ranking por afinidad de stack y cultura.",
                "category": "TECH",
            },
        )
        self.assertEqual(create.status_code, 200, create.text)
        self.assertTrue(int(create.json()["id"]) > 0)

        feed = self.client.get("/v2/feed")
        self.assertEqual(feed.status_code, 200, feed.text)
        posts = feed.json().get("posts", [])
        self.assertTrue(any(p["title"] == "Nuevo release del motor matcher" for p in posts))

    def test_only_senior_can_publish_security(self):
        # Junior (4 años o menos) no puede publicar SECURITY
        junior = self.client.post(
            "/v2/auth/register",
            json={
                "username": "junior_sec",
                "password": "CodeCommit123!",
                "stack": ["Python"],
                "years_exp": 2,
                "tabs_vs_spaces": True,
                "dark_mode": True,
                "puzzle_answer": "1",
            },
        )
        self.assertEqual(junior.status_code, 200)
        t_junior = self._login_token("junior_sec")
        denied = self.client.post(
            "/v2/feed",
            headers={"Authorization": f"Bearer {t_junior}"},
            json={
                "title": "Advisory",
                "content": "Rotar secrets y revisar headers.",
                "category": "SECURITY",
            },
        )
        self.assertEqual(denied.status_code, 400)

        # Senior (>8) sí puede publicar SECURITY
        senior = self.client.post(
            "/v2/auth/register",
            json={
                "username": "senior_sec",
                "password": "CodeCommit123!",
                "stack": ["Go", "Kubernetes"],
                "years_exp": 12,
                "tabs_vs_spaces": True,
                "dark_mode": True,
                "puzzle_answer": "1",
            },
        )
        self.assertEqual(senior.status_code, 200)
        t_senior = self._login_token("senior_sec")
        allowed = self.client.post(
            "/v2/feed",
            headers={"Authorization": f"Bearer {t_senior}"},
            json={
                "title": "Zero-day mitigación",
                "content": "Aplicar WAF y segmentación de redes.",
                "category": "SECURITY",
            },
        )
        self.assertEqual(allowed.status_code, 200, allowed.text)

    def test_bounty_closes_after_merge(self):
        self.assertEqual(self._register("bounty_creator").status_code, 200)
        self.assertEqual(self._register("bounty_solver").status_code, 200)
        token_creator = self._login_token("bounty_creator")
        token_solver = self._login_token("bounty_solver")

        create = self.client.post(
            "/v2/bounties",
            headers={"Authorization": f"Bearer {token_creator}"},
            json={
                "title": "Fix race condition",
                "description": "Need deterministic worker scheduling in job queue",
                "reward_amount": 50,
                "reward_currency": "USD",
                "tech_stack": "Python,Redis",
            },
        )
        self.assertEqual(create.status_code, 200, create.text)
        bounty_id = create.json()["id"]

        pr = self.client.post(
            "/v2/pull-requests",
            headers={"Authorization": f"Bearer {token_solver}"},
            json={"to_user_id": 1, "bounty_id": bounty_id},
        )
        self.assertEqual(pr.status_code, 200, pr.text)
        pr_id = pr.json()["id"]

        merged = self.client.post(
            f"/v2/pull-requests/{pr_id}/merge",
            headers={"Authorization": f"Bearer {token_creator}"},
        )
        self.assertEqual(merged.status_code, 200, merged.text)
        self.assertTrue(merged.json().get("bounty_paid", False))

        merged_bounties = self.client.get("/v2/bounties?status=Merged")
        self.assertEqual(merged_bounties.status_code, 200)
        ids = [b["id"] for b in merged_bounties.json().get("bounties", [])]
        self.assertIn(bounty_id, ids)

    def test_github_sync_updates_activity(self):
        self.assertEqual(self._register("git_live").status_code, 200)
        token = self._login_token("git_live")
        sync = self.client.post(
            "/v2/github/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(sync.status_code, 200, sync.text)
        self.assertTrue(sync.json().get("last_github_activity"))

    def test_suggested_matches_prioritizes_active_senior(self):
        # Base user
        self.assertEqual(
            self.client.post(
                "/v2/auth/register",
                json={
                    "username": "base_dev",
                    "password": "CodeCommit123!",
                    "stack": ["Python", "Docker"],
                    "years_exp": 6,
                    "tabs_vs_spaces": True,
                    "dark_mode": True,
                    "puzzle_answer": "1",
                },
            ).status_code,
            200,
        )

        # Senior activo
        self.assertEqual(
            self.client.post(
                "/v2/auth/register",
                json={
                    "username": "senior_active",
                    "password": "CodeCommit123!",
                    "stack": ["Python", "Docker"],
                    "years_exp": 12,
                    "tabs_vs_spaces": True,
                    "dark_mode": True,
                    "puzzle_answer": "1",
                },
            ).status_code,
            200,
        )

        # Senior inactivo (sin sync)
        self.assertEqual(
            self.client.post(
                "/v2/auth/register",
                json={
                    "username": "senior_inactive",
                    "password": "CodeCommit123!",
                    "stack": ["Python", "Docker"],
                    "years_exp": 12,
                    "tabs_vs_spaces": True,
                    "dark_mode": True,
                    "puzzle_answer": "1",
                },
            ).status_code,
            200,
        )

        base_token = self._login_token("base_dev")
        active_token = self._login_token("senior_active")

        # Simula actividad reciente en senior_active
        sync = self.client.post(
            "/v2/github/sync",
            headers={"Authorization": f"Bearer {active_token}"},
        )
        self.assertEqual(sync.status_code, 200)

        suggested = self.client.get(
            "/v2/suggested-matches?limit=10",
            headers={"Authorization": f"Bearer {base_token}"},
        )
        self.assertEqual(suggested.status_code, 200, suggested.text)
        profiles = suggested.json().get("profiles", [])
        usernames = [p["username"] for p in profiles]
        self.assertIn("senior_active", usernames)
        self.assertIn("senior_inactive", usernames)
        self.assertLess(usernames.index("senior_active"), usernames.index("senior_inactive"))

    def test_user_can_upload_showcase_project(self):
        self.assertEqual(self._register("market_owner").status_code, 200)
        token = self._login_token("market_owner")

        create = self.client.post(
            "/v2/showcase",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "title": "Algo Trader Lite",
                "description": "Micro-SaaS para backtesting con panel en tiempo real.",
                "price": 149.0,
                "demo_url": "https://example.com/demo",
                "image_url": "https://example.com/screen.png",
            },
        )
        self.assertEqual(create.status_code, 200, create.text)
        self.assertTrue(int(create.json()["id"]) > 0)

        listing = self.client.get("/v2/showcase?limit=20")
        self.assertEqual(listing.status_code, 200, listing.text)
        titles = [p["title"] for p in listing.json().get("projects", [])]
        self.assertIn("Algo Trader Lite", titles)

    def test_helpful_vote_increases_author_karma(self):
        self.assertEqual(self._register("resource_author").status_code, 200)
        self.assertEqual(self._register("resource_voter").status_code, 200)
        token_author = self._login_token("resource_author")
        token_voter = self._login_token("resource_voter")

        res = self.client.post(
            "/v2/resources",
            headers={"Authorization": f"Bearer {token_author}"},
            json={"link": "https://example.com/backend-guide", "topic": "Backend"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        resource_id = res.json()["id"]

        before = self.client.get("/v2/me", headers={"Authorization": f"Bearer {token_author}"})
        self.assertEqual(before.status_code, 200)
        before_karma = int(before.json().get("karma_score", 0))

        vote = self.client.post(
            f"/v2/resources/{resource_id}/helpful",
            headers={"Authorization": f"Bearer {token_voter}"},
        )
        self.assertEqual(vote.status_code, 200, vote.text)
        self.assertEqual(vote.json()["helpful_count"], 1)

        after = self.client.get("/v2/me", headers={"Authorization": f"Bearer {token_author}"})
        self.assertEqual(after.status_code, 200)
        after_karma = int(after.json().get("karma_score", 0))
        self.assertEqual(after_karma, before_karma + 5)

    def test_user_cannot_vote_helpful_on_own_resource(self):
        self.assertEqual(self._register("self_helpful").status_code, 200)
        token = self._login_token("self_helpful")
        res = self.client.post(
            "/v2/resources",
            headers={"Authorization": f"Bearer {token}"},
            json={"link": "https://example.com/self", "topic": "AI"},
        )
        self.assertEqual(res.status_code, 200)
        resource_id = res.json()["id"]

        vote = self.client.post(
            f"/v2/resources/{resource_id}/helpful",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(vote.status_code, 400)

    def test_marketplace_collaboration_increases_creator_karma(self):
        self.assertEqual(self._register("market_creator").status_code, 200)
        self.assertEqual(self._register("market_buyer").status_code, 200)
        t_creator = self._login_token("market_creator")
        t_buyer = self._login_token("market_buyer")

        created = self.client.post(
            "/v2/showcase",
            headers={"Authorization": f"Bearer {t_creator}"},
            json={
                "title": "Realtime Signals",
                "description": "Motor de señales para micro-saas financiero.",
                "price": 99,
                "demo_url": "https://example.com/signals",
                "image_url": "https://example.com/signals.png",
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        project_id = created.json()["id"]

        before = self.client.get("/v2/me", headers={"Authorization": f"Bearer {t_creator}"})
        before_karma = int(before.json().get("karma_score", 0))

        collab = self.client.post(
            f"/v2/showcase/{project_id}/collaborate",
            headers={"Authorization": f"Bearer {t_buyer}"},
        )
        self.assertEqual(collab.status_code, 200, collab.text)

        after = self.client.get("/v2/me", headers={"Authorization": f"Bearer {t_creator}"})
        after_karma = int(after.json().get("karma_score", 0))
        self.assertEqual(after_karma, before_karma + 20)

    def test_karma_top_ranking_desc_order(self):
        for username in ["top_a", "top_b", "top_c", "voter_1", "voter_2", "voter_3"]:
            self.assertEqual(
                self.client.post(
                    "/v2/auth/register",
                    json={
                        "username": username,
                        "password": "CodeCommit123!",
                        "stack": ["Python"],
                        "years_exp": 5,
                        "tabs_vs_spaces": True,
                        "dark_mode": True,
                        "puzzle_answer": "1",
                    },
                ).status_code,
                200,
            )

        t_a = self._login_token("top_a")
        t_b = self._login_token("top_b")
        t_c = self._login_token("top_c")
        t_v1 = self._login_token("voter_1")
        t_v2 = self._login_token("voter_2")
        t_v3 = self._login_token("voter_3")

        ra = self.client.post("/v2/resources", headers={"Authorization": f"Bearer {t_a}"}, json={"link": "https://ex.com/a", "topic": "Backend"}).json()["id"]
        rb = self.client.post("/v2/resources", headers={"Authorization": f"Bearer {t_b}"}, json={"link": "https://ex.com/b", "topic": "Backend"}).json()["id"]
        rc = self.client.post("/v2/resources", headers={"Authorization": f"Bearer {t_c}"}, json={"link": "https://ex.com/c", "topic": "Backend"}).json()["id"]

        # top_a => +10 (2 votes), top_b => +5 (1 vote), top_c => 0
        self.client.post(f"/v2/resources/{ra}/helpful", headers={"Authorization": f"Bearer {t_v1}"})
        self.client.post(f"/v2/resources/{ra}/helpful", headers={"Authorization": f"Bearer {t_v2}"})
        self.client.post(f"/v2/resources/{rb}/helpful", headers={"Authorization": f"Bearer {t_v3}"})

        ranking = self.client.get("/v2/karma/top?limit=10")
        self.assertEqual(ranking.status_code, 200, ranking.text)
        users = ranking.json().get("users", [])
        names = [u["username"] for u in users]
        self.assertLess(names.index("top_a"), names.index("top_b"))
        self.assertLess(names.index("top_b"), names.index("top_c"))

    def test_user_can_join_cluster_with_karma_and_comment_thread(self):
        for username in ["cluster_owner", "cluster_candidate", "cluster_voter", "cluster_low"]:
            self.assertEqual(self._register(username).status_code, 200)

        t_owner = self._login_token("cluster_owner")
        t_candidate = self._login_token("cluster_candidate")
        t_voter = self._login_token("cluster_voter")
        t_low = self._login_token("cluster_low")

        # Elevar karma del candidato (+5) usando helpful en su resource.
        resource = self.client.post(
            "/v2/resources",
            headers={"Authorization": f"Bearer {t_candidate}"},
            json={"link": "https://example.com/cluster-candidate-resource", "topic": "Backend"},
        )
        self.assertEqual(resource.status_code, 200, resource.text)
        resource_id = resource.json()["id"]
        vote = self.client.post(
            f"/v2/resources/{resource_id}/helpful",
            headers={"Authorization": f"Bearer {t_voter}"},
        )
        self.assertEqual(vote.status_code, 200, vote.text)

        cluster = self.client.post(
            "/v2/clusters",
            headers={"Authorization": f"Bearer {t_owner}"},
            json={
                "name": "Python Trading Architects",
                "description": "Cluster para arquitectura backend y sistemas de trading.",
                "min_karma_required": 5,
                "tech_stack_focus": "Python,Redis,PostgreSQL",
            },
        )
        self.assertEqual(cluster.status_code, 200, cluster.text)
        cluster_id = cluster.json()["id"]

        denied = self.client.post(
            f"/v2/clusters/{cluster_id}/join",
            headers={"Authorization": f"Bearer {t_low}"},
        )
        self.assertEqual(denied.status_code, 400, denied.text)

        joined = self.client.post(
            f"/v2/clusters/{cluster_id}/join",
            headers={"Authorization": f"Bearer {t_candidate}"},
        )
        self.assertEqual(joined.status_code, 200, joined.text)
        self.assertTrue(joined.json().get("joined"))

        feed_post = self.client.post(
            "/v2/feed",
            headers={"Authorization": f"Bearer {t_owner}"},
            json={
                "title": "Cluster kickoff",
                "content": "Publicamos la primera guia de arquitectura del cluster.",
                "category": "TECH",
            },
        )
        self.assertEqual(feed_post.status_code, 200, feed_post.text)
        post_id = feed_post.json()["id"]

        thread = self.client.post(
            "/v2/feed/threads",
            headers={"Authorization": f"Bearer {t_candidate}"},
            json={
                "target_type": "news",
                "target_id": post_id,
                "content": "THREAD: propondria versionar ADRs por sprint.",
            },
        )
        self.assertEqual(thread.status_code, 200, thread.text)

        listed = self.client.get(
            f"/v2/feed/threads?target_type=news&target_id={post_id}",
            headers={"Authorization": f"Bearer {t_candidate}"},
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        comments = listed.json().get("threads", [])
        self.assertTrue(
            any(
                c.get("user_id") == 2 and "ADRs" in c.get("content", "")
                for c in comments
            )
        )

    def test_notification_component_non_blocking_ui_contract(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200, page.text)
        html = page.text
        self.assertIn("function showNotification(message, type = \"info\")", html)
        self.assertIn("id=\"notifyDock\" class=\"pointer-events-none", html)
        self.assertIn("requestAnimationFrame(() => {", html)
        self.assertIn("setTimeout(() => note.remove(), timeout);", html)
        self.assertIn("startRealtimePulse()", html)
        self.assertIn("Silent: evitamos romper la UI principal", html)

    def test_boot_animation_under_2_seconds_ui_contract(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200, page.text)
        html = page.text
        self.assertIn("id=\"bootOverlay\"", html)
        self.assertIn("[ LOGIN_SEQUENCE_INITIALIZED ]", html)
        self.assertIn("[ ENCRYPTING_SESSION... ]", html)
        self.assertIn("[ HANDSHAKE_WITH_IP: 74.208.227.87 ]", html)
        self.assertIn("[ ACCESS_GRANTED: WELCOME ARCHITECT ]", html)
        self.assertIn("runBootSequence()", html)
        self.assertIn("bootOverlay.remove();", html)
        match = re.search(r"const\s+BOOT_ANIMATION_MS\s*=\s*(\d+)\s*;", html)
        self.assertIsNotNone(match, "BOOT_ANIMATION_MS no definido en index.html")
        self.assertLessEqual(int(match.group(1)), 2000)

    def test_scratchpad_syncs_between_two_users_via_websocket(self):
        self.assertEqual(self._register("pad_a").status_code, 200)
        self.assertEqual(self._register("pad_b").status_code, 200)
        token_a = self._login_token("pad_a")
        token_b = self._login_token("pad_b")

        self.client.post(
            "/v2/pull-requests",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"to_user_id": 2},
        )
        reverse = self.client.post(
            "/v2/pull-requests",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"to_user_id": 1},
        )
        self.assertEqual(reverse.status_code, 200, reverse.text)
        self.assertTrue(reverse.json()["matched"])
        chat_id = reverse.json()["chat_id"]

        payload = {"type": "scratchpad.update", "content": "print('sync ok')\n"}
        with self.client.websocket_connect(f"/v2/ws/chat/{chat_id}?token={token_a}") as ws_a:
            with self.client.websocket_connect(f"/v2/ws/chat/{chat_id}?token={token_b}") as ws_b:
                ws_a.send_text(json.dumps(payload))
                evt_a = ws_a.receive_json()
                evt_b = ws_b.receive_json()

                self.assertEqual(evt_a["type"], "chat.scratchpad")
                self.assertEqual(evt_b["type"], "chat.scratchpad")
                self.assertIn("sync ok", evt_a["scratchpad"]["content"])
                self.assertIn("sync ok", evt_b["scratchpad"]["content"])

        stored = self.client.get(
            f"/v2/chat/{chat_id}/scratchpad",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        self.assertEqual(stored.status_code, 200, stored.text)
        self.assertIn("sync ok", stored.json().get("content", ""))

    def test_admin_analytics_metrics_are_correct(self):
        self.assertEqual(
            self._register("admin_arch", stack=["Python", "Docker"], years_exp=10, is_admin=True).status_code,
            200,
        )
        self.assertEqual(self._register("dev_go", stack=["Go", "Docker"]).status_code, 200)
        self.assertEqual(self._register("dev_py", stack=["Python", "Rust"]).status_code, 200)

        t_admin = self._login_token("admin_arch")
        t_go = self._login_token("dev_go")
        t_py = self._login_token("dev_py")

        # Karma: dev_go publica recurso y dev_py vota helpful => +5 para dev_go
        resource = self.client.post(
            "/v2/resources",
            headers={"Authorization": f"Bearer {t_go}"},
            json={"link": "https://example.com/go-resource", "topic": "Backend"},
        )
        self.assertEqual(resource.status_code, 200, resource.text)
        vote = self.client.post(
            f"/v2/resources/{resource.json()['id']}/helpful",
            headers={"Authorization": f"Bearer {t_py}"},
        )
        self.assertEqual(vote.status_code, 200, vote.text)

        # Bounties total value: 40 + 25 = 65
        b1 = self.client.post(
            "/v2/bounties",
            headers={"Authorization": f"Bearer {t_admin}"},
            json={
                "title": "Hardening API",
                "description": "Aplicar mejoras de seguridad para release.",
                "reward_amount": 40,
                "reward_currency": "USD",
                "tech_stack": "Python,FastAPI",
            },
        )
        self.assertEqual(b1.status_code, 200, b1.text)
        b2 = self.client.post(
            "/v2/bounties",
            headers={"Authorization": f"Bearer {t_go}"},
            json={
                "title": "Optimize workers",
                "description": "Reducir latencia de workers en cola.",
                "reward_amount": 25,
                "reward_currency": "USD",
                "tech_stack": "Go,Redis",
            },
        )
        self.assertEqual(b2.status_code, 200, b2.text)

        analytics = self.client.get(
            "/v2/admin/analytics",
            headers={"Authorization": f"Bearer {t_admin}"},
        )
        self.assertEqual(analytics.status_code, 200, analytics.text)
        data = analytics.json()

        self.assertEqual(data["users_total"], 3)
        self.assertEqual(data["karma_total"], 5)
        self.assertEqual(data["bounties_total_value"], 65.0)
        self.assertEqual(data["bounties_open_value"], 65.0)
        stacks = {s["stack"]: s["count"] for s in data.get("stacks_top", [])}
        self.assertEqual(stacks.get("Docker"), 2)
        self.assertEqual(stacks.get("Python"), 2)

        # Fallback por URL secreta (sin token admin) tambien permitido.
        analytics_secret = self.client.get("/v2/admin/analytics?secret=test-admin-secret")
        self.assertEqual(analytics_secret.status_code, 200, analytics_secret.text)

    def test_health_endpoint_online(self):
        health_basic = self.client.get("/health")
        self.assertEqual(health_basic.status_code, 200, health_basic.text)
        self.assertEqual(health_basic.json(), {"status": "online"})

        health_v2 = self.client.get("/v2/health")
        self.assertEqual(health_v2.status_code, 200, health_v2.text)
        self.assertEqual(health_v2.json(), {"status": "online", "version": "5.7"})

    def test_old_jwt_invalid_after_secret_rotation(self):
        os.environ["CODECOMMIT_JWT_SECRET"] = "jwt-initial-secret"
        client_a = _load_test_client(self.tmp.name)

        reg = client_a.post(
            "/v2/auth/register",
            json={
                "username": "rotate_user",
                "password": "CodeCommit123!",
                "stack": ["Python"],
                "years_exp": 4,
                "tabs_vs_spaces": True,
                "dark_mode": True,
                "puzzle_answer": "1",
            },
        )
        self.assertEqual(reg.status_code, 200, reg.text)
        login = client_a.post(
            "/v2/auth/login",
            json={"username": "rotate_user", "password": "CodeCommit123!"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        old_token = login.json()["access_token"]

        os.environ["CODECOMMIT_JWT_SECRET"] = "jwt-rotated-secret"
        client_b = _load_test_client(self.tmp.name)
        denied = client_b.get("/v2/me", headers={"Authorization": f"Bearer {old_token}"})
        self.assertEqual(denied.status_code, 401, denied.text)


if __name__ == "__main__":
    unittest.main()
