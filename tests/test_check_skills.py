"""Every conformance check must fire, and the clean tier must pass.

A checker that never fails is worse than no checker: it converts an unchecked
limit into one everybody believes is enforced. So each check gets a fixture
that violates exactly one rule, and the suite asserts the specific finding
rather than merely a non-zero exit — otherwise a check could pass its own
fixture for the wrong reason.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = REPO_ROOT / "scripts" / "check_skills.py"

GOOD_DESCRIPTION = "Does a narrow thing. Use when asked to do that narrow thing."


def write_tier(
    root: Path,
    skills: list[tuple[str, str, str, dict[str, str] | None]],
    registry: list[str] | None = None,
) -> Path:
    for name, front, body, extra in skills:
        d = root / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\n{front}\n---\n\n{body}\n")
        for filename, content in (extra or {}).items():
            (d / filename).write_text(content)
    names = registry if registry is not None else [s[0] for s in skills]
    (root / "REGISTRY.md").write_text(
        "| Skill |\n|---|\n" + "".join(f"| `{n}` |\n" for n in names)
    )
    return root


def run_checker(root: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--dir", str(root)],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout


def good_skill(name: str = "good-skill") -> tuple[str, str, str, None]:
    return (name, f"name: {name}\ndescription: {GOOD_DESCRIPTION}", "# Good", None)


# Each case: label, the skills making up the tier, and a fragment that must
# appear in the reported finding.
CASES = [
    (
        "name-too-long",
        [("a" * 70, f"name: {'a' * 70}\ndescription: {GOOD_DESCRIPTION}", "# x", None)],
        "name is 70 chars, limit 64",
    ),
    (
        "name-bad-chars",
        [("Bad_Name", f"name: Bad_Name\ndescription: {GOOD_DESCRIPTION}", "# x", None)],
        "is not lowercase letters, numbers, hyphens",
    ),
    (
        "name-reserved-word",
        [
            (
                "claude-helper",
                f"name: claude-helper\ndescription: {GOOD_DESCRIPTION}",
                "# x",
                None,
            )
        ],
        "contains a reserved vendor word",
    ),
    (
        "name-mismatches-directory",
        [("dir-name", f"name: other-name\ndescription: {GOOD_DESCRIPTION}", "# x", None)],
        "does not match its directory",
    ),
    (
        "description-empty",
        [("empty-desc", "name: empty-desc\ndescription: ''", "# x", None)],
        "description is empty",
    ),
    (
        "description-too-long",
        [("long-desc", f"name: long-desc\ndescription: {'z' * 1100}", "# x", None)],
        "description is 1100 chars, limit 1024",
    ),
    (
        "body-too-long",
        [
            (
                "long-body",
                f"name: long-body\ndescription: {GOOD_DESCRIPTION}",
                "\n".join(f"line {i}" for i in range(520)),
                None,
            )
        ],
        "body is 520 lines, limit 500",
    ),
    (
        "description-first-person",
        [
            (
                "first-person",
                "name: first-person\ndescription: I can help diff JSON. Use when asked.",
                "# x",
                None,
            )
        ],
        "not third person",
    ),
    (
        "description-second-person",
        [
            (
                "second-person",
                "name: second-person\ndescription: You can use this to diff JSON. Use when asked.",
                "# x",
                None,
            )
        ],
        "not third person",
    ),
    (
        "reference-nested-two-levels",
        [
            (
                "nested-ref",
                f"name: nested-ref\ndescription: {GOOD_DESCRIPTION}",
                "See [a](a.md)",
                {"a.md": "See [b](b.md)", "b.md": "end"},
            )
        ],
        "references must be one level deep",
    ),
    (
        "reference-missing",
        [
            (
                "missing-ref",
                f"name: missing-ref\ndescription: {GOOD_DESCRIPTION}",
                "See [gone](gone.md)",
                None,
            )
        ],
        "does not exist",
    ),
    (
        "risk-executable-script",
        [
            (
                "has-script",
                f"name: has-script\ndescription: {GOOD_DESCRIPTION}",
                "# x",
                {"run.py": "print(1)"},
            )
        ],
        "contains an executable script",
    ),
    (
        "risk-url",
        [
            (
                "has-url",
                f"name: has-url\ndescription: {GOOD_DESCRIPTION}",
                "See https://example.com/doc",
                None,
            )
        ],
        "contains a URL",
    ),
    (
        "risk-credential",
        [
            (
                "has-cred",
                f"name: has-cred\ndescription: {GOOD_DESCRIPTION}",
                "api_key = sk-abcdef123456",
                None,
            )
        ],
        "credential-shaped string",
    ),
    (
        "risk-path-traversal",
        [
            (
                "has-traversal",
                f"name: has-traversal\ndescription: {GOOD_DESCRIPTION}",
                "Read ../../etc/passwd",
                None,
            )
        ],
        "contains a path traversal",
    ),
    (
        "redirect-cycle",
        [
            (
                "skill-one",
                f"name: skill-one\ndescription: {GOOD_DESCRIPTION}",
                "Go to skill-two",
                None,
            ),
            (
                "skill-two",
                f"name: skill-two\ndescription: {GOOD_DESCRIPTION}",
                "Go to skill-one",
                None,
            ),
        ],
        "redirect cycle",
    ),
]


@pytest.mark.parametrize("label,skills,expected", CASES, ids=[c[0] for c in CASES])
def test_check_fires(tmp_path, label, skills, expected):
    code, out = run_checker(write_tier(tmp_path / label, skills))
    assert code == 1, f"{label} should fail conformance:\n{out}"
    assert expected in out, f"{label} failed for the wrong reason:\n{out}"


def test_registry_missing_entry(tmp_path):
    code, out = run_checker(write_tier(tmp_path / "t", [good_skill()], registry=[]))
    assert code == 1
    assert "present in the tier but absent from REGISTRY.md" in out


def test_registry_entry_without_skill(tmp_path):
    root = write_tier(tmp_path / "t", [good_skill()], registry=["good-skill", "ghost-skill"])
    code, out = run_checker(root)
    assert code == 1
    assert "listed in REGISTRY.md but no such skill" in out


def test_registry_absent_entirely(tmp_path):
    root = write_tier(tmp_path / "t", [good_skill()])
    (root / "REGISTRY.md").unlink()
    code, out = run_checker(root)
    assert code == 1
    assert "no REGISTRY.md at the tier root" in out


def test_conforming_tier_passes(tmp_path):
    """The control. Without it, every check above could be passing vacuously."""
    code, out = run_checker(write_tier(tmp_path / "clean", [good_skill()]))
    assert code == 0, out
    assert "conformant with the Agent Skills authoring standard" in out


def test_absent_tier_is_not_a_failure(tmp_path):
    """Degradation matches the agent's own: no skills is a supported state."""
    code, out = run_checker(tmp_path / "does-not-exist")
    assert code == 0, out


def test_repository_tier_conforms():
    """The tier actually shipped must pass, not only the fixtures."""
    result = subprocess.run(
        [sys.executable, str(CHECKER)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_third_person_allows_the_user_phrasing(tmp_path):
    """Guard against the check being too eager.

    'Use when the user asks...' is the standard's own recommended phrasing.
    A third-person check that rejects it would push authors toward worse
    descriptions, which is the opposite of the point.
    """
    skill = (
        "user-phrasing",
        "name: user-phrasing\n"
        "description: Extracts tables from documents. Use when the user mentions "
        "tables, or when your output needs tabular data.",
        "# x",
        None,
    )
    code, out = run_checker(write_tier(tmp_path / "t", [skill]))
    assert code == 0, out
