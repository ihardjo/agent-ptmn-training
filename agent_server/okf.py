"""Open Knowledge Format v0.2 — parsing, conformance, and conformant writes.

OKF is the format the `/wiki/` tier is written in: a directory tree of markdown
concepts, each carrying a YAML frontmatter block. Spec:
https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md

Only three things are actually required (§11):

1. every non-reserved `.md` file has a parseable YAML frontmatter block,
2. every frontmatter block has a non-empty `type`,
3. `index.md` and `log.md`, when present, are a listing and a history (§8, §9)
   rather than concepts.

Everything else in the spec is SHOULD, and consumers **must not** reject a
document for an unknown `type`, unrecognised keys, missing optional fields, or a
broken cross-link. That asymmetry is the point of the format and it is enforced
here in both directions: `conformance_errors` reports only the three hard rules,
and nothing in this module refuses a document for a soft violation.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Mapping, Optional

import yaml

# §3.1 — reserved at any level of the hierarchy, and never concept documents.
RESERVED = frozenset({"index.md", "log.md"})

# §4.1 — the delimiter is `---` on its own line at the start of the file.
_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)

# §9 — date headings in a log are ISO 8601 calendar dates.
_LOG_DATE_HEADING = re.compile(r"^##\s+\d{4}-\d{2}-\d{2}\s*$", re.MULTILINE)

# §8 — an index entry is a markdown list item carrying a link.
_INDEX_ENTRY = re.compile(r"^\s*[*+-]\s+\[.+?\]\(.+?\)", re.MULTILINE)

def _iso(value: datetime | date) -> str:
    """A timestamp in the canonical form OKF §5 asks for."""
    if isinstance(value, datetime):
        text = value.isoformat()
        return text.replace("+00:00", "Z")
    return value.isoformat()


class _Dumper(yaml.SafeDumper):
    """A dumper that writes timestamps the way OKF reads them.

    Needed because YAML parses an unquoted `2026-07-01T04:00:00Z` into a
    `datetime`, and `safe_dump` writes a `datetime` back as
    `2026-07-01 04:00:00+00:00` — space-separated, not the `T...Z` form §5
    specifies. Every rewrite of a document would otherwise walk its timestamps
    one step further from the spec, silently and irreversibly.
    """


_Dumper.add_representer(
    datetime, lambda d, v: d.represent_scalar("tag:yaml.org,2002:str", _iso(v))
)
_Dumper.add_representer(
    date, lambda d, v: d.represent_scalar("tag:yaml.org,2002:str", _iso(v))
)


# The small fixed vocabulary the write path may assign (design Decision 10).
# The agent does not choose its own `type`, so the set stays legible.
NOTE_TYPES = ("Observation", "Analysis")
DEFAULT_NOTE_TYPE = "Observation"


def parse(text: str) -> tuple[Optional[dict[str, Any]], str]:
    """Split a document into its frontmatter mapping and its body.

    Returns `(None, text)` when there is no frontmatter block or the block does
    not parse as a YAML mapping — the two cases §11 rule 1 and 2 care about,
    which the caller distinguishes by asking for `conformance_errors`.
    """
    match = _FRONTMATTER.match(text)
    if not match:
        return None, text
    try:
        loaded = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None, text[match.end() :]
    if not isinstance(loaded, dict):
        return None, text[match.end() :]
    return loaded, text[match.end() :]


def is_reserved(path: str) -> bool:
    """Whether `path` names a reserved file, at any depth."""
    return path.rsplit("/", 1)[-1] in RESERVED


def conformance_errors(documents: Mapping[str, str]) -> list[str]:
    """The §11 violations in a bundle, as messages naming the document.

    `documents` maps path to text, so the same check runs over a local
    directory and over the Volume without knowing which it was given.
    """
    errors: list[str] = []
    for path in sorted(documents):
        if not path.endswith(".md"):
            continue
        text = documents[path]
        name = path.rsplit("/", 1)[-1]

        if name == "index.md":
            errors.extend(_index_errors(path, text))
            continue
        if name == "log.md":
            errors.extend(_log_errors(path, text))
            continue

        frontmatter, _ = parse(text)
        if frontmatter is None:
            errors.append(f"{path}: no parseable YAML frontmatter block (§11.1)")
            continue
        declared = frontmatter.get("type")
        if not (isinstance(declared, str) and declared.strip()):
            errors.append(f"{path}: frontmatter has no non-empty `type` (§11.2)")
    return errors


def _index_errors(path: str, text: str) -> list[str]:
    """§8 — an index is a listing, and carries frontmatter only at the root."""
    errors: list[str] = []
    frontmatter, body = parse(text)
    if frontmatter is not None:
        # The bundle-root index may declare `okf_version` and nothing else;
        # frontmatter anywhere else in an index is not permitted (§8, §12).
        at_root = "/" not in path.strip("/")
        extra = set(frontmatter) - {"okf_version"}
        if not at_root:
            errors.append(f"{path}: only a bundle-root index.md may carry frontmatter (§8)")
        elif extra:
            errors.append(
                f"{path}: a root index.md may declare only `okf_version`, found {sorted(extra)} (§8)"
            )
    if not _INDEX_ENTRY.search(body):
        errors.append(f"{path}: an index.md must list its contents as linked entries (§8)")
    return errors


def _log_errors(path: str, text: str) -> list[str]:
    """§9 — a log is date-grouped entries, newest first, and has no frontmatter."""
    errors: list[str] = []
    frontmatter, body = parse(text)
    if frontmatter is not None:
        errors.append(f"{path}: a log.md must not carry frontmatter (§9)")
    headings = _LOG_DATE_HEADING.findall(body)
    if not headings:
        errors.append(f"{path}: a log.md must group entries under `## YYYY-MM-DD` headings (§9)")
        return errors
    dates = [h.split()[-1] for h in headings]
    if dates != sorted(dates, reverse=True):
        errors.append(f"{path}: log.md entries must be newest first (§9), found {dates}")
    return errors


def ensure_conformant(
    content: str,
    *,
    actor: str,
    default_type: str = DEFAULT_NOTE_TYPE,
    now: Optional[datetime] = None,
) -> str:
    """Return `content` with the frontmatter a conformant concept needs.

    Called on the write path rather than requested in the prompt. The agent is a
    *producer* of this bundle, not only a consumer, so a note written without
    frontmatter would break conformance for every later reader — and an
    instruction to remember frontmatter is the kind of thing that holds most of
    the time rather than all of the time.

    What it supplies: a non-empty `type` (from the fixed note vocabulary, never
    the model's choice) and `generated: {by, at}` so a later reader can tell what
    produced the note and when. What it leaves alone: everything else the agent
    wrote, including keys this module does not recognise.
    """
    stamp = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    frontmatter, body = parse(content)
    if frontmatter is None:
        # No frontmatter, or frontmatter that did not parse. The body is kept
        # verbatim; a malformed block is not silently repaired into something
        # that might mean something different.
        frontmatter, body = {}, content
    else:
        frontmatter = dict(frontmatter)

    declared = frontmatter.get("type")
    if not (isinstance(declared, str) and declared.strip()):
        frontmatter["type"] = default_type

    generated = frontmatter.get("generated")
    if not isinstance(generated, dict) or not generated.get("by"):
        frontmatter["generated"] = {"by": actor, "at": stamp}
    elif not generated.get("at"):
        frontmatter["generated"] = {**generated, "at": stamp}

    rendered = yaml.dump(
        frontmatter, Dumper=_Dumper, sort_keys=False, allow_unicode=True
    ).rstrip("\n")
    return f"---\n{rendered}\n---\n\n{body.lstrip(chr(10))}"
