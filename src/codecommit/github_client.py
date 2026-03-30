import json
from collections import Counter
from typing import List, Optional
from urllib import request
from urllib.error import HTTPError


def fetch_top_languages(
    github_username: str,
    token: Optional[str] = None,
    base_url: str = "https://api.github.com",
    timeout: int = 10,
) -> List[str]:
    url = f"{base_url}/users/{github_username}/repos?per_page=100&sort=updated"
    req = request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "CodeCommitApp/1.0")

    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as err:
        if err.code == 403:
            raise RuntimeError("GitHub API rate limit or forbidden (403).") from err
        raise RuntimeError(f"GitHub API error ({err.code}).") from err

    counter = Counter()
    for repo in data:
        lang = repo.get("language")
        if lang:
            counter[lang] += 1
    return [name for name, _ in counter.most_common(5)]

