from pathlib import Path
from minimalci.tasks import Task
from minimalci.executors import Local, LocalContainer

import checks

SOURCE: Path
IMAGE: str


class Setup(Task):
    def run(self) -> None:
        with Local() as exe:
            global SOURCE
            global IMAGE
            SOURCE = exe.stash("*")
            IMAGE = f"test:{self.state.commit}"
            exe.sh(f"docker build . -t {IMAGE}")


class Pylint(Task):
    run_after = [Setup]

    def run(self) -> None:
        with LocalContainer(IMAGE) as exe:
            exe.unstash(self.state.secrets, "private_key.pem")
            exe.unstash(SOURCE)
            exe.sh("make lint")


class Mypy(Task):
    run_after = [Setup]

    def run(self) -> None:
        with LocalContainer(IMAGE) as exe:
            exe.unstash(SOURCE)
            exe.sh("make typecheck")
