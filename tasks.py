import os
from typing import Iterator, Tuple
from pathlib import Path
from minimalci.tasks import Task, Status  # type: ignore
from minimalci.executors import Executor, Local, LocalContainer, NonZeroExit  # type: ignore

import checks

SOURCE: Path
IMAGE: str
CTX: checks.Config


def run_and_capture_lines(exe: Executor, cmd: str) -> Tuple[Iterator[str], bool]:
    failed = False
    try:
        raw_output = exe.sh(cmd)
    except NonZeroExit as ex:
        raw_output = ex.stdout
        failed = True
    return raw_output.decode().split("\r\n"), failed


def get_checks_ctx(commit: str) -> checks.Config:
    private_key = Path("private_key.pem").read_text()
    _, _, repo = os.environ["REPO_URL"].partition(":")
    repo, _, _ = repo.partition(".")
    token = checks.create_token(private_key)
    return checks.Config(repo, commit, token)


class Setup(Task):
    def run(self) -> None:
        with Local() as exe:
            global SOURCE
            global IMAGE
            global CTX
            SOURCE = exe.stash("*")
            IMAGE = f"test:{self.state.commit}"
            exe.unstash(self.state.secrets, "private_key.pem")
            CTX = get_checks_ctx(self.state.commit)
            checks.start(CTX, "pylint")
            checks.start(CTX, "mypy")
            checks.start(CTX, "ci")


class Build(Task):
    run_after = [Setup]

    def run(self) -> None:
        with Local() as exe:
            exe.unstash(SOURCE)
            exe.sh(f"docker build . -t {IMAGE}")


class Pylint(Task):
    run_after = [Build]

    def run(self) -> None:
        with LocalContainer(IMAGE) as exe:
            lines, _ = run_and_capture_lines(exe, "make lint")
            checks.conclude(CTX, "pylint", from_lines=lines)


class Mypy(Task):
    run_after = [Build]

    def run(self) -> None:
        with LocalContainer(IMAGE) as exe:
            lines, failed = run_and_capture_lines(exe, "make typecheck")
            checks.conclude(CTX, "mypy", from_lines=lines)
            assert not failed


class Finally(Task):
    run_after = [Pylint, Mypy]
    run_always = True

    def run(self) -> None:
        with Local() as exe:
            exe.unstash(SOURCE)
            if all(t.status == Status.success for t in self.state.tasks if t != self):
                conclusion = "success"
            else:
                conclusion = "failure"
            print(f"Setting github check conclusion {conclusion}")
            checks.conclude(CTX, "ci", conclusion)
