# Chat template overlay

The chat UI is Databricks' stock `e2e-chatbot-app-next`, sparse-cloned at startup by
`scripts/start_app.py` and gitignored. This directory holds the only changes this repo makes to
it, applied after the clone by `scripts/overlay.py`.

**This is a fork in all but name, and it is entered deliberately.** The template ships the upload
*machinery* — a hidden file input, an upload handler, an upload queue, attachment previews — and
**neither the button that triggers it nor the route behind it**.

Precisely, at the pinned commit:

- `client/src/components/multimodal-input.tsx` has the hidden `<input type="file">`,
  `fileInputRef`, `handleFileChange`, `uploadQueue` and `<PreviewAttachment>` — and renders
  `<PromptInputTools />` **empty**, so nothing clicks the input. There is no paperclip on screen.
- `POST /api/files/upload` is implemented in no server route, so even a click would fail.

Two independent gaps, and fixing one without the other changes nothing visible.

## What is changed, and why so little

| File | Change |
|---|---|
| `server/src/routes/files.ts` | **new.** Forwards the multipart body to this repo's FastAPI backend |
| `server/src/index.ts` | registers that router on `/api/files` |
| `client/src/components/multimodal-input.tsx` | renders the attach button in the empty toolbar, imports its icon, sends the chat id with the upload, names attachments in the text rather than as `file` parts, and allows sending with attachments and no typed text |
| `client/src/components/message.tsx` | consecutive tool calls collapse to one line; individual tool steps start collapsed |

### Where the bytes go

**Uploads do not travel in the chat payload.** `files.ts` forwards the multipart body to the
FastAPI backend's `POST /files/upload`, which validates it (`agent_server/uploads.py`) and writes
it to the wiki Volume under `raw/uploads/<session>/`. The agent then reads it at
`/wiki/raw/uploads/<session>/` — the same tier, and the same `read_file`, it uses for everything
else a person put on the Volume.

That is why `attachments: []` in the template's `server/src/routes/chat.ts` is left exactly as it
is, and why the client names attachments in the message text instead. The template's message
schema admits only `image/jpeg` and `image/png` with an absolute URL, so a `.py` sent as a `file`
part fails validation and the whole send is rejected with `bad_request:api`. Making attachments
flow through `POST /invocations` and back out again would be a much larger change to buy nothing.

Note that the agent still **cannot write** to `/wiki/raw/` — the deny rule in
`filesystem_permissions()` is unchanged. The upload route is server-side code with its own
`VolumeBackend`, so it is not subject to the agent's filesystem permissions, and the tier stays
one the agent only reads.

### Why the tool steps collapse

A turn here runs a dozen tool calls — `ls`, `read_file` per skill, `execute_sql_read_only`,
`write_file` — and the stock template draws each as its own expanded card, so the answer arrives
under a wall of working. The template already groups *consecutive* tool calls
(`groupConsecutiveToolSegments` → `MessageToolGroup`); it just borders them and still renders N
cards. The overlay turns that group into one line — "Working…" while it runs, "N steps" when it
is done — with the individual calls one click away.

Two rules the patch keeps: a single tool call is left as the template drew it (one tool is not a
wall), and a tool **awaiting approval** is never hidden behind the disclosure, scoped to the
group that actually holds it.

## Upstream drift

`TEMPLATE_COMMIT` in `scripts/overlay.py` pins the commit these patches were written against, and
every anchor is verified before it is applied. **A template that has moved fails the startup
loudly, naming the file and the anchor**, rather than leaving the button silently broken again —
which is the failure this overlay exists to fix, and the one it could most easily reintroduce.

To re-pin: clone the template at the new commit, re-check each anchor by hand, update
`TEMPLATE_COMMIT`, and run `uv run start-app` once.
