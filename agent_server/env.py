"""Reading configuration out of the environment, tolerantly.

Every value this app is configured with arrives as an environment variable, and
several arrive from a Databricks Apps **secret resource** — `value_from` in
`databricks.yml`, backed by a secret scope someone populated by hand. A secret
written with `databricks secrets put-secret` from a file, an editor, or a copied
terminal line very often carries a trailing newline, and nothing between that
scope and this process trims it.

**The failure it produces is opaque.** A client secret with `\\n` on the end is
not a malformed request; it is a wrong password. The OAuth endpoint answers
`invalid_client: Client authentication failed`, which reads as "the credential
is revoked" and sends you to look at the service principal rather than at the
bytes. The same goes for a host with a trailing space, which yields a DNS
failure naming a host that looks correct in the log.

So values are stripped on the way in, and a variable that needed stripping is
reported once — the sanitising fixes this run, and the log line is what stops
the misconfiguration living in the scope forever. **Names are logged, never
values**: half of these are credentials.

Whitespace-only is treated as absent. `app.yaml` and `databricks.yml` can both
declare a variable with no value, which arrives as `""`; every caller here
already treats empty as unset, so a blank and a space should not differ.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Reported once per variable per process. Re-reading a value on every request
# is deliberate elsewhere (see `trace_config`), and a warning per request for a
# condition that cannot change mid-process is noise that trains people to
# ignore the log.
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
