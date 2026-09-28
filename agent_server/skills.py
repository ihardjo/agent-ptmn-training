"""The skill menu the model is offered, and how it reaches the model.

`skills/` is the catalogue and `SELECTED_SKILLS` is the configuration, so adding
a skill to the repository does not silently put it in front of the model.
"""

import logging
from pathlib import Path
from typing import Any

from deepagents.backends.utils import create_file_data

from agent_server.env import resolve

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

    The whole bundle, not just `SKILL.md`: a skill may carry reference files,
    and seeding only `SKILL.md` made `check-skills`'s reference validation a lie
    at runtime. Undecodable files are skipped, so a binary in a skill directory
    costs that file rather than the startup.
    """
    files: dict[str, Any] = {}
    for name in SELECTED_SKILLS:
        root = SKILLS_DIR / name
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            try:
                # Same substitution as the system prompt: a skill's SQL names
                # the table, and which schema that is differs per group.
                content = resolve(path.read_text())
            except (UnicodeDecodeError, OSError):
                logger.warning("skill %s: skipped unreadable file %s", name, path.name)
                continue
            files[f"{SKILLS_MOUNT}{name}/{path.relative_to(root).as_posix()}"] = (
                create_file_data(content)
            )
    return files
