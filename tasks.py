from pathlib import Path
from minimalci.tasks import Task
from minimalci.executors import Local, LocalContainer

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
