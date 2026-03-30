from random import choice, randint

from .auth import hash_password
from .config import DB_PATH
from .db import Database
from .service import CodeCommitService


STACKS = {
    "frontend": ["JavaScript", "TypeScript", "React", "Vue", "CSS"],
    "backend": ["Python", "Go", "Node.js", "PostgreSQL", "Redis"],
    "mobile": ["Kotlin", "Swift", "Flutter", "React Native", "Firebase"],
    "devops": ["Docker", "Kubernetes", "Terraform", "AWS", "Linux"],
}

USERNAMES = [
    "ana_front",
    "bruno_ui",
    "carla_css",
    "diego_react",
    "elena_vue",
    "fabian_api",
    "gaby_python",
    "hector_go",
    "ines_node",
    "jorge_db",
    "karla_android",
    "leo_ios",
    "maria_flutter",
    "nico_mobile",
    "olga_rn",
    "pablo_ops",
    "quime_devops",
    "rocio_sre",
    "santi_k8s",
    "tania_cloud",
]


def build_profile(username: str, index: int) -> dict:
    if index < 5:
        family = "frontend"
    elif index < 10:
        family = "backend"
    elif index < 15:
        family = "mobile"
    else:
        family = "devops"

    stack_base = STACKS[family]
    stack = [stack_base[0], stack_base[1], choice(stack_base[2:])]
    years_exp = randint(1, 12)
    tabs_vs_spaces = bool(index % 2)
    return {
        "username": username,
        "password_hash": hash_password("CodeCommit123!"),
        "stack": stack,
        "years": years_exp,
        "years_exp": years_exp,
        "prefers_tabs": tabs_vs_spaces,
        "tabs_vs_spaces": tabs_vs_spaces,
        "dark_mode": bool((index + 1) % 2),
        "github_username": username,
        "puzzle_answer": "1",
        "avatar_url": f"https://api.dicebear.com/7.x/bottts/svg?seed={username}",
        "setup_url": f"https://picsum.photos/seed/{index + 1}/800/600",
    }


def main():
    db = Database(DB_PATH)
    service = CodeCommitService(db)
    created = 0

    for idx, username in enumerate(USERNAMES):
        if db.get_user_by_username(username):
            continue
        payload = build_profile(username, idx)
        user = service.register_user(payload)
        db.update_user_images(
            user["id"],
            avatar_url=payload["avatar_url"],
            setup_url=payload["setup_url"],
        )
        created += 1

    print(f"Seed completado. Perfiles creados: {created}")
    print("Password para todos los usuarios seed: CodeCommit123!")


if __name__ == "__main__":
    main()
