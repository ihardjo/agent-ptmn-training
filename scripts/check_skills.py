#!/usr/bin/env python3
"""Check the skills tier against the published Agent Skills authoring standard.

The tier is instructions that reach the model's prompt, so a limit checked by
eye is a limit that drifts. This is the command that says no.

    uv run check-skills                 # the repository tier
    uv run check-skills --dir <path>    # any tier, used by the fixtures

Checks, in the order the standard states them:

  name          <=64 chars, ^[a-z0-9-]+$, no reserved vendor word, no XML tag,
                and matching its directory, so a rename cannot half-land
  description   non-empty, <=1024 chars, no XML tag, third person
  body          under 500 lines
  references    resolve inside the skill, and one level deep only
  risk          no scripts, no URLs, no credentials, no path traversal
  registry      every skill has an entry and every entry has a skill
  redirects     the skill-to-skill reference graph is acyclic

Exits non-zero when any skill violates any of them.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
REGISTRY = "REGISTRY.md"
SKILL_FILE = "SKILL.md"

NAME_MAX = 64
DESCRIPTION_MAX = 1024
BODY_MAX_LINES = 500

NAME_RE = re.compile(r"^[a-z0-9-]+$")
RESERVED = ("anthropic", "claude")
XML_TAG_RE = re.compile(r"<[a-zA-Z/][^>]*>")

# Third person. The standard's concern is the point of view the description is
# written from, not any occurrence of a pronoun -- "Use when the user asks" is
# correct and must not trip this.
FIRST_SECOND_PERSON_RE = re.compile(
    r"(^\s*(I|You|We|My|Our|Your)\b)|(\b(I can|I will|you can|we can|I help|I am)\b)",
    re.IGNORECASE | re.MULTILINE,
)

SCRIPT_SUFFIXES = (".py", ".sh", ".js", ".rb", ".pl", ".ps1")
URL_RE = re.compile(r"https?://")
TRAVERSAL_RE = re.compile(r"\.\./")
CREDENTIAL_RE = re.compile(
    r"\b(api[_-]?key|secret|token|password|passwd|bearer)\b\s*[:=]\s*\S{8,}",
    re.IGNORECASE,
)

# Markdown links. Bundled references are relative; a link to another tier is an
# absolute agent-filesystem path and is not a bundled file at all.
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


class Finding(str):
    """A single conformance failure, rendered as its own message."""


def _skill_dirs(root: Path) -> list[Path]:
    return sorted(p.parent for p in root.glob(f"*/{SKILL_FILE}"))


def _split_front_matter(text: str) -> tuple[dict, str]:
    """The frontmatter mapping and the body below it.

    A missing or unparseable block yields an empty mapping rather than raising:
    the caller reports it as a finding, which is more useful than a traceback
    naming a file the reader has to go and find.
    """
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        data = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}, parts[2]
    return (data if isinstance(data, dict) else {}), parts[2]


def check_name(skill: Path, meta: dict) -> list[Finding]:
    out: list[Finding] = []
    name = meta.get("name")
    if not name:
        out.append(Finding(f"{skill.name}: no `name` in frontmatter"))
    else:
        name = str(name)
        if len(name) > NAME_MAX:
            out.append(Finding(f"{skill.name}: name is {len(name)} chars, limit {NAME_MAX}"))
        if not NAME_RE.match(name):
            out.append(
                Finding(f"{skill.name}: name {name!r} is not lowercase letters, numbers, hyphens")
            )
        if any(w in name.lower() for w in RESERVED):
            out.append(Finding(f"{skill.name}: name {name!r} contains a reserved vendor word"))
        if XML_TAG_RE.search(name):
            out.append(Finding(f"{skill.name}: name contains an XML tag"))
        if name != skill.name:
            out.append(
                Finding(f"{skill.name}: name {name!r} does not match its directory {skill.name!r}")
            )
    return out


def check_description(skill: Path, meta: dict) -> list[Finding]:
    out: list[Finding] = []
    description = meta.get("description")
    if not description or not str(description).strip():
        out.append(Finding(f"{skill.name}: description is empty"))
    else:
        description = str(description)
        if len(description) > DESCRIPTION_MAX:
            out.append(
                Finding(
                    f"{skill.name}: description is {len(description)} chars, "
                    f"limit {DESCRIPTION_MAX}"
                )
            )
        if XML_TAG_RE.search(description):
            out.append(Finding(f"{skill.name}: description contains an XML tag"))
        hit = FIRST_SECOND_PERSON_RE.search(description)
        if hit:
            out.append(
                Finding(
                    f"{skill.name}: description is not third person — found {hit.group(0)!r}"
                )
            )
    return out


def check_body(skill: Path, body: str) -> list[Finding]:
    lines = body.strip().splitlines()
    if len(lines) > BODY_MAX_LINES:
        return [Finding(f"{skill.name}: body is {len(lines)} lines, limit {BODY_MAX_LINES}")]
    return []


def _bundled_links(text: str) -> list[str]:
    """Relative markdown links only.

    An absolute path is a reference to another filesystem tier -- `/wiki/...`
    -- not a bundled file, so depth does not apply to it.
    """
    return [
        t
        for t in LINK_RE.findall(text)
        if not t.startswith(("/", "#", "http://", "https://", "mailto:"))
    ]


def check_references(skill: Path) -> list[Finding]:
    out: list[Finding] = []
    for target in _bundled_links((skill / SKILL_FILE).read_text()):
        resolved = (skill / target.split("#", 1)[0]).resolve()
        if not str(resolved).startswith(str(skill.resolve())):
            out.append(Finding(f"{skill.name}: reference {target!r} escapes the skill directory"))
            continue
        if not resolved.exists():
            out.append(Finding(f"{skill.name}: reference {target!r} does not exist"))
            continue
        nested = _bundled_links(resolved.read_text())
        if nested:
            out.append(
                Finding(
                    f"{skill.name}: {target!r} links onward to {nested[0]!r} — "
                    "references must be one level deep from " + SKILL_FILE
                )
            )
    return out


def check_risk_indicators(skill: Path) -> list[Finding]:
    out: list[Finding] = []
    for path in sorted(skill.rglob("*")):
        if path.is_file() and path.suffix in SCRIPT_SUFFIXES:
            out.append(Finding(f"{skill.name}: contains an executable script {path.name!r}"))
    for path in sorted(skill.rglob("*.md")):
        text = path.read_text()
        if URL_RE.search(text):
            out.append(Finding(f"{skill.name}: {path.name} contains a URL"))
        if CREDENTIAL_RE.search(text):
            out.append(Finding(f"{skill.name}: {path.name} contains a credential-shaped string"))
        if TRAVERSAL_RE.search(text):
            out.append(Finding(f"{skill.name}: {path.name} contains a path traversal"))
    return out


def check_registry(root: Path, skills: list[Path]) -> list[Finding]:
    registry = root / REGISTRY
    if not registry.exists():
        return [Finding(f"no {REGISTRY} at the tier root — every skill needs an entry")]
    # Only the first cell of each table row names a skill. Matching every
    # backticked token would also pick up the column names listed under
    # Dependencies, which are not skills and must not be reported as missing.
    listed = {
        m.group(1)
        for m in (
            re.match(r"\|\s*`([a-z0-9-]+)`\s*\|", line.strip())
            for line in registry.read_text().splitlines()
        )
        if m
    }
    present = {s.name for s in skills}
    out = [Finding(f"{n}: present in the tier but absent from {REGISTRY}") for n in sorted(present - listed)]
    out += [Finding(f"{n}: listed in {REGISTRY} but no such skill") for n in sorted(listed - present)]
    return out


def check_redirects(skills: list[Path]) -> list[Finding]:
    """The skill-to-skill reference graph must be acyclic.

    Two skills that name each other send the agent back and forth instead of
    to an answer, which is a defect that only shows up at runtime.
    """
    names = {s.name for s in skills}
    graph = {
        s.name: {n for n in names if n != s.name and n in (s / SKILL_FILE).read_text()}
        for s in skills
    }
    out: list[Finding] = []
    seen: set[str] = set()

    def walk(node: str, path: list[str]) -> None:
        if node in path:
            cycle = " -> ".join(path[path.index(node) :] + [node])
            out.append(Finding(f"redirect cycle: {cycle}"))
            return
        if node in seen:
            return
        seen.add(node)
        for nxt in sorted(graph[node]):
            walk(nxt, path + [node])

    for name in sorted(graph):
        walk(name, [])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", type=Path, default=SKILLS_DIR, help="tier to check")
    args = ap.parse_args()

    root: Path = args.dir
    if not root.is_dir():
        print(f"No skills tier at {root} — nothing to check.")
        sys.exit(0)

    skills = _skill_dirs(root)
    findings: list[Finding] = []
    for skill in skills:
        meta, body = _split_front_matter((skill / SKILL_FILE).read_text())
        findings += check_name(skill, meta)
        findings += check_description(skill, meta)
        findings += check_body(skill, body)
        findings += check_references(skill)
        findings += check_risk_indicators(skill)
    findings += check_registry(root, skills)
    findings += check_redirects(skills)

    print(f"{root}: {len(skills)} skill(s)")
    if not findings:
        print("  conformant with the Agent Skills authoring standard")
        sys.exit(0)
    for f in findings:
        print(f"  FAIL {f}")
    sys.exit(1)


if __name__ == "__main__":
    main()
