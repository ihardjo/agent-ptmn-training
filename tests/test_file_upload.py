"""Attaching a file in the chat, and the overlay that makes the paperclip exist.

**The failure this whole feature exists to fix is a silent one.** The stock
`e2e-chatbot-app-next` template renders a file picker, an upload queue and
attachment previews with no button to trigger them and no server route behind
them, so the upload path is present and unreachable. Every test here is written
against the possibility of restoring that state by accident — a patch that
no-ops, a route that accepts a file and drops it, an error the user never sees.

The fixture the overlay tests run against is an *excerpt* of the real template,
committed under `tests/fixtures/template_excerpt/`. It exercises the patch
machinery; it cannot detect upstream drift. Only a clone at startup can, which
is what `scripts/start_app.py` does and why it exits rather than warning.
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_server.routes import router
from agent_server.uploads import (
    MAX_FILE_BYTES,
    UploadRejected,
    agent_path,
    check_name,
    check_size,
    safe_session,
    store,
    upload_path,
)
from scripts.overlay import PATCHES, OverlayError, apply

TEMPLATE_EXCERPT = Path(__file__).resolve().parent / "fixtures" / "template_excerpt"


class FakeUploads:
    """Stands in for the `raw/` tier. Records what it was asked to write, and where."""

    def __init__(self, fail: bool = False) -> None:
        self.written: dict[str, bytes] = {}
        self.fail = fail

    def upload_bytes(self, file_path: str, data: bytes) -> str:
        if self.fail:
            raise RuntimeError("volume unavailable")
        self.written[file_path] = data
        return file_path


def _app(backend, monkeypatch) -> FastAPI:
    monkeypatch.setattr("agent_server.backends.uploads_backend", lambda *a, **k: backend)
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def api(monkeypatch):
    """A test client over the real router, writing to a fake tier.

    Named `api` rather than `client` because `conftest.py` already owns that
    name for the fake Files API.
    """
    backend = FakeUploads()
    with TestClient(_app(backend, monkeypatch)) as test_client:
        test_client.backend = backend
        yield test_client


def upload(api, name: str, data: bytes = b"SELECT 1", session: str = "chat-1"):
    return api.post(
        "/files/upload",
        files={"file": (name, io.BytesIO(data), "text/plain")},
        data={"session": session},
    )


# ---------------------------------------------------------------------------
# the file reaches the tier the agent reads
# ---------------------------------------------------------------------------


def test_an_accepted_file_is_written_where_the_agent_reads(api):
    """Attachments go to the Volume rather than travelling in the chat payload,
    so a file attached in the chat and one dropped on the Volume by hand are the
    same file by the time `read_file` looks at it."""
    response = upload(api, "incidents.csv", b"id,priority\n1,P2\n")
    assert response.status_code == 200
    assert api.backend.written["/uploads/chat-1/incidents.csv"] == b"id,priority\n1,P2\n"


def test_the_response_is_the_shape_the_template_client_expects(api):
    """The client destructures `{url, pathname, contentType}` and shows `pathname`
    on the chip. A correct file written under a response shape the client cannot
    read is still a broken paperclip."""
    body = upload(api, "notes.md", b"# hi").json()
    assert set(body) >= {"url", "pathname", "contentType"}
    assert body["pathname"] == "notes.md"
    assert body["bytes"] == 4


def test_the_reported_url_is_the_path_the_agent_can_actually_open(api):
    """`url` is informational — nothing fetches it — but it is the only place the
    agent-visible path appears, so it has to be the one `read_file` takes."""
    assert upload(api, "notes.md").json()["url"] == "/wiki/raw/uploads/chat-1/notes.md"


def test_files_are_filed_against_the_conversation(api):
    """Per-session, so the agent can list one conversation's attachments without
    reading every other conversation's."""
    upload(api, "a.sql", session="abc-123")
    assert "/uploads/abc-123/a.sql" in api.backend.written


def test_an_unusable_session_id_still_stores_the_file(api):
    """A session id the server does not recognise is a reason to file the upload
    somewhere predictable, never a reason to refuse a file the user already
    chose."""
    upload(api, "a.sql", session="../../etc")
    assert "/uploads/unattributed/a.sql" in api.backend.written


