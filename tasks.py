import os
from typing import Iterator, Tuple
from pathlib import Path
from minimalci.tasks import Task, Status  # type: ignore
from minimalci.executors import Executor, Local, LocalContainer, NonZeroExit  # type: ignore

import checks

# Checks stuff
APP_ID = "56533"
INSTALLATION_ID = "7163640"


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
    token = checks.create_token(private_key, APP_ID, INSTALLATION_ID)
    return checks.Config(repo, commit, token)


class Setup(Task):
    def run(self) -> None:
        with Local() as exe:
            self.state.source = exe.stash("*")
            self.state.image = f"test:{self.state.commit}"
            exe.unstash(self.state.secrets, "private_key.pem")
            self.state.ctx = get_checks_ctx(self.state.commit)
            checks.start(self.state.ctx, "ci", details_url=self.state.log_url)
            checks.start(self.state.ctx, "pylint", details_url=f"{self.state.log_url}/#Pylint")
            checks.start(self.state.ctx, "mypy", details_url=f"{self.state.log_url}/#Mypy")


class Build(Task):
    run_after = [Setup]

    def run(self) -> None:
        with Local() as exe:
            exe.unstash(self.state.source)
            exe.sh(f"docker build . -t {self.state.image}")


class Pylint(Task):
    run_after = [Build]

    def run(self) -> None:
        with LocalContainer(self.state.image) as exe:
            lines, _ = run_and_capture_lines(exe, "make lint")
            checks.conclude(self.state.ctx, "pylint", from_lines=lines)


class Mypy(Task):
    run_after = [Build]

    def run(self) -> None:
        with LocalContainer(self.state.image) as exe:
            lines, failed = run_and_capture_lines(exe, "make typecheck")
            checks.conclude(self.state.ctx, "mypy", from_lines=lines)
            assert not failed


class Finally(Task):
    run_after = [Pylint, Mypy]
    run_always = True

    def run(self) -> None:
        with Local() as exe:
            exe.unstash(self.state.source)
            if all(t.status == Status.success for t in self.state.tasks if t != self):
                conclusion = "success"
            else:
                conclusion = "failure"
            print(f"Setting github check conclusion {conclusion}")
            checks.conclude(self.state.ctx, "ci", conclusion)
