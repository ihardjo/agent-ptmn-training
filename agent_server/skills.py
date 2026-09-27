"""The skill menu the model is offered, and how it reaches the model.

The repository's `skills/` tree is the catalogue; `SELECTED_SKILLS` is the
configuration. They are separate so that adding a skill to the repository does
not silently put it in front of the model.
"""

import logging
from pathlib import Path
from typing import Any

from deepagents.backends.utils import create_file_data

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
SKILLS_MOUNT = "/skills/"

logger = logging.getLogger(__name__)

## Skill Selection — copy the skills to put inside SELECTED_SKILLS.
# "auditing-data-quality",
# "checking-due-dates",
# "computing-target-adherence",
# "measuring-sprint-velocity",
# "splitting-planned-unplanned-work",
# "summarising-root-causes",
# "escalating-breaches",
# "report-from-template",
# "formatting-service-review",
# "ranking-squad-performance",

SELECTED_SKILLS = (
    ## TODO 4: Skill Selection — copy the skills to put inside SELECTED_SKILLS.
    
)

def skill_files() -> dict[str, Any]:
    """Every file of every selected skill, keyed by its agent-visible path.

    **The whole bundle, not just `SKILL.md`.** A skill may carry reference
    files — `report-from-template` ships the approved report layout — and
    `check-skills` validates that those links resolve. Seeding only `SKILL.md`
    made that validation a lie at runtime: the link passed conformance, and the
    path it pointed at did not exist in the filesystem the model reads, so the
    skill told the model to open a file that was not there.

    Only `name` and `description` reach the prompt regardless; a reference costs
    nothing until the model chooses to read it.

    Undecodable files are skipped rather than raising. The authoring standard
    forbids scripts and the references are markdown, so this should never fire —
    but a binary dropped into a skill directory should cost that one file, not
    the ability to start.
    """
    files: dict[str, Any] = {}
    for name in SELECTED_SKILLS:
        root = SKILLS_DIR / name
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            try:
                content = path.read_text()
            except (UnicodeDecodeError, OSError):
                logger.warning("skill %s: skipped unreadable file %s", name, path.name)
                continue
            files[f"{SKILLS_MOUNT}{name}/{path.relative_to(root).as_posix()}"] = (
                create_file_data(content)
            )
    return files
