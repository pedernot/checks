#!/usr/bin/env python3
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from pprint import pprint
from typing import Dict, cast, List, Optional, Tuple, Iterator
import os
import sys
import time

from jose import jwt  # type: ignore
import httpx


@dataclass
class GitContext:
    repo: str
    sha: str
    token: str


class AnnotationLevel(Enum):
    FAILURE = "failure"
    WARNING = "warning"
    NOTICE = "notice"

    @classmethod
    def from_mypy_level(cls, level: str) -> AnnotationLevel:
        if level == "error":
            return cls.FAILURE
        assert False


@dataclass
class Loc:
    path: str
    line_no: int


@dataclass
class Annotation:
    loc: Loc
    level: AnnotationLevel
    msg: str

    def asdict(self) -> dict:
        return {
            "path": self.loc.path,
            "start_line": self.loc.line_no,
            "end_line": self.loc.line_no,
            "annotation_level": self.level.value,
            "message": self.msg,
        }


@dataclass
class Annotations:
    title: str
    summary: str
    annotations: List[Annotation]


MACHINE_MAN_ACCEPT_HEADER = "application/vnd.github.machine-man-preview+json"
PREVIEW_ACCEPT_HEADER = "application/vnd.github.antiope-preview+json"
PRIVATE_KEY = Path("private_key.pem")
APP_ID = "56533"
INSTALLATION_ID = "7163640"
GH_API = "https://api.github.com"


def machine_man_headers(jwt_token: str,) -> Dict[str, str]:
    return {"Authorization": f"Bearer {jwt_token}", "Accept": MACHINE_MAN_ACCEPT_HEADER}


def create_token() -> str:
    now = int(time.time()) - 5
    payload = {"iat": now, "exp": now + 600, "iss": APP_ID}
    jwt_token = jwt.encode(payload, PRIVATE_KEY.read_text(), jwt.ALGORITHMS.RS256)
    resp = httpx.post(
        f"{GH_API}/app/installations/{INSTALLATION_ID}/access_tokens",
        headers=machine_man_headers(jwt_token),
    )
    resp.raise_for_status()
    return cast(dict, resp.json())["token"]


def headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": PREVIEW_ACCEPT_HEADER}


def url(ctx: GitContext, suffix: str) -> str:
    return f"{GH_API}/repos/{ctx.repo}/{suffix}"


def post(ctx, url_suffix, body: dict) -> httpx.Response:
    resp = httpx.post(url(ctx, url_suffix), json=body, headers=headers(ctx.token))
    resp.raise_for_status()
    return resp


def patch(ctx, url_suffix, body: dict) -> httpx.Response:
    resp = httpx.patch(url(ctx, url_suffix), json=body, headers=headers(ctx.token))
    resp.raise_for_status()
    return resp


def get(ctx, url_suffix) -> httpx.Response:
    resp = httpx.get(url(ctx, url_suffix), headers=headers(ctx.token))
    resp.raise_for_status()
    return resp


def start_check_run(ctx: GitContext, check_name: str) -> None:
    body = {"name": check_name, "head_sha": ctx.sha, "status": "in_progress"}
    post(ctx, "check-runs", body)


def list_check_runs(ctx: GitContext) -> dict:
    return cast(dict, get(ctx, f"commits/{ctx.sha}/check-runs").json())["check_runs"]


def check_run_id(ctx: GitContext, check_name) -> str:
    return [r["id"] for r in list_check_runs(ctx) if r["name"] == check_name][0]


def annotate(ctx: GitContext, check_name: str, annotations: Annotations) -> None:
    return
    current_check = check_run_id(ctx, check_name)
    patch(
        ctx,
        f"check-runs/{current_check}",
        {
            "output": {
                "title": annotations.title,
                "summary": annotations.summary,
                "annotations": [a.asdict() for a in annotations.annotations],
            }
        },
    )


def get_ctx() -> GitContext:
    repo = os.getenv("REPO")
    sha = os.getenv("SHA")
    token = os.getenv("TOKEN") or create_token()
    assert repo
    assert sha
    return GitContext(repo, sha, token)


def parse_loc(line: str) -> Tuple[Optional[Loc], str]:
    loc, _, rest = line.partition(": ")
    if not loc:
        return None, line
    path, _, line_no = loc.partition(":")
    if not path or not line_no:
        return None, line
    if not line_no.isdigit():
        return None, line
    return Loc(path, int(line_no)), rest


def parse_mypy(lines: Iterator[str]) -> Annotations:
    errors = []
    for line in lines:
        loc, rest = parse_loc(line)
        if not loc:
            continue
        level, _, msg = rest.partition(": ")
        print(loc, level, msg)
        errors.append(Annotation(loc, AnnotationLevel.from_mypy_level(level), msg))
    return Annotations("Mypy", "Result of mypy checks", errors)


def parse_pylint(lines: Iterator[str]) -> Annotations:
    pass


def broken_func(foo: str) -> int:
    return foo


def get_lines(path: str) -> Iterator[str]:
    if path == "-":
        yield from sys.stdin
    else:
        yield from Path(path).read_text().split("\n")


def main() -> None:
    ctx = get_ctx()
    action = sys.argv[1]
    if action == "list":
        pprint(list_check_runs(ctx))
    elif action == "start":
        start_check_run(ctx, sys.argv[2])
    elif action == "annotate-mypy":
        annotate(ctx, "mypy", parse_mypy(get_lines(sys.argv[2])))
    elif action == "annotate-pylint":
        annotate(ctx, "pylint", parse_pylint(get_lines(sys.argv[2])))


if __name__ == "__main__":
    main()
