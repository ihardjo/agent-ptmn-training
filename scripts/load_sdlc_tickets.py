"""Create and load `workshop_ai_platform.example.sdlc_tickets` in Jakarta.

Committed alongside the generator so the table is reproducible end to end:
same seed in, same rows out, same magnitudes verifiable.

Two things about the execution path are worth knowing before changing this:

- **The identity matters.** DDL here needs table ownership, which the agent's
  service principal deliberately does not hold. Run it under a profile whose
  user owns the schema's tables (`jakarta-workshop`), not under the app's
  credentials.
- **A failed statement is not an API error.** The statement API reports
  transport success while carrying the failure inside the payload, so every
  call checks `status.state` rather than trusting the absence of an exception.
  This is the same trap the agent itself has to handle.

Rows are loaded as batched multi-row INSERTs, which needs no Volume and no
cluster — only a SQL warehouse.

Usage:
    # first time, table does not exist
    uv run python -m scripts.load_sdlc_tickets --create --load --verify

    # regenerate an existing table in place (the destructive one)
    uv run python -m scripts.load_sdlc_tickets --replace --load --verify
"""

from __future__ import annotations

import argparse
import pathlib

from databricks.sdk import WorkspaceClient

from scripts.generate_sdlc_tickets import (
    ROWS,
    SEED,
    create_table_sql,
    generate,
    insert_batches,
)

DEFAULT_PROFILE = "jakarta-workshop"
DEFAULT_WAREHOUSE = "f623235257888af1"
DEFAULT_TABLE = "workshop_ai_platform.example.sdlc_tickets"
VERIFY_SQL = pathlib.Path(__file__).parent / "sdlc_tickets_verify.sql"

TABLE_COMMENT = (
    "Workshop training data for the Pertamina AI platform agent course. "
    "Generated deterministically by scripts/generate_sdlc_tickets.py. "
    "NOTE: this table contains intentional data-quality defects (impossible "
    "timestamps, cross-field inconsistencies, and inconsistent name spellings) "
    "planted so that validation and stewardship work has something real to "
    "find. They are by design, not a load failure -- see the generator and the "
    "replace-ticket-table-with-sdlc-schema change for the documented counts."
)


def run(client: WorkspaceClient, warehouse: str, statement: str) -> list[list]:
    """Execute one statement, raising on a failure carried inside the payload."""
    resp = client.statement_execution.execute_statement(
        warehouse_id=warehouse, statement=statement, wait_timeout="50s"
    )
    state = resp.status.state.value if resp.status and resp.status.state else "UNKNOWN"
    if state != "SUCCEEDED":
        message = resp.status.error.message if resp.status and resp.status.error else state
        raise RuntimeError(f"statement {state}: {message}\n---\n{statement[:400]}")
    return (resp.result.data_array if resp.result else None) or []


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--warehouse", default=DEFAULT_WAREHOUSE)
    ap.add_argument("--table", default=DEFAULT_TABLE)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--rows", type=int, default=ROWS)
    ap.add_argument("--batch", type=int, default=200)
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--replace", action="store_true",
                    help="regenerate in place: CREATE OR REPLACE TABLE, then load")
    ap.add_argument("--load", action="store_true")
    ap.add_argument("--allow-append", action="store_true",
                    help="permit --load into a table that already has rows")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    client = WorkspaceClient(profile=args.profile)
    who = run(client, args.warehouse, "SELECT current_user()")[0][0]
    print(f"connected as {who} via profile {args.profile!r}")

    if args.create or args.replace:
        run(client, args.warehouse,
            create_table_sql(args.table, replace=args.replace))
        run(client, args.warehouse,
            f"COMMENT ON TABLE {args.table} IS '{TABLE_COMMENT}'")
        verb = "replaced" if args.replace else "created"
        print(f"{verb} {args.table} with a comment recording the planted defects")

    if args.load:
        # Rows are appended, never upserted, so loading into a table that
        # already holds a generation doubles it — 8,000 rows, every planted
        # magnitude halved, and nothing errors. That is a silently wrong table,
        # which is the one failure this file exists to prevent, so it has to be
        # asked for explicitly. `--replace` emptied the table a moment ago and
        # is therefore exempt.
        if not (args.replace or args.allow_append):
            existing = int(run(
                client, args.warehouse, f"SELECT COUNT(*) FROM {args.table}")[0][0])
            if existing:
                ap.error(
                    f"{args.table} already holds {existing} row(s) and --load only "
                    "appends. Pass --replace to regenerate it in place (atomic, and "
                    "the prior version stays readable with VERSION AS OF), or "
                    "--allow-append if doubling the table is genuinely intended."
                )
        rows = generate(args.seed, args.rows)
        batches = list(insert_batches(rows, args.table, args.batch))
        for i, statement in enumerate(batches, 1):
            run(client, args.warehouse, statement)
            print(f"  loaded batch {i}/{len(batches)}", end="\r", flush=True)
        count = run(client, args.warehouse, f"SELECT COUNT(*) FROM {args.table}")[0][0]
        print(f"\nloaded {len(rows)} rows; table now reports {count}")

    if args.verify:
        blocks = [b.strip() for b in VERIFY_SQL.read_text().split("-- @@") if b.strip()]
        for block in blocks:
            label, _, body = block.partition("\n")
            statement = "\n".join(
                line for line in body.splitlines() if not line.strip().startswith("--")
            ).strip().rstrip(";")
            if not statement:
                continue
            print(f"\n── {label.strip()}")
            for row in run(client, args.warehouse, statement):
                print("   " + " | ".join("NULL" if v is None else str(v) for v in row))

    if not (args.create or args.replace or args.load or args.verify):
        ap.error("nothing to do: pass --create/--replace, --load, and/or --verify")


if __name__ == "__main__":
    main()
