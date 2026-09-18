"""A deepagents filesystem backend over a Unity Catalog Volume.

Databricks Apps deploy the repository to local disk but give it **no FUSE
mount** for Unity Catalog Volumes, so `FilesystemBackend(root_dir=...)` cannot
be pointed at one. The Volume is reachable only through the Files API, which is
why this exists rather than reusing the filesystem backend.

Only the synchronous half of `BackendProtocol` is implemented. The protocol's
async methods default to `asyncio.to_thread(self.<sync>)`, so an async server
gets non-blocking behaviour for free and a second code path is not worth
maintaining.
"""

from __future__ import annotations

import io
import logging
import posixpath
from datetime import datetime, timezone
from typing import Any, Optional

from databricks.sdk import WorkspaceClient
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

from agent_server.okf import ensure_conformant, is_reserved
from agent_server.privacy import names_in

logger = logging.getLogger(__name__)

# Reading a tier means downloading it. Small by design — this tier holds policy
# documents, not data — but bounded anyway so a mistake on the Volume cannot
# turn one grep into an unbounded transfer.
MAX_SCAN_FILES = 500


def _iso8601(last_modified: Any) -> Optional[str]:
    """The Files API's modification time as the protocol's ISO 8601 string.

    The API sends epoch milliseconds, while `FileInfo.modified_at` is specified
    as ISO 8601. Passing the integer through unconverted produced a field that
    looked populated and sorted wrongly everywhere it was compared as text.
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

    Each instance is confined to `<volume_root>/<subdir>`. Two instances
    sharing a volume root but differing in subdirectory are two tiers as far
    as the agent is concerned, which is how a single Volume carries both
    human-authored source content and agent-written notes while a path prefix
    still states which is which.

    `forbid_person_names` turns on the write-time privacy guard. It belongs on
    the agent-writable tier: a durable file outlives the reply that prompted it
    and is readable by users who never asked the original question, so it is the
    wider disclosure rather than the narrower one.

    `okf_actor` turns on conformant-write enforcement. When set, a markdown
    document written here is given the frontmatter OKF requires before it lands,
    because the agent is a producer of this bundle and a note without a `type`
    breaks the bundle for every later reader.
    """

    def __init__(
        self,
        client: WorkspaceClient,
        volume_root: str,
        subdir: str,
        *,
        forbid_person_names: bool = False,
        okf_actor: Optional[str] = None,
    ) -> None:
        self._client = client
        self._base = f"{volume_root.rstrip('/')}/{subdir.strip('/')}"
        self._subdir = subdir.strip("/")
        self._forbid_person_names = forbid_person_names
        self._okf_actor = okf_actor

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (
            f"VolumeBackend({self._base!r}, "
            f"forbid_person_names={self._forbid_person_names}, "
            f"okf_actor={self._okf_actor!r})"
        )

    # ── path handling ────────────────────────────────────────────────────────

    def _resolve(self, path: str) -> str:
        """Map an agent-visible path to a Volume path, refusing escapes.

        `normpath` collapses `..` *before* the prefix check rather than after,
        so `/a/../../etc` is rejected on what it resolves to and not on how it
        was spelled.
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
                # A directory keeps exactly one trailing slash, which is the
                # protocol's own convention for marking one. The API already
                # sends it that way; normalising rather than trusting keeps the
                # contract true if that ever changes.
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
            file_data = create_file_data(raw.decode("utf-8"))
        except UnicodeDecodeError:
            return ReadResult(
                error=f"File '{file_path}' is not UTF-8 text and cannot be read as a document"
            )
        if _get_backend_read_file_type(file_path) != "text":
            return ReadResult(file_data=file_data)
        # `slice_read_response` clamps the window through `normalize_read_bounds`
        # and sets every pagination field, including `start_line` — which the
        # middleware needs to number the gutter correctly.
        return slice_read_response(file_data, offset, limit)

    # ── writes ───────────────────────────────────────────────────────────────

    def write(self, file_path: str, content: str) -> WriteResult:
        try:
            target = self._resolve(file_path)
        except VolumeEscapeError as exc:
            return WriteResult(error=str(exc))
        content = self._as_okf(content, file_path)
        refusal = self._name_guard(content, file_path)
        if refusal:
            return WriteResult(error=refusal)
        try:
            self._upload(target, content)
        except Exception as exc:
            return WriteResult(error=self._describe(exc, target, "write"))
        return WriteResult(path=file_path)

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

        refusal = self._name_guard(new_content, file_path)
        if refusal:
            return EditResult(error=refusal)
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

        Applied before the privacy guard rather than after, so the guard reads
        exactly the bytes that would land — frontmatter included, since an actor
        or a title could carry a name as easily as the body can.

        Reserved filenames are passed through untouched: `index.md` and `log.md`
        are a listing and a history, and §8/§9 say they carry no frontmatter, so
        adding some would be the conformance failure rather than the fix.
        """
        if not self._okf_actor or not file_path.endswith(".md"):
            return content
        if is_reserved(file_path):
            return content
        return ensure_conformant(content, actor=self._okf_actor)

    def _name_guard(self, content: str, file_path: str) -> Optional[str]:
        """Refuse a write that would persist a person's name.

        Returned as an error rather than raised so the agent can rewrite the
        note in aggregate form and continue, which is the behaviour the spec
        asks for: the constraint must not be satisfiable by declining to write.
        """
        if not self._forbid_person_names:
            return None
        found = names_in(content)
        if not found:
            return None
        logger.warning(
            "Refused a write to %s: content named %d person(s).", file_path, len(found)
        )
        return (
            f"Refused: this content names {len(found)} individual(s), and personal "
            "names must not be written to durable storage. Report the figure and "
            "identify people by rank (1 (tertinggi), 2, 3) instead of by name, "
            "then write it again."
        )

    def _scan(self) -> tuple[dict[str, Any], Optional[str], bool]:
        """Every text file under this tier, as the `path -> FileData` mapping
        the shared grep and glob helpers expect.

        There is no ripgrep to delegate to and no local file to hand it, so
        search is a recursive list plus a download of each file. Acceptable
        while the tier holds policy documents; the trigger to revisit is the
        tier growing past `MAX_SCAN_FILES`, at which point an index or a search
        service is the answer rather than a wider scan.
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
                        # Reported as truncated, not returned as complete. A
                        # partial scan passed off as whole turns "I stopped
                        # looking" into "there is nothing there", which is the
                        # worst answer a search can give.
                        return files, None, True
                    try:
                        raw = self._client.files.download(e.path).contents.read()
                        files[self._to_agent_path(e.path)] = create_file_data(
                            raw.decode("utf-8")
                        )
                    except UnicodeDecodeError:
                        continue  # not a document; not searchable
        except Exception as exc:
            return files, self._describe(exc, self._base, "search"), False
        return files, None, False

    def _describe(self, exc: Exception, target: str, operation: str) -> str:
        """A Files API failure as a message the agent can act on.

        Every failure is mapped rather than raised. An unreachable Volume or a
        missing file has to arrive as a tool result the agent can respond to,
        not as a 500 from the route — the spec requires the request to continue.
        """
        logger.info("Volume %s failed for %s: %s", operation, target, exc)
        if "does not exist" in str(exc) or "NOT_FOUND" in str(exc) or "404" in str(exc):
            return f"Error: '{self._to_agent_path(target)}' not found"
        return f"Error: could not {operation} '{self._to_agent_path(target)}': {exc}"
