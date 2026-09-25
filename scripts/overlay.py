"""Applying this repo's changes to the sparse-cloned chat template.

The template is not vendored — it is cloned at startup and gitignored, so the changes have to
live here and be re-applied every time. Four files' worth, described in
`frontend_overlay/README.md`.

**The design rule is that drift fails loudly.** Every anchor below is checked before anything is
written, and a template whose text has moved stops the startup naming the file and the anchor.
The alternative is a patch that silently no-ops, which puts the paperclip back exactly where it
was — visibly present and quietly broken. That is the failure this overlay exists to fix and the
one it could most easily reintroduce.

Applying twice is a no-op: each patch checks for its own result first.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OVERLAY_DIR = REPO_ROOT / "frontend_overlay"

# The upstream commit these patches were written and verified against, 2026-09-23; every anchor
# below was re-checked against this repo's own clone on 2026-09-25 and all twelve still match
# exactly once. Re-pinning is a human job: clone the template at the new commit, re-check every
# anchor by hand, update this, and run `uv run start-app` once. See frontend_overlay/README.md.
TEMPLATE_COMMIT = "74c0cd0f66ed4c6bde454bcd5f7ad277f078f2fd"

# Files copied in whole. A new file cannot conflict with upstream, so these need no anchor.
COPIED = ("server/src/routes/files.ts",)


@dataclass(frozen=True)
class Patch:
    """One anchored edit. `anchor` must appear exactly once, or the startup stops."""

    path: str
    anchor: str
    replacement: str
    why: str


PATCHES = (
    Patch(
        path="server/src/index.ts",
        anchor="import { feedbackRouter } from './routes/feedback';",
        replacement=(
            "import { feedbackRouter } from './routes/feedback';\n"
            "import { filesRouter } from './routes/files';"
        ),
        why="the upload router has to be imported before it can be registered",
    ),
    Patch(
        path="server/src/index.ts",
        anchor="app.use('/api/feedback', feedbackRouter);",
        replacement=(
            "app.use('/api/feedback', feedbackRouter);\n"
            "app.use('/api/files', filesRouter);"
        ),
        why="`/api/files/upload` is the path the template's own paperclip already calls",
    ),
    Patch(
        path="client/src/components/multimodal-input.tsx",
        anchor=(
            "  const uploadFile = useCallback(async (file: File) => {\n"
            "    const formData = new FormData();\n"
            "    formData.append('file', file);"
        ),
        replacement=(
            "  const uploadFile = useCallback(\n"
            "    async (file: File) => {\n"
            "    const formData = new FormData();\n"
            "    formData.append('file', file);\n"
            "    // Which conversation this file belongs to. The backend files it under\n"
            "    // `/wiki/raw/uploads/<session>/`, so the agent can list one conversation's\n"
            "    // attachments without reading every other conversation's.\n"
            "    formData.append('session', chatId);"
        ),
        why="without the chat id the backend cannot tell whose conversation a file belongs to",
    ),
    # The one that actually makes the feature visible. The template renders
    # `<PromptInputTools />` with nothing inside it, so the hidden file input below it has
    # nothing to click it — every other piece of the upload path is present and unreachable.
    # A turn here runs a dozen tool calls and the template renders each as its own card, so the
    # answer arrives under a wall of `ls` and `read_file`. The template already groups
    # CONSECUTIVE tool calls (`groupConsecutiveToolSegments` -> `MessageToolGroup`); it just
    # draws a border round them and still renders N cards. These two patches turn that group
    # into one collapsed line — "Working…" while it runs, "N steps" when it is done — with the
    # individual calls one click away. Reported from the deployed app 2026-09-23.
    Patch(
        path="client/src/components/message.tsx",
        anchor="import { Shimmer } from './ui/shimmer';",
        replacement=(
            "import { Shimmer } from './ui/shimmer';\n"
            "import {\n"
            "  Collapsible,\n"
            "  CollapsibleContent,\n"
            "  CollapsibleTrigger,\n"
            "} from '@/components/ui/collapsible';\n"
            "import { ChevronDownIcon } from './icons';\n"
            "import { DbIcon } from './ui/db-icon';"
        ),
        why="the collapsed group needs a disclosure widget, a chevron and the shimmer label",
    ),
    Patch(
        path="client/src/components/message.tsx",
        anchor=(
            "  const isMultiple = tools.length > 1;\n"
            "  return (\n"
            "    <div\n"
            "      className={cn('flex flex-col gap-2', {\n"
            "        'rounded-md border border-border/60 bg-muted/20 p-2': isMultiple,\n"
            "      })}\n"
            "      data-testid={isMultiple ? 'tool-group' : undefined}\n"
            "    >\n"
            "      {tools.map((tool) => (\n"
            "        <ToolPartRenderer\n"
            "          key={tool.toolCallId}\n"
            "          part={tool}\n"
            "          isLoading={isLoading}\n"
            "          submitApproval={submitApproval}\n"
            "          isSubmitting={isSubmitting}\n"
            "          pendingApprovalId={pendingApprovalId}\n"
            "        />\n"
            "      ))}\n"
            "    </div>\n"
            "  );"
        ),
        replacement=(
            "  const isMultiple = tools.length > 1;\n"
            "  const [groupOpen, setGroupOpen] = useState(false);\n"
            "  const renderTool = (tool: ToolPart) => (\n"
            "    <ToolPartRenderer\n"
            "      key={tool.toolCallId}\n"
            "      part={tool}\n"
            "      isLoading={isLoading}\n"
            "      submitApproval={submitApproval}\n"
            "      isSubmitting={isSubmitting}\n"
            "      pendingApprovalId={pendingApprovalId}\n"
            "    />\n"
            "  );\n"
            "\n"
            "  // One tool is not a wall; leave it as the template drew it.\n"
            "  if (!isMultiple) {\n"
            "    return <div className=\"flex flex-col gap-2\">{tools.map(renderTool)}</div>;\n"
            "  }\n"
            "\n"
            "  // A tool awaiting approval must never be hidden behind a disclosure: the user\n"
            "  // cannot answer a question they cannot see.\n"
            "  //\n"
            "  // Scoped to THIS group's tools. `pendingApprovalId` is a prop of the whole\n"
            "  // message, so testing it alone force-opened every group on the page whenever any\n"
            "  // approval was pending — and because `open` was then pinned true, clicking the\n"
            "  // header set `groupOpen` to false and nothing moved. That is the reported bug:\n"
            "  // expanded fine, would not collapse again.\n"
            "  const awaitingApproval =\n"
            "    pendingApprovalId != null &&\n"
            "    tools.some(\n"
            "      (tool) =>\n"
            "        tool.callProviderMetadata?.databricks?.approvalRequestId ===\n"
            "        pendingApprovalId,\n"
            "    );\n"
            "  const running = tools.some(\n"
            "    (tool) =>\n"
            "      tool.state !== 'output-available' && tool.state !== 'output-error',\n"
            "  );\n"
            "  const failed = tools.filter((tool) => tool.state === 'output-error').length;\n"
            "  const label = running\n"
            "    ? 'Working…'\n"
            "    : failed > 0\n"
            "      ? `${tools.length} steps, ${failed} failed`\n"
            "      : `${tools.length} steps`;\n"
            "\n"
            "  return (\n"
            "    <Collapsible\n"
            "      open={groupOpen || awaitingApproval}\n"
            "      onOpenChange={setGroupOpen}\n"
            "      className=\"rounded-md border border-border/60 bg-muted/20\"\n"
            "      data-testid=\"tool-group\"\n"
            "    >\n"
            "      <CollapsibleTrigger\n"
            "        data-testid=\"tool-group-summary\"\n"
            "        className=\"flex w-full items-center gap-2 px-3 py-2 text-left text-muted-foreground text-sm\"\n"
            "      >\n"
            "        <DbIcon\n"
            "          icon={ChevronDownIcon}\n"
            "          className={cn('size-4 transition-transform', {\n"
            "            'rotate-180': groupOpen || awaitingApproval,\n"
            "          })}\n"
            "        />\n"
            "        {running ? <Shimmer>{label}</Shimmer> : <span>{label}</span>}\n"
            "      </CollapsibleTrigger>\n"
            "      <CollapsibleContent className=\"flex flex-col gap-2 p-2 pt-0\">\n"
            "        {tools.map(renderTool)}\n"
            "      </CollapsibleContent>\n"
            "    </Collapsible>\n"
            "  );"
        ),
        why="a dozen separate tool cards bury the answer the user is waiting for",
    ),
    # Tool steps open expanded in the stock template. For this assistant a single turn can run
    # a dozen of them - ls, read, write, per skill - and each expanded block pushes the actual
    # answer off the screen. The step list is still there and still clickable; it just does not
    # shout. Reported from the deployed app on 2026-09-23.
    Patch(
        path="client/src/components/message.tsx",
        anchor="      <McpTool defaultOpen={true}>",
        replacement="      <McpTool defaultOpen={false}>",
        why="an expanded MCP tool block pushes the answer below the fold",
    ),
    Patch(
        path="client/src/components/message.tsx",
        anchor="    <Tool defaultOpen={true}>",
        replacement="    <Tool defaultOpen={false}>",
        why="an expanded tool block per step buries the answer under the working",
    ),
    Patch(
        path="client/src/components/multimodal-input.tsx",
        anchor="import { ChevronDownIcon, ArrowUpIcon, StopIcon } from './icons';",
        replacement=(
            "import {\n"
            "  ChevronDownIcon,\n"
            "  ArrowUpIcon,\n"
            "  StopIcon,\n"
            "  PaperclipIcon,\n"
            "} from './icons';"
        ),
        why="the attach button needs an icon, and the template's barrel already exports one",
    ),
    Patch(
        path="client/src/components/multimodal-input.tsx",
        anchor='            <PromptInputTools className="gap-0 sm:gap-0.5" />',
        replacement=(
            '            <PromptInputTools className="gap-0 sm:gap-0.5">\n'
            "              {/* The template leaves this toolbar empty, so the hidden file input\n"
            "                  below has nothing to trigger it. Everything else in the upload\n"
            "                  path - the input, handleFileChange, uploadQueue, the previews -\n"
            "                  already exists and is unreachable without this. */}\n"
            "              <Button\n"
            '                data-testid="attachments-button"\n'
            '                aria-label="Attach files"\n'
            # `ghost` is the stock shadcn name and this template does not have it;
            # `tertiary` is its Databricks-design-system equivalent, transparent
            # until hover. Typechecks, where `ghost` is a TS2322 and at runtime a
            # button with no variant classes at all.
            '                variant="tertiary"\n'
            "                disabled={status !== 'ready'}\n"
            "                onClick={(event) => {\n"
            "                  event.preventDefault();\n"
            "                  fileInputRef.current?.click();\n"
            "                }}\n"
            '                className="size-8 rounded-full p-0 text-muted-foreground hover:text-foreground"\n'
            "              >\n"
            '                <DbIcon icon={PaperclipIcon} className="size-4" />\n'
            "              </Button>\n"
            "            </PromptInputTools>"
        ),
        why="without a button in the toolbar the paperclip is not rendered at all",
    ),
    # The template's own message schema admits ONLY image/jpeg and image/png, with an absolute
    # URL. A `.py` attachment therefore fails validation and the whole send returns
    # `bad_request:api` - "The request couldn't be processed." Reproduced against the deployed
    # app on 2026-09-23; a text-only message with the same content returns 200.
    #
    # The bytes do not need to be in the message at all: they are already on the artifact
    # Volume, which is where the agent reads them. So the filenames travel as text and the
    # `file` parts are not sent. Patching the shared zod schema instead would widen this overlay
    # into `packages/core` to carry data nothing downstream reads.
    Patch(
        path="client/src/components/multimodal-input.tsx",
        anchor=(
            "    sendMessage({\n"
            "      role: 'user',\n"
            "      parts: [\n"
            "        ...attachments.map((attachment) => ({\n"
            "          type: 'file' as const,\n"
            "          url: attachment.url,\n"
            "          name: attachment.name,\n"
            "          mediaType: attachment.contentType,\n"
            "        })),\n"
            "        {\n"
            "          type: 'text',\n"
            "          text: input,\n"
            "        },\n"
            "      ],\n"
            "    });"
        ),
        replacement=(
            "    // Attachments are named in the text rather than sent as `file` parts: the\n"
            "    // template's schema admits only image/jpeg and image/png with an absolute URL,\n"
            "    // so any other attachment fails validation and the send returns bad_request.\n"
            "    // The bytes are already on the wiki Volume, which is where the agent reads\n"
            "    // them, so nothing is lost by leaving them out of the message.\n"
            "    const attachedNames = attachments\n"
            "      .map((attachment) => attachment.name)\n"
            "      .filter((name): name is string => Boolean(name));\n"
            "    const composedText = attachedNames.length\n"
            "      ? `[attached to this conversation: ${attachedNames.join(', ')}]\\n\\n${input}`\n"
            "      : input;\n"
            "\n"
            "    sendMessage({\n"
            "      role: 'user',\n"
            "      parts: [\n"
            "        {\n"
            "          type: 'text',\n"
            "          text: composedText,\n"
            "        },\n"
            "      ],\n"
            "    });"
        ),
        why="a non-image attachment fails the message schema and the whole send is rejected",
    ),
    Patch(
        path="client/src/components/multimodal-input.tsx",
        anchor="                disabled={!input.trim() || uploadQueue.length > 0}",
        replacement=(
            "                disabled={\n"
            "                  (!input.trim() && attachments.length === 0) ||\n"
            "                  uploadQueue.length > 0\n"
            "                }"
        ),
        why="attaching files with no typed text is a reasonable thing to do and was unsendable",
    ),
    Patch(
        path="client/src/components/multimodal-input.tsx",
        anchor=(
            "      toast.error('Failed to upload file, please try again!');\n"
            "    }\n"
            "  }, []);"
        ),
        replacement=(
            "      toast.error('Failed to upload file, please try again!');\n"
            "    }\n"
            "    },\n"
            "    [chatId],\n"
            "  );"
        ),
        why="`chatId` is now read inside the callback, so it belongs in the dependency list",
    ),
)


class OverlayError(RuntimeError):
    """The template has moved under the overlay. Always names the file and what was expected."""


def _check(frontend: Path) -> list[Patch]:
    """Patches still to apply. Raises when one can neither be applied nor be already present."""
    pending = []
    for patch in PATCHES:
        target = frontend / patch.path
        if not target.is_file():
            raise OverlayError(
                f"{patch.path} is not in the cloned template. The overlay was written against "
                f"commit {TEMPLATE_COMMIT[:12]}; upstream appears to have moved."
            )
        body = target.read_text(encoding="utf-8")
        if patch.replacement in body:
            continue
        occurrences = body.count(patch.anchor)
        if occurrences != 1:
            raise OverlayError(
                f"{patch.path}: expected exactly one occurrence of the anchor and found "
                f"{occurrences}. The overlay was written against commit "
                f"{TEMPLATE_COMMIT[:12]}.\n"
                f"  Needed because: {patch.why}\n"
                f"  Anchor: {patch.anchor.strip().splitlines()[0][:100]}...\n"
                f"  Re-pin it by hand — see frontend_overlay/README.md. Do NOT skip this: the "
                f"upload button is present in the UI whether or not it works, so a patch that "
                f"silently no-ops looks exactly like one that applied."
            )
        pending.append(patch)
    return pending


def apply(frontend: Path) -> int:
    """Copy and patch. Returns how many patches were applied; 0 means already current."""
    if not frontend.is_dir():
        raise OverlayError(f"{frontend} does not exist; clone the template first")

    for relative in COPIED:
        source = OVERLAY_DIR / relative
        if not source.is_file():
            raise OverlayError(f"{source} is missing from frontend_overlay/ — repo regression")
        destination = frontend / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    pending = _check(frontend)
    for patch in pending:
        target = frontend / patch.path
        body = target.read_text(encoding="utf-8")
        target.write_text(body.replace(patch.anchor, patch.replacement, 1), encoding="utf-8")
    return len(pending)