def test_an_attachment_is_not_stamped_with_okf_frontmatter(api):
    """`store` goes through `upload_bytes`, which bypasses `write` and therefore
    `_as_okf`. A markdown file a person attached is a source document, and
    stamping a `type:` onto it would turn it into a malformed concept."""
    upload(api, "handover.md", b"# Handover\n\nno frontmatter\n")
    assert api.backend.written["/uploads/chat-1/handover.md"] == b"# Handover\n\nno frontmatter\n"


# ---------------------------------------------------------------------------
# what is refused, and whether the user is told why
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("notes.exe", "not a file type"),
        ("bundle.zip", "archive"),
        ("../../etc/passwd", "not a plain filename"),
        ("sub/dir.sql", "not a plain filename"),
        (".env", "not a plain filename"),
        ("weird\nname.sql", "characters I will not write"),
    ],
)
def test_a_refused_upload_says_why_in_words_the_user_reads(api, name: str, expected: str):
    """The template's client reads `error` off the response and puts it straight
    in a toast, so the sentence IS the user interface."""
    response = upload(api, name)
    assert response.status_code == 400
    assert expected in response.json()["detail"]["error"]
    assert api.backend.written == {}, "a refused file was written anyway"


def test_an_oversized_file_is_refused_and_pointed_at_the_volume(api):
    """The limit is policy, not platform, so the refusal has to offer the route
    that does work rather than reading as a dead end."""
    response = upload(api, "big.csv", b"x" * (MAX_FILE_BYTES + 1))
    assert response.status_code == 400
    error = response.json()["detail"]["error"]
    assert "Unity Catalog volume" in error
    assert "not a platform limit" in error


def test_an_empty_file_is_refused(api):
    assert upload(api, "empty.sql", b"").status_code == 400


def test_a_failed_write_is_not_reported_as_success(monkeypatch):
    """The worst outcome available: a 200 for a file that is not there. The agent
    would then confirm receipt of something it cannot read."""
    backend = FakeUploads(fail=True)
    with TestClient(_app(backend, monkeypatch), raise_server_exceptions=False) as api:
        response = upload(api, "a.sql")
    assert response.status_code == 500
    assert "Could not write" in response.json()["detail"]["error"]


def test_uploads_without_a_volume_are_refused_clearly(monkeypatch):
    """The `/wiki/` tier is optional — the course is taught on laptops that may
    not hold the credential — so this is a supported state and has to name the
    variable that fixes it rather than reading as a crash."""
    with TestClient(_app(None, monkeypatch)) as api:
        response = upload(api, "a.sql")
    assert response.status_code == 503
    assert "DATABRICKS_WIKI_VOLUME" in response.json()["detail"]["error"]


# ---------------------------------------------------------------------------
# validation, directly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["targets.md", "incidents.csv", "query.sql", "runbook.docx", "config.yaml", "a b-c.json"],
)
def test_every_type_the_agent_can_read_is_accepted(name: str):
    """The allowlist has to cover what the agent can actually turn into text —
    including `.docx`, which `agent_server/documents.py` extracts — or the agent
    asks for a file and then refuses it."""
    assert check_name(name) == name


def test_the_allowlist_is_an_allowlist():
    """A denylist is a list of the attacks somebody already thought of."""
    for name in ("x.so", "x.dll", "x.bin", "x.pdf", "x.xlsx"):
        with pytest.raises(UploadRejected):
            check_name(name)


def test_a_batch_total_is_bounded_as_well_as_each_file():
    check_size("a.sql", 1, running_total=0)
    with pytest.raises(UploadRejected, match="batch"):
        check_size("a.sql", 5 * 1024 * 1024, running_total=24 * 1024 * 1024)


def test_the_upload_path_is_under_uploads_and_never_escapes():
    assert upload_path("s", "a.sql") == "/uploads/s/a.sql"
    assert agent_path("s", "a.sql") == "/wiki/raw/uploads/s/a.sql"
    assert safe_session("a/../b") == "unattributed"


