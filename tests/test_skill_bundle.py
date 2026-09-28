"""What of a skill actually reaches the model's filesystem.

`check-skills` validates that a bundled reference link resolves, which is only
meaningful if the file is also seeded. For a while it was not, so a skill could
tell the model to open a file that was not there.
"""

from __future__ import annotations

import re

import pytest

from agent_server import skills as skills_module
from agent_server.skills import SKILLS_DIR, SKILLS_MOUNT, skill_files

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


@pytest.fixture
def seeded(monkeypatch):
    """The full menu, so selection cannot hide a broken reference."""
    names = sorted(p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md"))
    monkeypatch.setattr(skills_module, "SELECTED_SKILLS", tuple(names))
    return skill_files()


def test_every_skill_contributes_its_own_file(seeded):
    names = sorted(p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md"))
    for name in names:
        assert f"{SKILLS_MOUNT}{name}/SKILL.md" in seeded


def test_every_bundled_reference_is_seeded_too(seeded):
    """The property that was broken. A relative link in a SKILL.md must resolve
    to a path the model can actually read."""
    missing = []
    for path, data in list(seeded.items()):
        if not path.endswith("SKILL.md"):
            continue
        base = path.rsplit("/", 1)[0]
        body = "".join(data["content"]) if isinstance(data.get("content"), list) else data["content"]
        for target in LINK_RE.findall(body):
            if target.startswith(("/", "#", "http://", "https://", "mailto:")):
                continue
            wanted = f"{base}/{target.split('#', 1)[0]}"
            if wanted not in seeded:
                missing.append(f"{path} links to {target!r}, not seeded as {wanted!r}")
    assert not missing, "\n".join(missing)


def test_the_report_template_is_reachable(seeded):
    """Named explicitly: this is the reference the feature exists for, and a
    silent rename of the file would otherwise only show up in a live run."""
    path = f"{SKILLS_MOUNT}report-from-template/references/sprint-report-template.md"
    assert path in seeded
    body = seeded[path]["content"]
    body = "".join(body) if isinstance(body, list) else body
    # On the shape rather than one heading's wording, so that dropping a section
    # the table cannot fill renumbers the rest without failing here.
    numbered = re.findall(r"^## (\d+)\. \S", body, re.MULTILINE)
    assert numbered == [str(i) for i in range(1, len(numbered) + 1)], (
        f"the template lost its numbered sections, found {numbered}"
    )
    assert len(numbered) >= 4


def test_an_unselected_skill_contributes_nothing(monkeypatch):
    """Selection still gates the tier. A reference must not smuggle a skill in."""
    monkeypatch.setattr(skills_module, "SELECTED_SKILLS", ("report-from-template",))
    seeded = skill_files()
    assert all(p.startswith(f"{SKILLS_MOUNT}report-from-template/") for p in seeded)


def test_an_empty_selection_seeds_nothing(monkeypatch):
    monkeypatch.setattr(skills_module, "SELECTED_SKILLS", ())
    assert skill_files() == {}


def test_an_undecodable_file_costs_one_file_not_the_startup(monkeypatch, tmp_path):
    """A binary dropped into a skill directory should not stop the agent."""
    root = tmp_path / "broken-skill"
    root.mkdir()
    (root / "SKILL.md").write_text("---\nname: broken-skill\ndescription: x\n---\n\nbody\n")
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")
    monkeypatch.setattr(skills_module, "SKILLS_DIR", tmp_path)
    monkeypatch.setattr(skills_module, "SELECTED_SKILLS", ("broken-skill",))
    seeded = skill_files()
    assert list(seeded) == [f"{SKILLS_MOUNT}broken-skill/SKILL.md"]
