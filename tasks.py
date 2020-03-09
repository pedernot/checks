import os
from pathlib import Path
from minimalci.tasks import Task, Status
from minimalci.executors import Local, LocalContainer

from checks import (
    GitContext,
    annotate,
    complete_check_run,
    create_token,
    parse_mypy,
    parse_pylint,
    start_check_run,
)

SOURCE: Path
IMAGE: str
CTX: GitContext


def get_checks_ctx(commit: str) -> GitContext:
    private_key = Path("private_key.pem").read_text()
    _, _, repo = os.environ["REPO_URL"].partition(":")
    repo, _, _ = repo.partition(".")
    return GitContext(repo, commit, create_token(private_key))


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
            start_check_run(CTX, "pylint")
            start_check_run(CTX, "mypy")
            start_check_run(CTX, "ci")
            print(CTX.repo)


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
            output = exe.sh("make lint").decode().split("\n")
            annotate(CTX, "pylint", parse_pylint(output))


class Mypy(Task):
    run_after = [Build]

    def run(self) -> None:
        with LocalContainer(IMAGE) as exe:
            output = exe.sh("make typecheck").decode()
            print(output)
            annotate(CTX, "mypy", parse_mypy(output.split("\n")))


class Finally(Task):
    run_after = [Pylint, Mypy]
    run_always = True

    def run(self) -> None:
        with Local() as exe:
            exe.unstash(SOURCE)
            conclusion = (
                "success"
                if all(t.status == Status.success for t in self.state.tasks if t != self)
                else "failure"
            )
            print(f"Setting github check conclusion {conclusion}")
            complete_check_run(CTX, "ci", conclusion)