def test_store_uses_the_backend_it_is_given():
    backend = FakeUploads()
    result = store(backend, "s", "a.sql", b"data")
    assert result.bytes_written == 4
    assert backend.written["/uploads/s/a.sql"] == b"data"


def test_the_upload_tier_cannot_be_written_outside_its_subdirectory(client, volume_root):
    """`upload_bytes` is the one write path that skips `BackendProtocol`, so the
    confinement `_resolve` provides has to be asserted on it separately."""
    from agent_server.backends import VolumeBackend, VolumeEscapeError

    backend = VolumeBackend(client, volume_root, "raw")
    with pytest.raises(VolumeEscapeError):
        backend.upload_bytes("/../../notes/planted.md", b"x")


def test_upload_bytes_writes_the_bytes_it_was_given(client, volume_root):
    """Bytes, not text: a `.docx` is a ZIP and decoding it to write it would
    corrupt it."""
    from agent_server.backends import VolumeBackend

    backend = VolumeBackend(client, volume_root, "raw")
    backend.upload_bytes("/uploads/s/a.docx", b"PK\x03\x04binary")
    assert client.files.contents[f"{volume_root}/raw/uploads/s/a.docx"] == b"PK\x03\x04binary"


def test_the_agent_still_cannot_write_to_the_landing_tree():
    """Uploads land in `raw/`, and the deny rule that keeps the *agent* out of it
    is load-bearing — a UC volume grant is per-volume, not per-path. The upload
    route is server-side and holds its own backend, which is exactly why adding
    it does not need this rule relaxed."""
    from agent_server.backends import WIKI_SOURCE_MOUNT, filesystem_permissions

    denied = [
        p
        for p in filesystem_permissions()
        if p.mode == "deny" and f"{WIKI_SOURCE_MOUNT}**" in p.paths and "write" in p.operations
    ]
    assert denied, "the /wiki/raw/ write deny was dropped when uploads were added"


# ---------------------------------------------------------------------------
# the template overlay
# ---------------------------------------------------------------------------


@pytest.fixture
def template(tmp_path: Path) -> Path:
    target = tmp_path / "e2e-chatbot-app-next"
    shutil.copytree(TEMPLATE_EXCERPT, target)
    return target


def test_the_overlay_applies_and_is_idempotent(template: Path):
    assert apply(template) == len(PATCHES)
    assert apply(template) == 0, "re-applying patched a second time"


def test_the_overlay_registers_the_route_the_paperclip_already_calls(template: Path):
    apply(template)
    index = (template / "server/src/index.ts").read_text()
    assert "import { filesRouter } from './routes/files';" in index
    assert "app.use('/api/files', filesRouter);" in index
    assert (template / "server/src/routes/files.ts").is_file()


def test_the_overlay_sends_the_chat_id(template: Path):
    apply(template)
    body = (template / "client/src/components/multimodal-input.tsx").read_text()
    assert "formData.append('session', chatId);" in body
    assert "[chatId]," in body, "chatId is read in the callback but not in its dependency list"


def test_a_drifted_anchor_fails_loudly_and_names_the_file(template: Path):
    """The whole point. A patch that silently no-ops leaves the paperclip visibly
    present and quietly broken — indistinguishable, from the UI, from one that
    worked."""
    index = template / "server/src/index.ts"
    index.write_text(index.read_text().replace("app.use('/api/feedback', feedbackRouter);", ""))
    with pytest.raises(OverlayError) as raised:
        apply(template)
    message = str(raised.value)
    assert "server/src/index.ts" in message
    assert "found 0" in message
    assert "silently no-ops" in message


def test_a_missing_template_file_fails_loudly(template: Path):
    (template / "client/src/components/multimodal-input.tsx").unlink()
    with pytest.raises(OverlayError, match="multimodal-input.tsx"):
        apply(template)


def test_every_patch_explains_why_it_exists():
    """The `why` is read by whoever has to re-pin this against a moved template,
    at the moment they are deciding whether the patch is still needed."""
    for patch in PATCHES:
        assert len(patch.why.split()) >= 6, f"{patch.path}: `why` says nothing useful"


