#!/usr/bin/env python3
"""Check the wiki bundle against OKF v0.2 conformance (§11).

Two things are worth checking and they are not the same. The committed seed is
checked on every test run; the **Volume** is not, and it is the one that drifts
— because the agent writes to it. A note that lands without frontmatter breaks
the bundle for every later reader, so this is the command that says so.

    uv run check-okf              # the committed seed and, if configured, the Volume
    uv run check-okf --seed-only  # no workspace needed

Exits non-zero when any document violates one of the three hard rules.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=REPO_ROOT / ".env", override=True)

SEED_DIR = REPO_ROOT / "wiki_seed" / "raw"

# Each tier is its own bundle, checked separately. They are not one bundle with
# two subdirectories, for two reasons: `/wiki/` itself is not a route, so a
# shared bundle root would have nowhere reachable to live; and the seed's
# cross-links are bundle-relative (`/policies/...`), which only resolves if the
# tier is the root. §3 allows a bundle to be a subdirectory, so two is fine.
SUBDIRS = ("raw", "notes")


def seed_documents() -> dict[str, str]:
    """The seed bundle, keyed relative to its own root."""
    return {
        p.relative_to(SEED_DIR).as_posix(): p.read_text()
        for p in sorted(SEED_DIR.rglob("*.md"))
    }


def volume_documents() -> dict[str, dict[str, str]] | None:
    """Each tier's documents, keyed relative to that tier's own root.

    Returns None when the Volume is not reachable, which is a supported state
    rather than a failure.
    """
    from databricks.sdk import WorkspaceClient

    volume = os.environ.get("DATABRICKS_WIKI_VOLUME")
    host = os.environ.get("DATABRICKS_JAKARTA_HOST")
    client_id = os.environ.get("DATABRICKS_JAKARTA_CLIENT_ID")
    client_secret = os.environ.get("DATABRICKS_JAKARTA_CLIENT_SECRET")
    if not (volume and host and client_id and client_secret):
        return None

    w = WorkspaceClient(
        host=host, client_id=client_id, client_secret=client_secret, auth_type="oauth-m2m"
    )
    bundles: dict[str, dict[str, str]] = {}
    for subdir in SUBDIRS:
        base = f"{volume.rstrip('/')}/{subdir}"
        documents: dict[str, str] = {}
        pending = [base]
        while pending:
            current = pending.pop()
            try:
                entries = list(w.files.list_directory_contents(current))
            except Exception as exc:
                print(f"  ! could not list {current}: {exc}", file=sys.stderr)
                continue
            for e in entries:
                if not e.path:
                    continue
                if e.is_directory:
                    pending.append(e.path)
                elif e.path.endswith(".md"):
                    documents[e.path[len(base) + 1 :]] = (
                        w.files.download(e.path).contents.read().decode("utf-8")
                    )
        bundles[subdir] = documents
    return bundles


def report(label: str, documents: dict[str, str]) -> bool:
    from agent_server.okf import conformance_errors, is_reserved

    concepts = sum(1 for p in documents if not is_reserved(p))
    errors = conformance_errors(documents)
    print(f"\n{label}: {len(documents)} document(s), {concepts} concept(s)")
    if not errors:
        print("  conformant with OKF v0.2")
        return True
    for e in errors:
        print(f"  FAIL {e}")
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed-only", action="store_true", help="skip the Volume")
    args = ap.parse_args()

    if not SEED_DIR.is_dir():
        sys.exit(f"No seed bundle at {SEED_DIR}")
    ok = report(f"seed ({SEED_DIR.relative_to(REPO_ROOT)})", seed_documents())

    if not args.seed_only:
        bundles = volume_documents()
        if bundles is None:
            print(
                "\nVolume: not configured — set DATABRICKS_WIKI_VOLUME and "
                "DATABRICKS_JAKARTA_* to check it."
            )
        else:
            volume = os.environ["DATABRICKS_WIKI_VOLUME"].rstrip("/")
            for subdir, documents in bundles.items():
                if not documents:
                    print(f"\n{volume}/{subdir}: empty")
                    continue
                ok &= report(f"{volume}/{subdir}", documents)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
