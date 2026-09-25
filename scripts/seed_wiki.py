#!/usr/bin/env python3
"""Upload the committed OKF seed bundle to the wiki Volume.

The seed exists so the `/wiki/` tier is reproducible without access to the real
OpenWiki: a trainee with the Jakarta credential can populate the wiki from the
repository and run the evaluation. It is also the worked example of the format
— trainees read it to see what a conformant concept looks like.

The bundle mirrors the Volume's two prefixes and is uploaded as it stands:

    raw/    the landing tree — files as people drop them, any format
    notes/  the wiki itself — OKF markdown and its indexes

`notes/` is also where the agent writes, so a re-seed can overwrite an agent
note that happens to share a seeded path. Seeded paths are the ones committed
here, and the digest check leaves anything unchanged alone.

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

SEED_DIR = Path(__file__).resolve().parent.parent / "wiki_seed"


def jakarta_client(profile: str | None = None) -> WorkspaceClient:
    """A client for the workspace holding the Volume.

    The same explicit-host, pinned-auth construction `agent_server.tools` uses,
    and for the same reason: left to its own credential chain the SDK picks up
    the ambient Databricks auth and sends a token for the wrong workspace.

    `profile` seeds under a CLI profile instead, for a workspace where the
    service principal does not exist yet — seeding is a person's job anyway.
    """
    if profile:
        return WorkspaceClient(profile=profile)

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


def is_document(path: Path) -> bool:
    """Whether a seed file belongs on the Volume at all.

    Hidden files are skipped. The seed is a directory on someone's laptop, so it
    collects what laptops leave lying around — `.DS_Store` on macOS, editor and
    VCS metadata elsewhere. Uploading those puts junk in a knowledge tier the
    agent lists and searches, and the agent has no way to tell an artefact from
    a document. Filtered here rather than in `.gitignore`, which keeps them out
    of the repository but not out of `rglob`.
    """
    return not any(part.startswith(".") for part in path.parts)


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
    ap.add_argument("--profile", help="seed under a CLI profile instead of the service principal")
    ap.add_argument("--volume", help="seed this Volume instead of DATABRICKS_WIKI_VOLUME")
    args = ap.parse_args()

    # `load_dotenv(override=True)` means `.env` beats the environment, so a
    # second Volume has to be named here rather than exported.
    volume = args.volume or os.environ.get("DATABRICKS_WIKI_VOLUME")
    if not volume:
        sys.exit("DATABRICKS_WIKI_VOLUME is not set. See .env.example.")
    if not SEED_DIR.is_dir():
        sys.exit(f"No seed bundle at {SEED_DIR}")

    base = volume.rstrip("/")
    files = sorted(
        p for p in SEED_DIR.rglob("*")
        if p.is_file() and is_document(p.relative_to(SEED_DIR))
    )
    if not files:
        sys.exit(f"Seed bundle at {SEED_DIR} is empty")

    w = jakarta_client(args.profile) if not args.dry_run else None
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


if __name__ == "__main__":
    main()
