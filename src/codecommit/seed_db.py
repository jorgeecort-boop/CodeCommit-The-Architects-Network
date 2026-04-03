"""
seed_db.py – Poblar la base de datos con usuarios realistas usando RandomUser API.

Estrategia:
  1. Intenta obtener perfiles de https://randomuser.me/api/ (datos reales).
  2. Si la API no está disponible, usa el dataset local de respaldo.

Uso:
    python -m codecommit.seed_db          # desde la raíz del proyecto
    python -m codecommit.seed_db --count 30   # especificar cantidad
"""
from __future__ import annotations

import argparse
import json
import sys
from random import choice, randint, seed as random_seed
from typing import Any
from urllib import request as urllib_request
from urllib.error import URLError

from .auth import hash_password
from .avatars import avatar_url_for_user, setup_url_for_user
from .config import DB_PATH
from .db import Database
from .service import CodeCommitService

random_seed(42)  # reproducible

# ── Constantes ────────────────────────────────────────────────────────────────
SEED_PASSWORD = "CodeCommit123!"

STACKS: dict[str, list[str]] = {
    "frontend":  ["JavaScript", "TypeScript", "React",   "Vue",      "CSS"],
    "backend":   ["Python",     "Go",         "Node.js", "PostgreSQL","Redis"],
    "mobile":    ["Kotlin",     "Swift",      "Flutter", "React Native","Firebase"],
    "devops":    ["Docker",     "Kubernetes", "Terraform","AWS",      "Linux"],
    "ai":        ["Python",     "PyTorch",    "FastAPI", "LangChain","NumPy"],
}

_STACK_FAMILIES = list(STACKS.keys())

# Fallback local si RandomUser no está disponible
_LOCAL_PROFILES: list[dict[str, Any]] = [
    {"username": "ana_front",    "github_username": "anafront",    "years": 3},
    {"username": "bruno_ui",     "github_username": "brunoui",     "years": 5},
    {"username": "carla_css",    "github_username": "carlacss",    "years": 2},
    {"username": "diego_react",  "github_username": "diegoreact",  "years": 6},
    {"username": "elena_vue",    "github_username": "elenavue",    "years": 4},
    {"username": "fabian_api",   "github_username": "fabianapi",   "years": 7},
    {"username": "gaby_python",  "github_username": "gabypython",  "years": 8},
    {"username": "hector_go",    "github_username": "hectorgo",    "years": 9},
    {"username": "ines_node",    "github_username": "inesnode",    "years": 3},
    {"username": "jorge_db",     "github_username": "jorgedb",     "years": 11},
    {"username": "karla_android","github_username": "karlaandroid","years": 4},
    {"username": "leo_ios",      "github_username": "leoios",      "years": 5},
    {"username": "maria_flutter","github_username": "mariaflutter","years": 2},
    {"username": "nico_mobile",  "github_username": "nicomobile",  "years": 3},
    {"username": "olga_rn",      "github_username": "olgarn",      "years": 6},
    {"username": "pablo_ops",    "github_username": "pabloops",    "years": 10},
    {"username": "quime_devops", "github_username": "quimedevops", "years": 7},
    {"username": "rocio_sre",    "github_username": "rociosre",    "years": 8},
    {"username": "santi_k8s",    "github_username": "santik8s",    "years": 5},
    {"username": "tania_cloud",  "github_username": "taniacloud",  "years": 9},
    {"username": "ugo_ai",       "github_username": "ugoai",       "years": 4},
    {"username": "vera_ml",      "github_username": "veraml",      "years": 6},
    {"username": "will_torch",   "github_username": "willtorch",   "years": 3},
    {"username": "xandra_nlp",   "github_username": "xandranl",    "years": 7},
    {"username": "yoshi_llm",    "github_username": "yoshillm",    "years": 5},
]


# ── RandomUser API ─────────────────────────────────────────────────────────────

