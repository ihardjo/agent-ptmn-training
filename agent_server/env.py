"""Reading configuration out of the environment, tolerantly.

Values are stripped on the way in, because a secret saved with a trailing
newline is rejected downstream as a wrong credential rather than a malformed
one. The second half derives everything that differs between the eight workshop
instances from one variable, `WORKSHOP_GROUP`.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Once per variable per process: the condition cannot change mid-process, and a
# warning per request trains people to ignore the log.
_REPORTED: set[str] = set()


def env(name: str, default: str | None = None) -> str | None:
    """The variable, stripped, or `default` when unset or blank."""
    raw = os.environ.get(name)
    if raw is None:
        return default

    value = raw.strip()
    if value != raw and name not in _REPORTED:
        _REPORTED.add(name)
        logger.warning(
            "%s had surrounding whitespace, which was stripped. This run is fine, "
            "but the stored value is not — a trailing newline in a secret reads "
            "downstream as a wrong credential, not as a malformed one. Re-save it.",
            name,
        )
    return value or default


# ── which group this instance is ─────────────────────────────────────────────
#
# Eight instances run side by side, one per branch `group-0` … `group-7`, and
# `WORKSHOP_GROUP=group-0` points one at that group's data.

# Unset resolves to `default` and logs what it resolved to, since pointing at
# the wrong group is otherwise silent.

CATALOG = "workshop_ai_platform"
DEFAULT_GROUP = "default"
TABLE_NAME = "sdlc_tickets"
VOLUME_NAME = "agent_wiki"

# Doubled braces so a single `{` in a SQL snippet is not mistaken for one, and
# no angle brackets so `check-skills`'s XML-tag rule does not see a tag.
TABLE_PLACEHOLDER = "{{TABLE}}"

_GROUP_REPORTED = False


def group() -> str:
    """The configured group, in the hyphenated form the app name uses."""
    return env("WORKSHOP_GROUP") or DEFAULT_GROUP


def schema() -> str:
    """The Unity Catalog schema this instance reads, reported once.

    Hyphens become underscores. Accepting either form is deliberate: a value
    written `group_0` by hand still resolves, rather than producing a schema
    that does not exist and a first query that fails.
    """
    global _GROUP_REPORTED
    name = group().replace("-", "_")
    if not _GROUP_REPORTED:
        _GROUP_REPORTED = True
        logger.info(
            "WORKSHOP_GROUP %r — schema %s, table %s, volume %s",
            group(), name, table(name), volume(name),
        )
    return name


def table(name: str | None = None) -> str:
    """The fully qualified ticket table for a schema."""
    return f"{CATALOG}.{name or group().replace('-', '_')}.{TABLE_NAME}"


def volume(name: str | None = None) -> str:
    """The wiki Volume path for a schema."""
    return f"/Volumes/{CATALOG}/{name or group().replace('-', '_')}/{VOLUME_NAME}"


def resolve(text: str) -> str:
    """Markdown with `{{TABLE}}` replaced by this instance's table.

    Applied on read rather than on disk, so one checkout serves every group.
    """
    if TABLE_PLACEHOLDER not in text:
        return text
    return text.replace(TABLE_PLACEHOLDER, table(schema()))
