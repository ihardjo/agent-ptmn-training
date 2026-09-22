#!/usr/bin/env python3
"""Upload the committed OKF seed bundle to the wiki Volume.

The seed exists so the `/wiki/` tier is reproducible without access to the real
OpenWiki: a trainee with the Jakarta credential can populate the source tree
from the repository and run the evaluation. It is also the worked example of
the format — trainees read it to see what a conformant concept looks like.

Only `raw/` is written. `notes/` is the agent's, and a re-seed must not
touch it: the whole point of the provenance split is that refreshing source
content cannot destroy what the agent wrote.

    uv run seed-wiki            # upload, skipping unchanged files
    uv run seed-wiki --force    # re-upload everything
    uv run seed-wiki --dry-run  # say what would happen
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import sys
from pathlib import Path

from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

SEED_DIR = Path(__file__).resolve().parent.parent / "wiki_seed" / "raw"
SOURCE_SUBDIR = "raw"


def jakarta_client() -> WorkspaceClient:
    """A client for the workspace holding the Volume.

    The same explicit-host, pinned-auth construction `agent_server.tools` uses,
    and for the same reason: left to its own credential chain the SDK picks up
    the ambient Databricks auth and sends a token for the wrong workspace.
    """
    host = os.environ.get("DATABRICKS_JAKARTA_HOST")
    client_id = os.environ.get("DATABRICKS_JAKARTA_CLIENT_ID")
    client_secret = os.environ.get("DATABRICKS_JAKARTA_CLIENT_SECRET")
    if not (host and client_id and client_secret):
        sys.exit(
            "DATABRICKS_JAKARTA_HOST / _CLIENT_ID / _CLIENT_SECRET must be set "
            "to seed the wiki. See .env.example."
        )
    return WorkspaceClient(
        host=host, client_id=client_id, client_secret=client_secret, auth_type="oauth-m2m"
    )


def remote_digest(w: WorkspaceClient, path: str) -> str | None:
    """The SHA-256 of a file already on the Volume, or None if it is not there.

    Compared rather than trusting a timestamp: the Files API reports a
    modification time set by the upload, so every re-seed would look newer than
    the local file and nothing would ever be skipped.
    """
    try:
        return hashlib.sha256(w.files.download(path).contents.read()).hexdigest()
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-upload unchanged files")
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    args = ap.parse_args()

    volume = os.environ.get("DATABRICKS_WIKI_VOLUME")
    if not volume:
        sys.exit("DATABRICKS_WIKI_VOLUME is not set. See .env.example.")
    if not SEED_DIR.is_dir():
        sys.exit(f"No seed bundle at {SEED_DIR}")

    base = f"{volume.rstrip('/')}/{SOURCE_SUBDIR}"
    files = sorted(p for p in SEED_DIR.rglob("*") if p.is_file())
    if not files:
        sys.exit(f"Seed bundle at {SEED_DIR} is empty")

    w = jakarta_client() if not args.dry_run else None
    uploaded = skipped = 0

    for local in files:
        rel = local.relative_to(SEED_DIR).as_posix()
        remote = f"{base}/{rel}"
        body = local.read_bytes()

        if args.dry_run:
            print(f"  would upload  {remote}")
            uploaded += 1
            continue

        if not args.force and remote_digest(w, remote) == hashlib.sha256(body).hexdigest():
            print(f"  unchanged     {remote}")
            skipped += 1
            continue

        w.files.upload(remote, io.BytesIO(body), overwrite=True)
        print(f"  uploaded      {remote}")
        uploaded += 1

    verb = "would upload" if args.dry_run else "uploaded"
    print(f"\n{verb} {uploaded}, skipped {skipped} — under {base}/")
    print(f"{volume.rstrip('/')}/notes/ was not touched.")


if __name__ == "__main__":
    main()
