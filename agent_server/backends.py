"""The agent's filesystem: a backend over a Unity Catalog Volume, and the
tiers assembled from it.

Databricks Apps give no FUSE mount for Volumes, so `FilesystemBackend` cannot be
pointed at one and this reaches the Files API instead. Only the synchronous half
of `BackendProtocol` is implemented; the async methods default to
`asyncio.to_thread`.
"""

from __future__ import annotations

import io
import logging
import posixpath
from datetime import datetime, timezone
from typing import Any, Optional

from databricks.sdk import WorkspaceClient
from deepagents.backends import CompositeBackend, StateBackend
from deepagents.backends.protocol import (
    BackendProtocol,
    DeleteResult,
    EditResult,
    FileInfo,
    GlobResult,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)
from deepagents.backends.utils import (
    InvalidGlobPatternError,
    _get_backend_read_file_type,
    _glob_search_files,
    create_file_data,
    file_data_to_string,
    grep_matches_from_files,
    perform_string_replacement,
    slice_read_response,
    update_file_data,
)
from deepagents.middleware.filesystem import FilesystemPermission

from agent_server.documents import UnreadableDocumentError, decode
from agent_server.env import env
from agent_server.env import schema as workshop_schema
from agent_server.env import volume as workshop_volume
from agent_server.okf import ensure_conformant, is_reserved
from agent_server.skills import SKILLS_MOUNT
from agent_server.clients import jakarta_workspace_client

logger = logging.getLogger(__name__)

# Reading a tier means downloading it. Bounded so a mistake on the Volume
# cannot turn one grep into an unbounded transfer.
MAX_SCAN_FILES = 500


