"""A stand-in for the Databricks Files API, backed by a dict.

The backend's contract with `BackendProtocol` — window clamping, error results
instead of raises, path confinement — is worth testing on every run, and none
of it needs a workspace. Tests that genuinely need the Volume are marked
`live` and skipped unless the Jakarta credentials are present.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Iterator

import pytest


class FileNotFound(Exception):
    """What the SDK raises for a missing path, near enough for a test."""

    def __init__(self, path: str) -> None:
        super().__init__(f"The file being accessed does not exist: {path}")


class Unreachable(Exception):
    """A transport fault, as distinct from a missing file."""


@dataclass
class _Entry:
    path: str
    is_directory: bool
    file_size: int | None = None
    last_modified: int | None = None


class FakeFiles:
    def __init__(self, contents: dict[str, bytes], *, broken: bool = False) -> None:
        self.contents = dict(contents)
        self.broken = broken
        self.uploads: list[str] = []
        self.deletes: list[str] = []

    def _check(self) -> None:
        if self.broken:
            raise Unreachable("connection to the workspace failed")

    def download(self, file_path: str):
        self._check()
        if file_path not in self.contents:
            raise FileNotFound(file_path)
        return type("Resp", (), {"contents": io.BytesIO(self.contents[file_path])})()

    def upload(self, file_path: str, contents, *, overwrite: bool = False) -> None:
        self._check()
        self.contents[file_path] = contents.read()
        self.uploads.append(file_path)

    def delete(self, file_path: str) -> None:
        self._check()
        if file_path not in self.contents:
            raise FileNotFound(file_path)
        del self.contents[file_path]
        self.deletes.append(file_path)

    def list_directory_contents(self, directory_path: str) -> Iterator[_Entry]:
        self._check()
        base = directory_path.rstrip("/") + "/"
        seen_dirs: set[str] = set()
        out: list[_Entry] = []
        for path, body in sorted(self.contents.items()):
            if not path.startswith(base):
                continue
            rest = path[len(base) :]
            if "/" in rest:
                # The real API sends a directory path with a trailing slash and
                # no size or timestamp. Mirrored here so the fake cannot drift
                # into being easier to satisfy than the thing it stands in for.
                d = base + rest.split("/", 1)[0] + "/"
                if d not in seen_dirs:
                    seen_dirs.add(d)
                    out.append(_Entry(path=d, is_directory=True))
                continue
            # `last_modified` is epoch milliseconds from the real API, not ISO.
            out.append(
                _Entry(
                    path=path,
                    is_directory=False,
                    file_size=len(body),
                    last_modified=1789719090000,
                )
            )
        return iter(out)


class FakeClient:
    def __init__(self, contents: dict[str, bytes], *, broken: bool = False) -> None:
        self.files = FakeFiles(contents, broken=broken)


VOLUME = "/Volumes/cat/sch/vol"


@pytest.fixture
def seeded() -> dict[str, bytes]:
    return {
        f"{VOLUME}/raw/index.md": b"# Policy\n\n* [Targets](/policies/targets.md)\n",
        f"{VOLUME}/raw/policies/targets.md": (
            b"---\ntype: Service Level Policy\n---\n\n"
            b"# Targets\n\n| Priority | Target |\n|---|---|\n| P2 | 80 |\n"
        ),
        f"{VOLUME}/notes/existing.md": b"---\ntype: Observation\n---\n\nprior note\n",
    }


@pytest.fixture
def client(seeded):
    return FakeClient(seeded)


@pytest.fixture
def volume_root() -> str:
    return VOLUME


@pytest.fixture
def broken_client():
    """A client whose every Files API call fails as a transport fault."""
    return FakeClient({}, broken=True)


@pytest.fixture
def source(client, volume_root):
    """The read-only source tier."""
    from agent_server.backends import VolumeBackend

    return VolumeBackend(client, volume_root, "raw")


@pytest.fixture
def notes(client, volume_root):
    """The agent-writable notes tier: conformant writes on.

    Configured the way `agent_server.agent.wiki_routes` configures it, so a test
    cannot pass against a tier the agent never actually gets.
    """
    from agent_server.backends import VolumeBackend

    return VolumeBackend(
        client,
        volume_root,
        "notes",
        okf_actor="agent-ptmn-training/test-model",
    )