def test_the_overlay_renders_an_attach_button(template: Path):
    """The half that is easiest to miss. The template has every other piece of
    the upload path and renders `<PromptInputTools />` empty, so nothing on
    screen clicks the input. A working route behind an invisible button is, from
    the user's side, indistinguishable from no upload feature at all."""
    apply(template)
    body = (template / "client/src/components/multimodal-input.tsx").read_text()
    assert 'data-testid="attachments-button"' in body
    assert "fileInputRef.current?.click()" in body, "the button does not open the file picker"
    assert "PaperclipIcon," in body, "the icon is used but not imported"
    assert '<PromptInputTools className="gap-0 sm:gap-0.5" />' not in body, (
        "the empty self-closing toolbar is still there, so the button was added somewhere else"
    )


def test_the_overlay_does_not_send_file_parts(template: Path):
    """The template's own message schema admits **only** `image/jpeg` and
    `image/png`, with an absolute URL. A `.csv` attachment therefore fails
    validation and the entire send is rejected with `bad_request:api` — so the
    user sees a chip appear and then the send fail, which reads as the upload
    having worked and the agent having broken.

    The bytes are on the Volume, which is where the agent reads them, so naming
    the files in the text loses nothing and avoids widening this overlay into
    the shared `packages/core` schema."""
    apply(template)
    body = (template / "client/src/components/multimodal-input.tsx").read_text()
    assert "type: 'file' as const" not in body, (
        "file parts are still sent, and any non-image attachment will fail the schema"
    )
    assert "attached to this conversation" in body


def test_the_overlay_allows_sending_with_only_attachments(template: Path):
    """Attaching files and pressing send without typing anything is a reasonable
    thing to do, and the stock disabled condition made it impossible."""
    apply(template)
    body = (template / "client/src/components/multimodal-input.tsx").read_text()
    assert "!input.trim() && attachments.length === 0" in body


def test_tool_steps_start_collapsed(template: Path):
    """A single turn here runs a dozen tool calls — `ls`, `read_file` per skill,
    `execute_sql_read_only` — and the stock template opens every one expanded,
    which pushes the actual answer off the screen. The steps stay in the
    transcript and stay clickable; they just do not shout."""
    apply(template)
    body = (template / "client/src/components/message.tsx").read_text()
    assert "defaultOpen={true}" not in body
    assert body.count("defaultOpen={false}") == 2, (
        "both the tool and the MCP-tool step must start collapsed, or half still expand"
    )


def test_consecutive_tool_steps_collapse_into_one_line(template: Path):
    """The template already groups consecutive calls — it just borders them and
    still renders N cards. The group becomes one line: "Working…" while it runs,
    "N steps" when it is done."""
    apply(template)
    body = (template / "client/src/components/message.tsx").read_text()
    assert 'data-testid="tool-group-summary"' in body
    assert "Working…" in body
    assert "${tools.length} steps" in body


def test_a_tool_awaiting_approval_is_never_hidden(template: Path):
    """The user cannot answer a question they cannot see. A gated tool inside a
    collapsed group would stall the run with nothing on screen explaining why."""
    apply(template)
    body = (template / "client/src/components/message.tsx").read_text()
    assert "awaitingApproval" in body
    assert "open={groupOpen || awaitingApproval}" in body


def test_a_single_tool_call_is_left_as_the_template_drew_it(template: Path):
    """One tool is not a wall, and wrapping it in a disclosure adds a click for
    nothing."""
    apply(template)
    body = (template / "client/src/components/message.tsx").read_text()
    assert "if (!isMultiple) {" in body


def test_only_the_group_holding_the_pending_approval_is_force_opened(template: Path):
    """`pendingApprovalId` is a prop of the whole message, so testing it alone
    force-opened every group on the page — and because `open` was then pinned
    true, clicking the header set `groupOpen` false and nothing moved. Reported
    as: expands fine, will not collapse again."""
    apply(template)
    body = (template / "client/src/components/message.tsx").read_text()
    assert "pendingApprovalId != null &&" in body
    assert "approvalRequestId ===" in body, (
        "the force-open is not scoped to this group's tools, so any pending approval anywhere "
        "pins every group open"
    )
