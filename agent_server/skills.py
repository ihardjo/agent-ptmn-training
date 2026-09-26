"""The skill menu the model is offered, and how it reaches the model.

The repository's `skills/` tree is the catalogue; `SELECTED_SKILLS` is the
configuration. They are separate so that adding a skill to the repository does
not silently put it in front of the model.
"""

from pathlib import Path
from typing import Any

from deepagents.backends.utils import create_file_data

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
SKILLS_MOUNT = "/skills/"

## TODO 4: Skill Selection — uncomment the skills to put in front of the model.
SELECTED_SKILLS = (
    # "auditing-data-quality",
    # "checking-due-dates",
    # "computing-target-adherence",
    # "measuring-sprint-velocity",
    # "splitting-planned-unplanned-work",
    # "summarising-root-causes",
    # "escalating-breaches",
    # "explaining-ticket-history",
    # "formatting-service-review",
    # "ranking-squad-performance",
)

def skill_files() -> dict[str, Any]:
    return {
        f"{SKILLS_MOUNT}{name}/SKILL.md": create_file_data((SKILLS_DIR / name / "SKILL.md").read_text())
        for name in SELECTED_SKILLS
    }
