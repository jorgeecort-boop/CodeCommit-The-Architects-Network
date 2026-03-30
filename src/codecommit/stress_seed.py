import argparse
import random
import string
from dataclasses import dataclass

from .auth import hash_password
from .config import DB_PATH
from .db import Database
from .service import CodeCommitService


@dataclass
class StackFamily:
    name: str
    items: list[str]


FAMILIES = [
    StackFamily("frontend", ["JavaScript", "TypeScript", "React", "Vue", "CSS", "Next.js"]),
    StackFamily("backend", ["Python", "Go", "Node.js", "PostgreSQL", "Redis", "FastAPI"]),
    StackFamily("mobile", ["Kotlin", "Swift", "Flutter", "React Native", "Firebase"]),
    StackFamily("devops", ["Docker", "Kubernetes", "Terraform", "AWS", "Linux", "GitHub Actions"]),
]


def random_username(prefix: str = "stress") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{suffix}"


def random_stack() -> list[str]:
    fam = random.choice(FAMILIES)
    return random.sample(fam.items, k=min(3, len(fam.items)))


def build_payload(username: str) -> dict:
    years_exp = random.randint(1, 15)
    tabs_vs_spaces = random.choice([True, False])
    dark_mode = random.choice([True, False])
    return {
        "username": username,
        "password_hash": hash_password("CodeCommit123!"),
        "stack": random_stack(),
        "years": years_exp,
        "years_exp": years_exp,
        "prefers_tabs": tabs_vs_spaces,
        "tabs_vs_spaces": tabs_vs_spaces,
        "dark_mode": dark_mode,
        "github_username": username,
        "puzzle_answer": "1",
        "avatar_url": f"https://api.dicebear.com/7.x/bottts/svg?seed={username}",
        "setup_url": f"https://picsum.photos/seed/{username}/800/600",
    }


def run(count: int):
    db = Database(DB_PATH)
    service = CodeCommitService(db)
    created = 0
    attempts = 0

    while created < count and attempts < count * 10:
        attempts += 1
        username = random_username()
        if db.get_user_by_username(username):
            continue
        payload = build_payload(username)
        user = service.register_user(payload)
        db.update_user_images(
            user["id"],
            avatar_url=payload["avatar_url"],
            setup_url=payload["setup_url"],
        )
        created += 1

    print(f"Stress seed completado. Creados: {created}/{count}")
    print("Password para usuarios stress: CodeCommit123!")


def main():
    parser = argparse.ArgumentParser(description="Genera usuarios random para stress testing.")
    parser.add_argument("--count", type=int, default=100, help="Cantidad de usuarios a crear")
    args = parser.parse_args()
    run(args.count)


if __name__ == "__main__":
    main()

