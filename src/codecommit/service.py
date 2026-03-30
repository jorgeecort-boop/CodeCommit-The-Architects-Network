from datetime import datetime, timedelta, timezone
from collections import Counter
from typing import Any, Dict

from .db import Database
from .github_client import fetch_top_languages
from .security import sanitize_chat_message
from .stack_matcher import DevMatcher


class DomainError(ValueError):
    pass


class CodeCommitService:
    def __init__(self, db: Database):
        self.db = db
        self.matcher = DevMatcher()

    @staticmethod
    def _validate_entry_gate(puzzle_answer: str | None, github_username: str | None):
        puzzle_ok = (puzzle_answer or "").strip() == "1"
        github_ok = bool((github_username or "").strip())
        if not (puzzle_ok or github_ok):
            raise DomainError(
                "Debes resolver el acertijo tecnico (respuesta: 1) o conectar GitHub."
            )

    def register_user(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        required = ["username", "stack", "years"]
        for key in required:
            if key not in payload:
                raise DomainError(f"Falta campo requerido: {key}")

        username = str(payload["username"]).strip()
        if len(username) < 3:
            raise DomainError("username debe tener al menos 3 caracteres.")
        if self.db.get_user_by_username(username):
            raise DomainError("username ya existe.")

        stack = payload["stack"]
        if not isinstance(stack, list) or not stack:
            raise DomainError("stack debe ser una lista no vacia.")
        normalized_stack = [str(s).strip() for s in stack if str(s).strip()]
        if not normalized_stack:
            raise DomainError("stack invalido.")

        years = int(payload["years"])
        if years < 0 or years > 60:
            raise DomainError("years fuera de rango.")

        github_username = payload.get("github_username")
        puzzle_answer = payload.get("puzzle_answer")
        self._validate_entry_gate(puzzle_answer, github_username)

        user_id = self.db.create_user(
            {
                "username": username,
                "password_hash": payload.get("password_hash", ""),
                "stack": normalized_stack,
                "years": years,
                "prefers_tabs": bool(payload.get("prefers_tabs", False)),
                "dark_mode": bool(payload.get("dark_mode", True)),
                "is_admin": bool(payload.get("is_admin", False)),
                "github_username": github_username,
            }
        )
        return self.db.get_user(user_id)

    def get_user(self, user_id: int) -> Dict[str, Any]:
        user = self.db.get_user(user_id)
        if not user:
            raise DomainError("Usuario no encontrado.")
        return user

    def compatibility(self, user_id: int, target_id: int) -> Dict[str, Any]:
        user = self.get_user(user_id)
        target = self.get_user(target_id)
        score = self.matcher.calculate_compatibility(user, target)
        return {"user_id": user_id, "target_id": target_id, "score": score}

    def send_pull_request(
        self, from_user_id: int, to_user_id: int, bounty_id: int | None = None
    ) -> Dict[str, Any]:
        if from_user_id == to_user_id:
            raise DomainError("No puedes enviarte PR a ti mismo.")
        self.get_user(from_user_id)
        target_user = self.get_user(to_user_id)
        if bounty_id is not None:
            bounty = self.db.get_bounty(bounty_id)
            if not bounty:
                raise DomainError("Bounty no existe.")
            if int(bounty["creator_id"]) != int(to_user_id):
                raise DomainError("El bounty debe pertenecer al destinatario del PR.")
            pr = self.db.create_or_get_pull_request_with_bounty(
                from_user_id, to_user_id, bounty_id=bounty_id
            )
            if bounty["status"] == "Open":
                self.db.update_bounty_assignment(
                    bounty_id=bounty_id,
                    assigned_user_id=from_user_id,
                    status="In_Progress",
                )
        else:
            pr = self.db.create_or_get_pull_request(from_user_id, to_user_id)
        if not pr:
            raise DomainError("No se pudo crear la Pull Request.")

        # Modo demo: si el perfil destino es stress_, mergeamos de inmediato
        # para abrir chat real y persistente en BD.
        if str(target_user.get("username", "")).startswith("stress_"):
            if pr["status"] != "merged":
                self.db.merge_pull_request(pr["id"])
            chat_id = self.db.get_or_create_chat(from_user_id, to_user_id)
            return {
                "id": pr["id"],
                "status": "merged",
                "matched": True,
                "chat_id": chat_id,
                "bounty_id": pr.get("bounty_id"),
                "from_user_id": from_user_id,
                "to_user_id": to_user_id,
            }

        reverse_pr = self.db.get_pull_request_between(to_user_id, from_user_id)
        if reverse_pr:
            if pr["status"] != "merged":
                self.db.merge_pull_request(pr["id"])
            if reverse_pr["status"] != "merged":
                self.db.merge_pull_request(reverse_pr["id"])
            chat_id = self.db.get_or_create_chat(from_user_id, to_user_id)
            return {
                "id": pr["id"],
                "status": "merged",
                "matched": True,
                "chat_id": chat_id,
                "bounty_id": pr.get("bounty_id"),
                "from_user_id": from_user_id,
                "to_user_id": to_user_id,
            }

        return {
            "id": pr["id"],
            "status": pr["status"],
            "matched": False,
            "bounty_id": pr.get("bounty_id"),
            "from_user_id": pr["from_user_id"],
            "to_user_id": pr["to_user_id"],
        }

    def merge_pull_request(self, pr_id: int) -> Dict[str, Any]:
        pr = self.db.get_pull_request(pr_id)
        if not pr:
            raise DomainError("Pull Request no existe.")
        if pr["status"] == "merged":
            chat_id = self.db.get_or_create_chat(pr["from_user_id"], pr["to_user_id"])
            result = {"pull_request_id": pr_id, "chat_id": chat_id, "status": "merged"}
            if pr.get("bounty_id"):
                result["bounty_id"] = pr["bounty_id"]
            return result

        self.db.merge_pull_request(pr_id)
        chat_id = self.db.get_or_create_chat(pr["from_user_id"], pr["to_user_id"])
        result = {"pull_request_id": pr_id, "chat_id": chat_id, "status": "merged"}
        bounty_id = pr.get("bounty_id")
        if bounty_id:
            bounty = self.db.get_bounty(int(bounty_id))
            if bounty and bounty["status"] != "Merged":
                self.db.mark_bounty_merged_and_paid(int(bounty_id))
                # Simulación payout escrow: pagar al ejecutor del PR.
                self.db.adjust_user_balance(int(pr["from_user_id"]), float(bounty["reward_amount"]))
                result["bounty_id"] = int(bounty_id)
                result["bounty_paid"] = True
        return result

    def send_message(self, chat_id: int, sender_id: int, body: str) -> Dict[str, Any]:
        self.get_user(sender_id)
        if not self.db.chat_has_user(chat_id, sender_id):
            raise DomainError("No tienes acceso a este chat.")
        safe_body = sanitize_chat_message(body)
        message_id = self.db.create_message(chat_id, sender_id, safe_body)
        return {
            "id": message_id,
            "chat_id": chat_id,
            "sender_id": sender_id,
            "body": safe_body,
        }

    def list_messages(self, chat_id: int) -> list[Dict[str, Any]]:
        return self.db.list_messages(chat_id)

    def get_scratchpad(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        self.get_user(user_id)
        if not self.db.chat_has_user(chat_id, user_id):
            raise DomainError("No tienes acceso a este scratchpad.")
        return self.db.get_chat_scratchpad(chat_id)

    def update_scratchpad(self, chat_id: int, user_id: int, content: str) -> Dict[str, Any]:
        self.get_user(user_id)
        if not self.db.chat_has_user(chat_id, user_id):
            raise DomainError("No tienes acceso a este scratchpad.")
        safe_content = str(content or "")
        if len(safe_content) > 20000:
            raise DomainError("Scratchpad excede 20000 caracteres.")
        return self.db.upsert_chat_scratchpad(chat_id, safe_content, user_id)

    def export_gist(
        self,
        user_id: int,
        chat_id: int,
        content: str,
        filename: str | None = None,
        language: str | None = None,
    ) -> Dict[str, Any]:
        user = self.get_user(user_id)
        if not self.db.chat_has_user(chat_id, user_id):
            raise DomainError("No tienes acceso a este chat para exportar.")
        body = str(content or "").strip()
        if not body:
            scratch = self.db.get_chat_scratchpad(chat_id)
            body = str(scratch.get("content", "")).strip()
        if not body:
            raise DomainError("No hay contenido para exportar.")
        fname = str(filename or "").strip() or f"codecommit-chat-{chat_id}.txt"
        lang = str(language or "").strip().lower() or "text"
        fake_id = abs(hash(f"{user['username']}:{chat_id}:{fname}:{len(body)}")) % (10**10)
        gist_url = f"https://gist.github.com/{user['username']}/{fake_id:010d}"
        return {
            "simulated": True,
            "gist_url": gist_url,
            "filename": fname,
            "language": lang,
            "chat_id": chat_id,
            "exported_chars": len(body),
        }

    def list_profiles(self, user_id: int, stack_filter: str | None = None) -> list[Dict[str, Any]]:
        profiles = list(self.db.list_users(exclude_user_id=user_id))
        if not stack_filter:
            return profiles
        target = stack_filter.strip().lower()
        if not target:
            return profiles
        return [
            p
            for p in profiles
            if any(str(lang).strip().lower() == target for lang in p.get("stack", []))
        ]

    def create_feed_post(
        self,
        user_id: int,
        title: str,
        content: str,
        category: str,
    ) -> Dict[str, Any]:
        user = self.get_user(user_id)
        normalized_category = str(category or "").strip().upper()
        allowed = {"NEWS", "TECH", "BUG", "SECURITY"}
        if normalized_category not in allowed:
            raise DomainError("category invalida. Usa NEWS, TECH, BUG o SECURITY.")

        # Regla de exclusividad: SECURITY solo para Senior Architect (>8 años)
        if normalized_category == "SECURITY" and int(user["years"]) <= 8:
            raise DomainError("Solo Senior Architect (>8 años) puede publicar SECURITY.")

        safe_title = str(title or "").strip()
        safe_content = str(content or "").strip()
        if len(safe_title) < 3:
            raise DomainError("title debe tener al menos 3 caracteres.")
        if len(safe_content) < 5:
            raise DomainError("content debe tener al menos 5 caracteres.")

        post_id = self.db.create_feed_post(
            user_id=user_id,
            title=safe_title,
            content=safe_content,
            category=normalized_category,
        )
        return {"id": post_id, "user_id": user_id, "category": normalized_category}

    def list_feed_posts(self, limit: int = 20) -> list[Dict[str, Any]]:
        return self.db.list_feed_posts(limit=limit)

    @staticmethod
    def _normalize_target_type(target_type: str) -> str:
        normalized = str(target_type or "").strip().lower()
        if normalized in {"news", "feed"}:
            return "news"
        if normalized in {"resource", "resources"}:
            return "resource"
        raise DomainError("target_type invalido. Usa news o resource.")

    def _ensure_target_exists(self, target_type: str, target_id: int) -> None:
        normalized = self._normalize_target_type(target_type)
        if normalized == "news":
            if not self.db.get_feed_post(int(target_id)):
                raise DomainError("Publicacion news no existe.")
            return
        if not self.db.get_resource(int(target_id)):
            raise DomainError("Publicacion resource no existe.")

    def create_cluster(
        self,
        creator_id: int,
        name: str,
        description: str,
        min_karma_required: int,
        tech_stack_focus: str | None,
    ) -> Dict[str, Any]:
        self.get_user(creator_id)
        safe_name = str(name or "").strip()
        safe_description = str(description or "").strip()
        safe_focus = str(tech_stack_focus or "").strip() or None
        min_karma = int(min_karma_required or 0)
        if len(safe_name) < 3:
            raise DomainError("name del cluster muy corto.")
        if len(safe_description) < 10:
            raise DomainError("description del cluster muy corta.")
        if min_karma < 0:
            raise DomainError("min_karma_required no puede ser negativo.")
        try:
            cluster_id = self.db.create_cluster(
                name=safe_name,
                description=safe_description,
                creator_id=creator_id,
                min_karma_required=min_karma,
                tech_stack_focus=safe_focus,
            )
        except Exception as err:
            raise DomainError("No se pudo crear el cluster (nombre duplicado o datos invalidos).") from err
        return {"id": cluster_id, "creator_id": creator_id, "name": safe_name}

    def list_clusters(self, query: str | None = None, limit: int = 50) -> list[Dict[str, Any]]:
        return self.db.list_clusters(query=query, limit=limit)

    def join_cluster(self, user_id: int, cluster_id: int) -> Dict[str, Any]:
        user = self.get_user(user_id)
        cluster = self.db.get_cluster(cluster_id)
        if not cluster:
            raise DomainError("Cluster no existe.")
        required = int(cluster.get("min_karma_required", 0) or 0)
        current_karma = int(user.get("karma_score", 0))
        if current_karma < required:
            raise DomainError(
                f"Karma insuficiente para unirte. Requiere {required} y tienes {current_karma}."
            )
        self.db.add_cluster_member(cluster_id, user_id)
        return {"cluster_id": cluster_id, "user_id": user_id, "joined": True}

    def interact_feed(
        self,
        user_id: int,
        target_type: str,
        target_id: int,
        interaction_type: str,
        fork_cluster_id: int | None = None,
    ) -> Dict[str, Any]:
        self.get_user(user_id)
        normalized_target = self._normalize_target_type(target_type)
        self._ensure_target_exists(normalized_target, target_id)
        normalized_interaction = str(interaction_type or "").strip().upper()
        if normalized_interaction not in {"ACK", "FORK"}:
            raise DomainError("interaction_type invalido. Usa ACK o FORK.")
        if normalized_interaction == "FORK" and fork_cluster_id is not None:
            cluster = self.db.get_cluster(int(fork_cluster_id))
            if not cluster:
                raise DomainError("fork_cluster_id no existe.")
            if not self.db.is_cluster_member(int(fork_cluster_id), user_id):
                raise DomainError("Debes pertenecer al cluster para hacer FORK hacia ese destino.")

        interaction_id = self.db.create_feed_interaction(
            user_id=user_id,
            target_type=normalized_target,
            target_id=int(target_id),
            interaction_type=normalized_interaction,
            fork_cluster_id=int(fork_cluster_id) if fork_cluster_id is not None else None,
        )
        return {
            "id": interaction_id,
            "user_id": user_id,
            "target_type": normalized_target,
            "target_id": int(target_id),
            "interaction_type": normalized_interaction,
            "fork_cluster_id": int(fork_cluster_id) if fork_cluster_id is not None else None,
        }

    def list_interactions(self, target_type: str, target_id: int, limit: int = 200) -> list[Dict[str, Any]]:
        normalized_target = self._normalize_target_type(target_type)
        self._ensure_target_exists(normalized_target, target_id)
        return self.db.list_feed_interactions(normalized_target, int(target_id), limit=limit)

    def create_thread_comment(
        self,
        user_id: int,
        target_type: str,
        target_id: int,
        content: str,
        parent_thread_id: int | None = None,
    ) -> Dict[str, Any]:
        self.get_user(user_id)
        normalized_target = self._normalize_target_type(target_type)
        self._ensure_target_exists(normalized_target, target_id)
        safe_content = str(content or "").strip()
        if len(safe_content) < 2:
            raise DomainError("content muy corto para THREAD.")
        if parent_thread_id is not None:
            parent = self.db.get_feed_thread(int(parent_thread_id))
            if not parent:
                raise DomainError("parent_thread_id no existe.")
            if (
                str(parent.get("target_type")) != normalized_target
                or int(parent.get("target_id")) != int(target_id)
            ):
                raise DomainError("parent_thread_id no corresponde a la misma publicacion.")
        thread_id = self.db.create_feed_thread(
            user_id=user_id,
            target_type=normalized_target,
            target_id=int(target_id),
            content=safe_content,
            parent_thread_id=int(parent_thread_id) if parent_thread_id is not None else None,
        )
        return {
            "id": thread_id,
            "user_id": user_id,
            "target_type": normalized_target,
            "target_id": int(target_id),
            "parent_thread_id": int(parent_thread_id) if parent_thread_id is not None else None,
        }

    def list_thread_comments(self, target_type: str, target_id: int, limit: int = 200) -> list[Dict[str, Any]]:
        normalized_target = self._normalize_target_type(target_type)
        self._ensure_target_exists(normalized_target, target_id)
        return self.db.list_feed_threads(normalized_target, int(target_id), limit=limit)

    def get_github_repositories(self, github_username: str) -> Dict[str, Any]:
        # Simulación local del fetch de repos para fase inicial.
        username = str(github_username or "").strip()
        if not username:
            raise DomainError("github username invalido.")
        seed = sum(ord(ch) for ch in username)
        sample = [
            f"{username}-core-api",
            f"{username}-infra-k8s",
            f"{username}-awesome-cli",
            f"{username}-frontend-lab",
        ]
        repos = sample[: 2 + (seed % 3)]
        return {"github_username": username, "repositories": repos, "simulated": True}

    def lock_funds(self, user_id: int, amount: float) -> Dict[str, Any]:
        if amount <= 0:
            raise DomainError("reward_amount debe ser positivo.")
        balance = self.db.get_user_balance(user_id)
        if balance < amount:
            raise DomainError("Saldo insuficiente para abrir bounty.")
        self.db.adjust_user_balance(user_id, -amount)
        return {"locked": True, "remaining_balance": round(balance - amount, 2)}

    def create_bounty(
        self,
        creator_id: int,
        title: str,
        description: str,
        reward_amount: float,
        reward_currency: str,
        tech_stack: str,
    ) -> Dict[str, Any]:
        self.get_user(creator_id)
        title = str(title or "").strip()
        description = str(description or "").strip()
        tech_stack = str(tech_stack or "").strip()
        reward_currency = str(reward_currency or "USD").strip().upper()
        reward_amount = float(reward_amount)

        if len(title) < 3:
            raise DomainError("title muy corto.")
        if len(description) < 8:
            raise DomainError("description muy corta.")
        if reward_currency not in {"USD", "SATS"}:
            raise DomainError("reward_currency debe ser USD o SATS.")

        lock = self.lock_funds(creator_id, reward_amount)
        bounty_id = self.db.create_bounty(
            creator_id=creator_id,
            title=title,
            description=description,
            reward_amount=reward_amount,
            reward_currency=reward_currency,
            tech_stack=tech_stack,
            status="Open",
            escrow_locked=True,
        )
        return {"id": bounty_id, "status": "Open", "escrow": lock}

    def list_bounties(self, status: str | None = None) -> list[Dict[str, Any]]:
        normalized = status if status in {None, "Open", "In_Progress", "Merged"} else None
        return self.db.list_bounties(status=normalized)

    def sync_github_activity(self, user_id: int) -> Dict[str, Any]:
        self.get_user(user_id)
        ts = datetime.now(timezone.utc).isoformat()
        self.db.update_last_github_activity(user_id, ts)
        return {"user_id": user_id, "last_github_activity": ts, "simulated": True}

    @staticmethod
    def _is_recent_activity(ts_iso: str | None, hours: int = 48) -> bool:
        if not ts_iso:
            return False
        try:
            dt = datetime.fromisoformat(ts_iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        return dt >= datetime.now(timezone.utc) - timedelta(hours=hours)

    def suggested_matches(self, user_id: int, limit: int = 10) -> list[Dict[str, Any]]:
        user = self.get_user(user_id)
        base_stack = {str(lang).strip().lower() for lang in user.get("stack", [])}
        candidates = self.list_profiles(user_id=user_id)

        ranked: list[Dict[str, Any]] = []
        for cand in candidates:
            cand_stack_raw = cand.get("stack", [])
            cand_stack = {str(lang).strip().lower() for lang in cand_stack_raw}
            common = sorted(base_stack & cand_stack)
            stack_match_count = len(common)
            is_active = self._is_recent_activity(cand.get("last_github_activity"))
            bounty_solved = self.db.count_merged_bounties_by_user(int(cand["id"]))
            bounty_hunter = bounty_solved > 0

            # Priorización lexicográfica: stack > pulse > bounty.
            score_tuple = (stack_match_count, int(is_active), int(bounty_hunter), bounty_solved)
            score = (stack_match_count * 100) + (30 if is_active else 0) + (20 if bounty_hunter else 0) + min(bounty_solved, 10)

            level = "low"
            if stack_match_count >= 2 and is_active and bounty_hunter:
                level = "high"
            elif stack_match_count >= 1 and (is_active or bounty_hunter):
                level = "medium"

            ranked.append(
                {
                    **cand,
                    "ai_recommended": True,
                    "recommendation_score": score,
                    "recommendation_level": level,
                    "recommendation_reason": {
                        "common_stack": common,
                        "stack_match_count": stack_match_count,
                        "active_in_last_48h": is_active,
                        "bounties_solved": bounty_solved,
                        "bounty_hunter": bounty_hunter,
                    },
                    "_score_tuple": score_tuple,
                }
            )

        ranked.sort(
            key=lambda item: (
                item["_score_tuple"][0],
                item["_score_tuple"][1],
                item["_score_tuple"][2],
                item["_score_tuple"][3],
                item["years"],
            ),
            reverse=True,
        )
        for item in ranked:
            item.pop("_score_tuple", None)
        return ranked[: max(1, min(limit, 50))]

    def create_showcase_project(
        self,
        user_id: int,
        title: str,
        description: str,
        price: float | None,
        demo_url: str | None,
        image_url: str | None,
    ) -> Dict[str, Any]:
        self.get_user(user_id)
        title = str(title or "").strip()
        description = str(description or "").strip()
        demo_url = str(demo_url or "").strip() or None
        image_url = str(image_url or "").strip() or None
        parsed_price = None if price in (None, "") else float(price)
        if len(title) < 3:
            raise DomainError("title muy corto para showcase.")
        if len(description) < 10:
            raise DomainError("description muy corta para showcase.")
        if parsed_price is not None and parsed_price < 0:
            raise DomainError("price no puede ser negativo.")
        pid = self.db.create_showcase_project(
            user_id=user_id,
            title=title,
            description=description,
            price=parsed_price,
            demo_url=demo_url,
            image_url=image_url,
        )
        return {"id": pid, "user_id": user_id, "title": title}

    def list_showcase_projects(self, limit: int = 30) -> list[Dict[str, Any]]:
        return self.db.list_showcase_projects(limit=limit)

    def create_resource(self, user_id: int, link: str, topic: str) -> Dict[str, Any]:
        self.get_user(user_id)
        link = str(link or "").strip()
        topic = str(topic or "").strip()
        if not link.startswith(("http://", "https://")):
            raise DomainError("link debe iniciar con http:// o https://")
        if topic.lower() not in {"frontend", "backend", "ai"}:
            raise DomainError("topic debe ser Frontend, Backend o AI.")
        rid = self.db.create_resource(user_id=user_id, link=link, topic=topic)
        return {"id": rid, "user_id": user_id, "topic": topic}

    def list_resources(self, topic: str | None = None, limit: int = 50) -> list[Dict[str, Any]]:
        return self.db.list_resources(topic=topic, limit=limit)

    def mark_resource_helpful(self, voter_user_id: int, resource_id: int) -> Dict[str, Any]:
        self.get_user(voter_user_id)
        resource = self.db.get_resource(resource_id)
        if not resource:
            raise DomainError("Resource no existe.")
        author_id = int(resource["user_id"])
        if author_id == int(voter_user_id):
            raise DomainError("No puedes votar Helpful sobre tu propio recurso.")
        self.db.increment_resource_helpful(resource_id)
        self.db.adjust_user_karma(author_id, 5)
        updated = self.db.get_resource(resource_id)
        author = self.get_user(author_id)
        return {
            "resource_id": resource_id,
            "helpful_count": int(updated["helpful_count"]) if updated else None,
            "author_id": author_id,
            "author_karma_score": int(author.get("karma_score", 0)),
        }

    def collaborate_showcase(self, buyer_user_id: int, project_id: int) -> Dict[str, Any]:
        self.get_user(buyer_user_id)
        project = self.db.get_showcase_project(project_id)
        if not project:
            raise DomainError("Project no existe.")
        creator_id = int(project["user_id"])
        if creator_id == int(buyer_user_id):
            raise DomainError("No puedes colaborar contigo mismo.")
        self.db.adjust_user_karma(creator_id, 20)
        creator = self.get_user(creator_id)
        return {
            "project_id": project_id,
            "creator_id": creator_id,
            "creator_karma_score": int(creator.get("karma_score", 0)),
            "collaboration": "recorded",
        }

    def top_karma_users(self, limit: int = 10) -> list[Dict[str, Any]]:
        users = self.db.list_top_karma_users(limit=limit)
        output = []
        for idx, user in enumerate(users, start=1):
            years = int(user.get("years", 0))
            seniority = "Senior Architect" if years > 8 else "Junior Dev" if years < 4 else "Mid Engineer"
            stack = user.get("stack", [])
            output.append(
                {
                    "rank": idx,
                    "id": user["id"],
                    "username": user["username"],
                    "avatar_url": user.get("avatar_url"),
                    "karma_score": int(user.get("karma_score", 0)),
                    "stack_primary": stack[0] if stack else None,
                    "years": years,
                    "seniority": seniority,
                }
            )
        return output

    def global_stats(self) -> Dict[str, Any]:
        return self.db.get_global_stats()

    def admin_analytics(self) -> Dict[str, Any]:
        users = list(self.db.list_users())
        bounties = self.db.list_bounties()
        resources = self.db.list_resources(limit=10000)

        total_karma = sum(int(u.get("karma_score", 0)) for u in users)
        bounty_total_value = round(sum(float(b.get("reward_amount", 0)) for b in bounties), 2)
        bounty_open_value = round(
            sum(float(b.get("reward_amount", 0)) for b in bounties if str(b.get("status")) == "Open"),
            2,
        )
        bounty_in_progress_value = round(
            sum(
                float(b.get("reward_amount", 0))
                for b in bounties
                if str(b.get("status")) == "In_Progress"
            ),
            2,
        )
        stack_counter: Counter[str] = Counter()
        for u in users:
            for lang in u.get("stack", []):
                norm = str(lang).strip()
                if norm:
                    stack_counter[norm] += 1
        top_stacks = [
            {"stack": stack, "count": count}
            for stack, count in sorted(stack_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
        ]

        return {
            "users_total": len(users),
            "resources_total": len(resources),
            "karma_total": total_karma,
            "bounties_total_value": bounty_total_value,
            "bounties_open_value": bounty_open_value,
            "bounties_in_progress_value": bounty_in_progress_value,
            "stacks_top": top_stacks,
        }

    def import_github_languages(
        self, user_id: int, github_username: str, github_token: str | None = None
    ) -> Dict[str, Any]:
        user = self.get_user(user_id)
        langs = fetch_top_languages(github_username, token=github_token)
        merged = sorted(set(user["stack"]) | set(langs))
        self.db.update_user_stack(user_id, merged)
        updated = self.get_user(user_id)
        return {"user_id": user_id, "stack": updated["stack"], "imported": langs}