def _iso8601(last_modified: Any) -> Optional[str]:
    """The Files API's modification time as the protocol's ISO 8601 string.

    The API sends epoch milliseconds. Passed through unconverted, the field
    looked populated and sorted wrongly wherever it was compared as text.
    """
    if last_modified is None:
        return None
    if isinstance(last_modified, (int, float)):
        return (
            datetime.fromtimestamp(last_modified / 1000, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    return str(last_modified)


class VolumeEscapeError(ValueError):
    """A path resolved outside the backend's subdirectory."""


class VolumeBackend(BackendProtocol):
    """Files under one subdirectory of one Unity Catalog Volume.

    Confinement to `<volume_root>/<subdir>` is how one Volume carries both
    human-authored source and agent-written notes while a path prefix still
    states which is which. `okf_actor` stamps OKF frontmatter onto markdown.
    """

    def __init__(
        self,
        client: WorkspaceClient,
        volume_root: str,
        subdir: str,
        *,
        okf_actor: Optional[str] = None,
    ) -> None:
        self._client = client
        self._base = f"{volume_root.rstrip('/')}/{subdir.strip('/')}"
        self._subdir = subdir.strip("/")
        self._okf_actor = okf_actor

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (
            f"VolumeBackend({self._base!r}, "
            f"okf_actor={self._okf_actor!r})"
        )

    # ── path handling ────────────────────────────────────────────────────────

    def _resolve(self, path: str) -> str:
        """Map an agent-visible path to a Volume path, refusing escapes.

        `normpath` collapses `..` before the prefix check, so a path is judged
        on what it resolves to rather than on how it was spelled.
        """
        candidate = posixpath.normpath(posixpath.join(self._base, path.lstrip("/")))
        if candidate != self._base and not candidate.startswith(f"{self._base}/"):
            raise VolumeEscapeError(
                f"Path '{path}' resolves outside '{self._subdir}/' and was refused"
            )
        return candidate

    def _to_agent_path(self, volume_path: str) -> str:
        """The inverse of `_resolve`: a Volume path as the agent addresses it."""
        return "/" + volume_path[len(self._base) :].lstrip("/")

    # ── reads ────────────────────────────────────────────────────────────────

    def ls(self, path: str) -> LsResult:
        try:
            target = self._resolve(path)
        except VolumeEscapeError as exc:
            return LsResult(error=str(exc))
        try:
            entries: list[FileInfo] = []
            for e in self._client.files.list_directory_contents(target):
                is_dir = bool(e.is_directory)
                path = self._to_agent_path(e.path or "")
                # One trailing slash marks a directory, per the protocol. The
                # API sends it that way; normalising keeps that true regardless.
                path = path.rstrip("/") + "/" if is_dir else path
                info: FileInfo = {"path": path, "is_dir": is_dir}
                if e.file_size is not None:
                    info["size"] = int(e.file_size)
                stamp = _iso8601(e.last_modified)
                if stamp:
                    info["modified_at"] = stamp
                entries.append(info)
            return LsResult(entries=sorted(entries, key=lambda i: i["path"]))
        except Exception as exc:
            return LsResult(error=self._describe(exc, target, "list"))

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        try:
            target = self._resolve(file_path)
        except VolumeEscapeError as exc:
            return ReadResult(error=str(exc))
        try:
            raw = self._client.files.download(target).contents.read()
        except Exception as exc:
            return ReadResult(error=self._describe(exc, target, "read"))
        try:
            file_data = create_file_data(decode(raw, file_path))
        except UnreadableDocumentError as exc:
            return ReadResult(error=str(exc))
        if _get_backend_read_file_type(file_path) != "text":
            return ReadResult(file_data=file_data)
        # Clamps the window and sets every pagination field, including the
        # `start_line` the middleware needs to number the gutter.
        return slice_read_response(file_data, offset, limit)

    # ── writes ───────────────────────────────────────────────────────────────

    def write(self, file_path: str, content: str) -> WriteResult:
        try:
            target = self._resolve(file_path)
        except VolumeEscapeError as exc:
            return WriteResult(error=str(exc))
        content = self._as_okf(content, file_path)
        try:
            self._upload(target, content)
        except Exception as exc:
            return WriteResult(error=self._describe(exc, target, "write"))
        return WriteResult(path=file_path)

    def upload_bytes(self, file_path: str, data: bytes) -> str:
        """Write raw bytes, bypassing the text and OKF paths. Returns the Volume path.

        Ingest from the chat upload route, not reachable by the agent. It cannot
        go through `write`, which would UTF-8 decode a `.docx` ZIP and stamp OKF
        frontmatter onto an attachment. Escapes raise rather than returning an
        error result, because the caller owes the user a status code.
        """
        target = self._resolve(file_path)
        self._client.files.upload(target, io.BytesIO(data), overwrite=True)
        return target

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        try:
            target = self._resolve(file_path)
        except VolumeEscapeError as exc:
            return EditResult(error=str(exc))
        try:
            raw = self._client.files.download(target).contents.read()
        except Exception as exc:
            return EditResult(error=self._describe(exc, target, "read"))
        try:
            existing = create_file_data(raw.decode("utf-8"))
        except UnicodeDecodeError:
            return EditResult(error=f"Error: File '{file_path}' is not UTF-8 text")

        result = perform_string_replacement(
            file_data_to_string(existing), old_string, new_string, replace_all
        )
        if isinstance(result, str):
            # The helper signals a failed match by returning the message itself.
            return EditResult(error=result)
        new_content, occurrences = result
        new_content = self._as_okf(new_content, file_path)
        try:
            self._upload(target, file_data_to_string(update_file_data(existing, new_content)))
        except Exception as exc:
            return EditResult(error=self._describe(exc, target, "write"))
        return EditResult(path=file_path, occurrences=occurrences)

    def delete(self, file_path: str) -> DeleteResult:
        try:
            target = self._resolve(file_path)
        except VolumeEscapeError as exc:
            return DeleteResult(error=str(exc))
        try:
            self._client.files.delete(target)
        except Exception as exc:
            return DeleteResult(error=self._describe(exc, target, "delete"))
        return DeleteResult(path=file_path)

    # ── search ───────────────────────────────────────────────────────────────

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        files, error, truncated = self._scan()
        if error:
            return GrepResult(error=error)
        result = grep_matches_from_files(files, pattern, path, glob, max_count=max_count)
        if truncated and not result.error:
            result.truncated = True
        return result

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        files, error, truncated = self._scan()
        if error:
            return GlobResult(error=error)
        try:
            found = _glob_search_files(files, pattern, path)
        except InvalidGlobPatternError as exc:
            # A refused pattern is a result the model can rewrite, not a raise.
            return GlobResult(error=str(exc))
        if found == "No files found":
            return GlobResult(matches=[], truncated=truncated)
        matches: list[FileInfo] = []
        for p in found.split("\n"):
            fd = files.get(p)
            matches.append(
                {
                    "path": p,
                    "is_dir": False,
                    "size": len(file_data_to_string(fd)) if fd else 0,
                    "modified_at": (fd or {}).get("modified_at", ""),
                }
            )
        return GlobResult(matches=matches, truncated=truncated)

    # ── internals ────────────────────────────────────────────────────────────

    def _upload(self, target: str, content: str) -> None:
        self._client.files.upload(target, io.BytesIO(content.encode("utf-8")), overwrite=True)

    def _as_okf(self, content: str, file_path: str) -> str:
        """Supply the frontmatter a conformant concept needs, or pass through.

        `index.md` and `log.md` are passed through untouched: §8 and §9 say a
        listing and a history carry none, so adding it would be the violation.
        """
        if not self._okf_actor or not file_path.endswith(".md"):
            return content
        if is_reserved(file_path):
            return content
        return ensure_conformant(content, actor=self._okf_actor)

    def _scan(self) -> tuple[dict[str, Any], Optional[str], bool]:
        """Every text file under this tier, as the `path -> FileData` mapping
        the shared grep and glob helpers expect.

        No ripgrep to delegate to, so search is a recursive list plus a download
        of each file.
        """
        files: dict[str, Any] = {}
        try:
            pending = [self._base]
            while pending:
                current = pending.pop()
                for e in self._client.files.list_directory_contents(current):
                    if not e.path:
                        continue
                    if e.is_directory:
                        pending.append(e.path)
                        continue
                    if len(files) >= MAX_SCAN_FILES:
                        logger.warning(
                            "Stopped scanning %s at %d files.", self._base, MAX_SCAN_FILES
                        )
                        # Truncated, not complete: a partial scan passed off as
                        # whole turns "I stopped looking" into "nothing is there".
                        return files, None, True
                    agent_path = self._to_agent_path(e.path)
                    try:
                        raw = self._client.files.download(e.path).contents.read()
                        files[agent_path] = create_file_data(decode(raw, agent_path))
                    except UnreadableDocumentError:
                        continue  # not a document; not searchable
        except Exception as exc:
            return files, self._describe(exc, self._base, "search"), False
        return files, None, False

    def _describe(self, exc: Exception, target: str, operation: str) -> str:
        """A Files API failure as a message the agent can act on.

        Mapped rather than raised: an unreachable Volume or a missing file has
        to arrive as a tool result, not as a 500 that ends the request.
        """
        logger.info("Volume %s failed for %s: %s", operation, target, exc)
        if "does not exist" in str(exc) or "NOT_FOUND" in str(exc) or "404" in str(exc):
            return f"Error: '{self._to_agent_path(target)}' not found"
        return f"Error: could not {operation} '{self._to_agent_path(target)}': {exc}"


# The two halves of the wiki tier. Both are subdirectories of one Unity Catalog
# Volume; the prefix, not the storage, is what states provenance.
WIKI_SOURCE_MOUNT = "/wiki/raw/"
WIKI_MOUNT = "/wiki/"
WIKI_SOURCE_SUBDIR = "raw"
WIKI_SUBDIR = "wiki"


def wiki_routes(client: Optional[Any] = None, okf_actor: Optional[str] = None) -> dict[str, Any]:
    """The two wiki routes, or nothing when the Jakarta credential is absent.

    The path derives from `WORKSHOP_GROUP`, so a group branch sets one variable
    rather than two that can disagree. A UC grant is per-volume, so read-only on
    `/wiki/raw/` comes from `filesystem_permissions()` and not from the grant.

    The credential is the only gate, since the Volume lives in another workspace.
    """
    volume = workshop_volume(workshop_schema())
    if client is None:
        try:
            client = jakarta_workspace_client()
        except Exception:
            logger.warning(
                "Could not build a client for the wiki Volume. "
                "Continuing without the /wiki/ tier.",
                exc_info=True,
            )
            return {}
    if client is None:
        logger.info(
            "DATABRICKS_JAKARTA_* is not configured — "
              "continuing without the /wiki/ tier."
        )
        return {}
    return {
        WIKI_SOURCE_MOUNT: VolumeBackend(client, volume, WIKI_SOURCE_SUBDIR),
        WIKI_MOUNT: VolumeBackend(
            client,
            volume,
            WIKI_SUBDIR,
            okf_actor=okf_actor,
        ),
    }


def uploads_backend(client: Optional[Any] = None) -> Optional[VolumeBackend]:
    """The backend the chat upload route writes through, or None when unconfigured.

    The Volume's `raw/` subdirectory with no `okf_actor`, since stamping OKF
    frontmatter onto an attachment would make it a malformed concept. A separate
    instance from the agent's, which is behind the write deny.
    """
    volume = workshop_volume(workshop_schema())
    if client is None:
        try:
            client = jakarta_workspace_client()
        except Exception:
            logger.warning("Could not build a client for uploads.", exc_info=True)
            return None
    if client is None:
        return None
    return VolumeBackend(client, volume, WIKI_SOURCE_SUBDIR)


def build_backend(
    wiki_client: Optional[Any] = None, okf_actor: Optional[str] = None
) -> CompositeBackend:
    """The agent's filesystem, tiered so a path prefix states a file's lifetime,
    who wrote it, and whether the agent may write there.

        /                  turn-scoped scratch, discarded with the thread
        /skills/           read-only, seeded from the repository each turn
        /wiki/raw/         read-only landing tree, any format, written by people
        /wiki/             the wiki: an OKF bundle, durable, shared across users

    The default is state, not local disk, because a scratch file on a
    container's filesystem looks durable and is not. Routing is longest-prefix,
    so `/wiki/raw/…` reaches the landing tree rather than the bundle.
    """
    routes: dict[str, Any] = wiki_routes(wiki_client, okf_actor=okf_actor)
    logger.info("Filesystem tiers: / (scratch), %s", ", ".join(sorted(routes)) or "none")
    return CompositeBackend(default=StateBackend(), routes=routes)


def filesystem_permissions() -> list[FilesystemPermission]:
    """Deny writes under the skills mount and the wiki's landing tree.

    Telling the agent not to edit its own instructions is not a control; a rule
    that refuses the write is. For `/wiki/raw/` this rule is the *only* thing
    enforcing read-only, since the Volume grant covers both subdirectories — a
    gap here is a correctness bug.
    """
    return [
        FilesystemPermission(
            operations=["write"],
            paths=[f"{SKILLS_MOUNT}**", f"{WIKI_SOURCE_MOUNT}**"],
            mode="deny",
        )
    ]
