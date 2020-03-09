import sys
import time
import os
from pathlib import Path
from typing import Dict, cast
from pprint import pprint

from jose import jwt  # type: ignore
import httpx


MACHINE_MAN_ACCEPT_HEADER = "application/vnd.github.machine-man-preview+json"
PREVIEW_ACCEPT_HEADER = "application/vnd.github.antiope-preview+json"
PRIVATE_KEY = Path("private_key.pem")
APP_ID = "56533"
INSTALLATION_ID = "7163640"
GH_API = "https://api.github.com"


def machine_man_headers(jwt_token: str,) -> Dict[str, str]:
    return {"Authorization": f"Bearer {jwt_token}", "Accept": MACHINE_MAN_ACCEPT_HEADER}


def headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": PREVIEW_ACCEPT_HEADER}


def url(suffix: str) -> str:
    return f"{GH_API}/{suffix}"


def create_token() -> str:
    now = int(time.time()) - 5
    payload = {"iat": now, "exp": now + 600, "iss": APP_ID}
    jwt_token = jwt.encode(payload, PRIVATE_KEY.read_text(), jwt.ALGORITHMS.RS256)
    resp = httpx.post(
        url(f"/app/installations/{INSTALLATION_ID}/access_tokens"),
        headers=machine_man_headers(jwt_token),
    )
    resp.raise_for_status()
    return cast(dict, resp.json())["token"]


def start_check_run(token: str, repo: str, sha: str, check_name: str) -> None:
    body = {"name": check_name, "head_sha": sha, "status": "in_progress"}
    resp = httpx.post(url(f"repos/{repo}/check-runs"), json=body, headers=headers(token))
    resp.raise_for_status()


def list_check_runs(token: str, repo: str, sha: str) -> None:
    resp = httpx.get(url(f"repos/{repo}/commits/{sha}/check-runs"), headers=headers(token))
    pprint(resp.json())


def main(action: str):
    token = os.getenv("TOKEN") or create_token()
    repo = os.getenv("REPO")
    sha = os.getenv("SHA")
    assert repo
    assert sha
    if action == "list":
        list_check_runs(token, repo, sha)
    elif action == "start":
        start_check_run(token, repo, sha, "pylint")


if __name__ == "__main__":
    main(sys.argv[1])
