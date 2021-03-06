#!/usr/bin/env python3
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from pprint import pprint
from typing import Dict, cast, List, Optional, Tuple, Iterator, TypeVar, Callable
import subprocess as sp
import os
import sys
import time

from jose import jwt  # type: ignore
import httpx


T = TypeVar("T")


@dataclass
class Config:
    repo: str
    sha: str
    token: str


class AnnotationLevel(Enum):
    FAILURE = "failure"
    WARNING = "warning"
    NOTICE = "notice"

    # pylint: disable=inconsistent-return-statements

    @classmethod
    def from_mypy_level(cls, level: str) -> AnnotationLevel:
        if level == "error":
            return cls.FAILURE
        assert False

    @classmethod
    def from_pylint_level(cls, level: str) -> AnnotationLevel:
        if level in ["E", "F"]:
            return cls.FAILURE
        if level == "W":
            return cls.WARNING
        if level in ["R", "C"]:
            return cls.NOTICE
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
    title: str = ""

    def asdict(self) -> dict:
        return {
            "path": self.loc.path,
            "start_line": self.loc.line_no,
            "end_line": self.loc.line_no,
            "annotation_level": self.level.value,
            "message": self.msg,
            "title": self.title,
        }


@dataclass
class Annotations:
    title: str
    summary: str
    annotations: List[Annotation]


MACHINE_MAN_ACCEPT_HEADER = "application/vnd.github.machine-man-preview+json"
PREVIEW_ACCEPT_HEADER = "application/vnd.github.antiope-preview+json"
GH_API = "https://api.github.com"


def machine_man_headers(jwt_token: str,) -> Dict[str, str]:
    return {"Authorization": f"Bearer {jwt_token}", "Accept": MACHINE_MAN_ACCEPT_HEADER}


def create_token(private_key: str, app_id: str, installation_id: str) -> str:
    now = int(time.time()) - 5
    payload = {"iat": now, "exp": now + 600, "iss": app_id}
    jwt_token = jwt.encode(payload, private_key, jwt.ALGORITHMS.RS256)
    resp = httpx.post(
        f"{GH_API}/app/installations/{installation_id}/access_tokens",
        headers=machine_man_headers(jwt_token),
    )
    resp.raise_for_status()
    return cast(dict, resp.json())["token"]


def headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": PREVIEW_ACCEPT_HEADER}


def url(ctx: Config, suffix: str) -> str:
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


def start(ctx: Config, check_name: str, details_url: Optional[str] = None) -> str:
    body = {"name": check_name, "head_sha": ctx.sha, "status": "in_progress"}
    if details_url:
        body["details_url"] = details_url
    return cast(dict, post(ctx, "check-runs", body).json())["id"]


def list_check_runs(ctx: Config) -> dict:
    return cast(dict, get(ctx, f"commits/{ctx.sha}/check-runs").json())["check_runs"]


def check_run_id(ctx: Config, check_name) -> str:
    check_runs = [r["id"] for r in list_check_runs(ctx) if r["name"] == check_name]
    if not check_runs:
        return start(ctx, check_name)
    return check_runs[0]


def conclude(
    ctx: Config,
    check_name: str,
    conclusion: Optional[str] = None,
    from_lines: Optional[Iterator[str]] = None,
) -> None:
    current_check = check_run_id(ctx, check_name)
    body = {"status": "completed", "conclusion": conclusion}
    if conclusion is not None:
        patch(ctx, f"check-runs/{current_check}", body)
        return
    assert from_lines is not None
    if check_name == "pylint":
        annotations = parse_pylint(from_lines)
    elif check_name == "mypy":
        annotations = parse_mypy(from_lines)
    else:
        assert False
    patch(
        ctx,
        f"check-runs/{current_check}",
        {
            "status": "completed",
            "conclusion": get_conclusion(annotations),
            "output": {
                "title": annotations.title,
                "summary": annotations.summary,
                "annotations": [a.asdict() for a in annotations.annotations],
            },
        },
    )


def get_conclusion(annotations: Annotations) -> str:
    if any(a.level == AnnotationLevel.FAILURE for a in annotations.annotations):
        return "failure"
    if any(a.level == AnnotationLevel.WARNING for a in annotations.annotations):
        return "failure"
    if any(a.level == AnnotationLevel.NOTICE for a in annotations.annotations):
        return "neutral"
    return "success"


def get_ctx() -> Config:
    repo = os.getenv("REPO")
    sha = os.getenv("SHA") or sp.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    app_id = "56533"
    installation_id = "7163640"
    token = os.getenv("TOKEN") or create_token(
        Path("private_key.pem").read_text(), app_id, installation_id
    )
    assert repo
    assert sha
    return Config(repo, sha, token)


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


def skip_nones(items: Iterator[Optional[T]]) -> Iterator[T]:
    for item in items:
        if item is not None:
            yield item


def parse_mypy_line(line: str) -> Optional[Annotation]:
    loc, rest = parse_loc(line)
    if not loc:
        return None
    level, _, msg = rest.partition(": ")
    return Annotation(loc, AnnotationLevel.from_mypy_level(level), msg)


def extract_between(lsep: str, rsep: str, line: str) -> Tuple[str, str, str]:
    before, _, stripped = line.partition(lsep)
    extracted, _, after = stripped.rpartition(rsep)
    return before, extracted, after


def parse_pylint_line(line: str) -> Optional[Annotation]:
    loc, rest = parse_loc(line)
    if not loc:
        return None
    _, error_spec, msg = extract_between("[", "]", rest)
    error_code, error_name, _ = extract_between("(", ")", error_spec)
    return Annotation(
        loc, AnnotationLevel.from_pylint_level(error_code[0]), msg.strip(), error_name
    )


def parse_annotations(
    parser: Callable[[str], Optional[Annotation]], lines: Iterator[str]
) -> List[Annotation]:
    return list(skip_nones(map(parser, lines)))


def parse_mypy(lines: Iterator[str]) -> Annotations:
    return Annotations("Mypy", "Result of mypy checks", parse_annotations(parse_mypy_line, lines))


def parse_pylint(lines: Iterator[str]) -> Annotations:
    return Annotations(
        "Pylint", "Result of pylint checks", parse_annotations(parse_pylint_line, lines)
    )


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
        start(ctx, sys.argv[2])


if __name__ == "__main__":
    main()
