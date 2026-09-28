"""Accepting a file from the chat, and refusing the ones that should not arrive.

Uploads do not travel in the chat payload: they are written to `raw/uploads/
<session>/` on the wiki Volume and the agent reads them there, like everything
else a person put on the Volume. The upload route holds its own backend, so this
does not give the agent write access to `/wiki/raw/`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# An allowlist, not a denylist: what this agent can read is small and known,
# and a denylist is a list of the attacks somebody already thought of.
ALLOWED_SUFFIXES = frozenset(
    {
        ".md", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml", ".xml",
        ".sql", ".py", ".sh", ".bash", ".ipynb",
        ".conf", ".cfg", ".properties", ".log", ".docx",
    }
)

# Rejected by name, not by sniffing: the reason is "I cannot read it", not
# "this might be dangerous".
ARCHIVE_SUFFIXES = frozenset({".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".bz2", ".xz", ".jar"})

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_REQUEST_BYTES = 25 * 1024 * 1024

# A name that is not obviously a filename is refused rather than sanitised into
# something the user did not choose.
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ \-()]{0,199}$")

UPLOADS_SUBDIR = "uploads"


class UploadRejected(Exception):
    """A refusal the user should read. The message is shown to them verbatim."""


@dataclass(frozen=True)
class StoredUpload:
    filename: str
    bytes_written: int
    path: str


def _suffix(filename: str) -> str:
    _, dot, tail = filename.rpartition(".")
    return f".{tail.lower()}" if dot else ""


def check_name(filename: str) -> str:
    """The filename, validated. Raises `UploadRejected` with the reason to show the user."""
    name = (filename or "").strip()
    if not name:
        raise UploadRejected("The upload has no filename.")
    # Checked before the pattern, so a traversal attempt is named as one rather
    # than reported as an unusual character.
    if "/" in name or "\\" in name or name.startswith("."):
        raise UploadRejected(
            f"`{name}` is not a plain filename. Send the file itself rather than a path."
        )
    if not SAFE_NAME.match(name):
        raise UploadRejected(
            f"`{name}` contains characters I will not write to disk. Rename it to letters, "
            f"digits, dots, spaces, dashes and underscores."
        )
    suffix = _suffix(name)
    if suffix in ARCHIVE_SUFFIXES:
        raise UploadRejected(
            f"`{name}` is an archive. Upload its contents instead — I do not expand archives, "
            f"because what comes out of one is not what you chose to send."
        )
    if suffix not in ALLOWED_SUFFIXES:
        raise UploadRejected(
            f"`{suffix or name}` is not a file type I can read. I accept: "
            f"{', '.join(sorted(ALLOWED_SUFFIXES))}."
        )
    return name


def check_size(filename: str, size: int, running_total: int = 0) -> None:
    if size > MAX_FILE_BYTES:
        raise UploadRejected(
            f"`{filename}` is {size / 1024 / 1024:.1f} MB and the limit here is "
            f"{MAX_FILE_BYTES // 1024 // 1024} MB. That limit keeps one chat turn bounded; it is "
            f"not a platform limit. Put it on the Unity Catalog volume instead — that route has "
            f"no ceiling worth worrying about."
        )
    if size == 0:
        raise UploadRejected(f"`{filename}` is empty.")
    if running_total + size > MAX_REQUEST_BYTES:
        raise UploadRejected(
            f"This batch exceeds {MAX_REQUEST_BYTES // 1024 // 1024} MB in total. Send it in "
            f"smaller batches, or use the Unity Catalog volume."
        )


def safe_session(session: str | None) -> str:
    """The chat id as a directory name; anything unexpected becomes `unattributed`.

    Never raises — an unrecognised session id is a reason to file the upload
    somewhere predictable, not to refuse a file the user already chose.
    """
    candidate = (session or "").strip()
    return candidate if re.fullmatch(r"[A-Za-z0-9._\-]{1,128}", candidate) else "unattributed"


def upload_path(session: str, filename: str) -> str:
    """Where the file goes, relative to the `raw/` backend that stores it.

    The agent sees the same file one prefix up, at `/wiki/raw/uploads/...`.
    """
    return f"/{UPLOADS_SUBDIR}/{safe_session(session)}/{filename}"


def agent_path(session: str, filename: str) -> str:
    """The same file as the agent names it, which is what the reply quotes."""
    from agent_server.backends import WIKI_SOURCE_MOUNT

    return f"{WIKI_SOURCE_MOUNT.rstrip('/')}{upload_path(session, filename)}"


def store(backend, session: str, filename: str, data: bytes) -> StoredUpload:
    """Write one validated file to the backend it is given.

    Bytes rather than text: a `.docx` is a ZIP and decoding it would corrupt it.
    """
    path = upload_path(session, filename)
    backend.upload_bytes(path, data)
    return StoredUpload(filename=filename, bytes_written=len(data), path=path)
