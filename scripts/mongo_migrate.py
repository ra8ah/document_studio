#!/usr/bin/env python3
"""
Copy a MongoDB database (e.g. the local/Emergent one) into MongoDB Atlas, safely.

    # 1) dry run (default): connects to both sides, prints what WOULD be copied, writes nothing
    python scripts/mongo_migrate.py --target-uri "$ATLAS_URI" --target-db document_studio

    # 2) copy for real
    python scripts/mongo_migrate.py --target-uri "$ATLAS_URI" --target-db document_studio --execute

Source defaults to MONGO_URL / DB_NAME from the environment or backend/.env.
Safety:
  * nothing is written without --execute (--dry-run is accepted and is the default);
  * the target must be empty unless --allow-nonempty (then documents are upserted by _id,
    so re-running is idempotent; existing target-only documents are left alone);
  * the source is only ever read;
  * BSON is copied natively (ObjectId, dates, numbers keep their exact types);
  * per-collection counts are verified after copying; exit code 1 on any mismatch;
  * connection strings are printed with the password redacted.
Indexes are not copied: the backend creates them on startup (idempotent).
Requires: pip install pymongo  (dnspython comes with it, for mongodb+srv:// URIs)
"""
import argparse
import os
import re
import sys
from pathlib import Path

from pymongo import MongoClient, ReplaceOne

ROOT = Path(__file__).resolve().parent.parent


def env_default(key):
    if os.environ.get(key):
        return os.environ[key]
    f = ROOT / "backend" / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def redact(uri: str) -> str:
    return re.sub(r"//([^:/@]+):([^@]+)@", r"//\1:***@", uri or "")


def collections(db, only):
    names = sorted(n for n in db.list_collection_names() if not n.startswith("system."))
    return [n for n in names if not only or n in only]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-uri", default=env_default("MONGO_URL"))
    ap.add_argument("--source-db", default=env_default("DB_NAME"))
    ap.add_argument("--target-uri", default=os.environ.get("TARGET_MONGO_URL"), help="or env TARGET_MONGO_URL")
    ap.add_argument("--target-db", default=os.environ.get("TARGET_DB_NAME"), help="or env TARGET_DB_NAME")
    ap.add_argument("--collections", nargs="*", help="only these collections (default: all)")
    ap.add_argument("--batch-size", type=int, default=500)
    ap.add_argument("--allow-nonempty", action="store_true", help="upsert into a target that already has data")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report only (default)")
    mode.add_argument("--execute", action="store_true", help="actually copy")
    a = ap.parse_args()

    for k in ("source_uri", "source_db", "target_uri", "target_db"):
        if not getattr(a, k):
            ap.error(f"--{k.replace('_', '-')} is required")
    if a.source_uri == a.target_uri and a.source_db == a.target_db:
        ap.error("source and target are the same database")

    src = MongoClient(a.source_uri, serverSelectionTimeoutMS=10000)[a.source_db]
    dst = MongoClient(a.target_uri, serverSelectionTimeoutMS=10000, retryWrites=True)[a.target_db]
    src.command("ping")
    dst.command("ping")
    print(f"source: {redact(a.source_uri)}  db={a.source_db}")
    print(f"target: {redact(a.target_uri)}  db={a.target_db}")
    print(f"mode:   {'EXECUTE' if a.execute else 'DRY RUN (nothing will be written)'}\n")

    names = collections(src, a.collections)
    plan, blocked = [], []
    for n in names:
        s_count = src[n].estimated_document_count() if not a.collections else src[n].count_documents({})
        t_count = dst[n].count_documents({})
        plan.append((n, s_count, t_count))
        if t_count and not a.allow_nonempty:
            blocked.append(n)
        print(f"  {n:<20} source={s_count:<7} target={t_count:<7} "
              f"{'BLOCKED (target not empty)' if n in blocked else ('upsert' if t_count else 'insert')}")

    if blocked:
        print(f"\nrefusing: target collections not empty: {', '.join(blocked)} (use --allow-nonempty to upsert)")
        return 1
    if not a.execute:
        print("\ndry run complete - re-run with --execute to copy")
        return 0

    failed = False
    for n, s_count, _ in plan:
        copied, batch = 0, []
        for doc in src[n].find({}, no_cursor_timeout=False).batch_size(a.batch_size):
            batch.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
            if len(batch) >= a.batch_size:
                dst[n].bulk_write(batch, ordered=False)
                copied += len(batch)
                batch = []
        if batch:
            dst[n].bulk_write(batch, ordered=False)
            copied += len(batch)
        # verify: every source _id exists in the target
        src_ids = {d["_id"] for d in src[n].find({}, {"_id": 1})}
        dst_ids = {d["_id"] for d in dst[n].find({"_id": {"$in": list(src_ids)}}, {"_id": 1})} if src_ids else set()
        ok = src_ids == dst_ids
        failed |= not ok
        print(f"  {n:<20} copied={copied:<7} verified={'yes' if ok else 'NO - missing ' + str(len(src_ids - dst_ids))}")
    print("\nmigration " + ("FAILED verification" if failed else "complete and verified"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
