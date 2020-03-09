import os
from pathlib import Path
from minimalci.tasks import Task
from minimalci.executors import Local, LocalContainer

from checks import GitContext, start_check_run, create_token

SOURCE: Path
IMAGE: str
CTX: GitContext


class Setup(Task):
    def run(self) -> None:
        with Local() as exe:
            global SOURCE
            global IMAGE
            global CTX
            SOURCE = exe.stash("*")
            IMAGE = f"test:{self.state.commit}"
            exe.sh(f"docker build . -t {IMAGE}")
            exe.unstash(self.state.secrets, "private_key.pem")
            private_key = Path("private_key.pem").read_text()
            _, _, repo = os.environ["REPO_URL"].partition(":")
            CTX = GitContext(repo, self.state.commit, create_token(private_key))
            start_check_run(CTX, "pylint")
            start_check_run(CTX, "mypy")
            start_check_run(CTX, "ci")
            print(CTX.repo)


class Pylint(Task):
    run_after = [Setup]

    def run(self) -> None:
        with LocalContainer(IMAGE) as exe:
            exe.unstash(SOURCE)
            output = exe.sh("make lint").decode().split("\n")


class Mypy(Task):
    run_after = [Setup]

    def run(self) -> None:
        with LocalContainer(IMAGE) as exe:
            exe.unstash(SOURCE)
            output = exe.sh("make typecheck").decode().split("\n")
