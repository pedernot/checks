import os
from pathlib import Path
from minimalci.tasks import Task
from minimalci.executors import Local, LocalContainer

from checks import GitContext, start_check_run, create_token, annotate, parse_mypy, parse_pylint

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
            exe.unstash(SOURCE)
            output = exe.sh("make lint").decode().split("\n")
            print(output)
            annotate(CTX, "pylint", parse_pylint(output))


class Mypy(Task):
    run_after = [Build]

    def run(self) -> None:
        with LocalContainer(IMAGE) as exe:
            exe.unstash(SOURCE)
            output = exe.sh("make typecheck").decode().split("\n")
            annotate(CTX, "mypy", parse_mypy(output))