def _fetch_randomuser(count: int = 20) -> list[dict[str, Any]] | None:
    """
    Llama a https://randomuser.me/api/ y devuelve perfiles procesados.
    Retorna None si la API no está disponible (fail-safe).
    """
    url = f"https://randomuser.me/api/?results={count}&inc=login,name,picture,nat&noinfo"
    try:
        req = urllib_request.Request(url, headers={"User-Agent": "CodeCommitSeed/6.0"})
        with urllib_request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("results", [])
        profiles = []
        for r in results:
            login = r.get("login", {})
            username = login.get("username", "")[:32]
            if not username:
                continue
            profiles.append({
                "username": username,
                "github_username": username,
                # RandomUser proporciona fotos reales del perfil
                "avatar_override": r.get("picture", {}).get("large"),
                "years": randint(1, 12),
            })
        print(f"  ✅ RandomUser API: {len(profiles)} perfiles obtenidos.")
        return profiles
    except (URLError, OSError, Exception) as exc:
        print(f"  ⚠️  RandomUser no disponible ({exc}) – usando perfiles locales.")
        return None


# ── Build payload ──────────────────────────────────────────────────────────────

def _build_payload(profile: dict[str, Any], index: int) -> dict[str, Any]:
    """Construye el payload de registro para un perfil."""
    family = _STACK_FAMILIES[index % len(_STACK_FAMILIES)]
    stack_pool = STACKS[family]
    # 2 tecnologías fijas + 1 aleatoria del pool restante
    stack = [stack_pool[0], stack_pool[1], choice(stack_pool[2:])]
    username: str = profile["username"]

    # Avatar: usa el de RandomUser si existe, sino DiceBear/RoboHash
    avatar_url = profile.get("avatar_override") or avatar_url_for_user(username)
    setup_url = setup_url_for_user(username)

    return {
        "username": username,
        "password_hash": hash_password(SEED_PASSWORD),
        "stack": stack,
        "years": profile.get("years", randint(1, 10)),
        "prefers_tabs": bool(index % 2),
        "dark_mode": bool((index + 1) % 2),
        "github_username": profile.get("github_username", username),
        "puzzle_answer": "1",
        "avatar_url": avatar_url,
        "setup_url": setup_url,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main(count: int = 20, use_api: bool = True) -> None:
    db = Database(DB_PATH)
    svc = CodeCommitService(db)

    print(f"\n🌱 CodeCommit Seed DB (objetivo: {count} usuarios)")
    print("─" * 50)

    # Obtener perfiles
    profiles: list[dict[str, Any]] | None = None
    if use_api:
        profiles = _fetch_randomuser(count)

    if not profiles:
        # Fallback: recortar o extender la lista local
        profiles = _LOCAL_PROFILES[:count]
        if len(profiles) < count:
            # Si se pide más de lo que hay en local, extender con variaciones
            extra_needed = count - len(profiles)
            for i in range(extra_needed):
                base = _LOCAL_PROFILES[i % len(_LOCAL_PROFILES)]
                profiles.append({
                    "username": f"{base['username']}_{i + 1}",
                    "github_username": f"{base['github_username']}{i + 1}",
                    "years": randint(1, 12),
                })

    created = skipped = 0

    for idx, profile in enumerate(profiles):
        username = profile["username"]

        if db.get_user_by_username(username):
            print(f"  ⏭  {username} ya existe – omitido.")
            skipped += 1
            continue

        payload = _build_payload(profile, idx)

        try:
            user = svc.register_user(payload)
            db.update_user_images(
                user["id"],
                avatar_url=payload["avatar_url"],
                setup_url=payload["setup_url"],
            )
            print(f"  ✓  {username} [{', '.join(payload['stack'][:2])}…]")
            created += 1
        except Exception as exc:
            print(f"  ✗  {username} – ERROR: {exc}")

    print("─" * 50)
    print(f"✅ Completado: {created} creados, {skipped} omitidos.")
    print(f"🔑 Password universal del seed: {SEED_PASSWORD}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed CodeCommit database")
    parser.add_argument("--count", type=int, default=20, help="Número de usuarios a crear")
    parser.add_argument("--no-api", action="store_true", help="No usar RandomUser API")
    args = parser.parse_args()
    main(count=args.count, use_api=not args.no_api)
