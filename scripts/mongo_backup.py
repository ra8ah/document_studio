#!/usr/bin/env python3
"""
Logical backup / restore for MongoDB (built for Atlas M0, which has no automated backups).

  Backup  (read-only on the database):
    python scripts/mongo_backup.py backup --out backups/ [--keep 30]
      -> backups/<db>-<UTC timestamp>/<collection>.jsonl.gz  + manifest.json (counts, sha256)
         --keep N deletes all but the newest N backups of that database in --out.

  Restore (dry run by default):
    python scripts/mongo_backup.py restore backups/<db>-<ts> --target-db document_studio
    python scripts/mongo_backup.py restore backups/<db>-<ts> --target-db document_studio --execute [--drop]
      Without --drop the target collections must be empty. With --drop each collection in the
      backup is replaced (other collections untouched). Counts are verified against the manifest.

  Verify a backup's files against its manifest (no database needed):
    python scripts/mongo_backup.py verify backups/<db>-<ts>

Connection: --uri / --db, else MONGO_URL / DB_NAME from the environment or backend/.env.
Format: MongoDB Extended JSON v2 *canonical* (one document per line, gzip). This keeps exact
BSON types (ObjectId, dates, Int64, Decimal128), so a restore is type-identical.
Requires: pip install pymongo
"""
import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from bson import json_util
from bson.json_util import CANONICAL_JSON_OPTIONS
from pymongo import MongoClient

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


def redact(uri):
    return re.sub(r"//([^:/@]+):([^@]+)@", r"//\1:***@", uri or "")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def connect(uri, dbname):
    db = MongoClient(uri, serverSelectionTimeoutMS=10000)[dbname]
    db.command("ping")
    return db


def do_backup(a):
    db = connect(a.uri, a.db)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = Path(a.out) / f"{a.db}-{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    manifest = {"db": a.db, "created_utc": stamp, "format": "extjson-canonical-jsonl-gz", "collections": {}}
    for name in sorted(n for n in db.list_collection_names() if not n.startswith("system.")):
        f = out / f"{name}.jsonl.gz"
        n = 0
        with gzip.open(f, "wt", encoding="utf-8") as fh:
            for doc in db[name].find({}).sort("_id", 1):
                fh.write(json_util.dumps(doc, json_options=CANONICAL_JSON_OPTIONS) + "\n")
                n += 1
        manifest["collections"][name] = {"count": n, "file": f.name, "sha256": sha256(f)}
        print(f"  {name:<20} {n} docs")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"backup written: {out}")
    if a.keep:
        olds = sorted(p for p in Path(a.out).glob(f"{a.db}-*") if p.is_dir() and (p / "manifest.json").exists())
        for p in olds[:-a.keep]:
            shutil.rmtree(p)
            print(f"  pruned old backup {p.name}")
    return 0


def load_manifest(path):
    m = json.loads((Path(path) / "manifest.json").read_text())
    for name, info in m["collections"].items():
        f = Path(path) / info["file"]
        if sha256(f) != info["sha256"]:
            raise SystemExit(f"checksum mismatch for {f} - backup is corrupt")
    return m


def do_verify(a):
    m = load_manifest(a.path)
    total = 0
    for name, info in m["collections"].items():
        with gzip.open(Path(a.path) / info["file"], "rt", encoding="utf-8") as fh:
            n = sum(1 for line in fh if line.strip())
        ok = n == info["count"]
        total += n
        print(f"  {name:<20} {n} docs {'ok' if ok else 'COUNT MISMATCH'}")
        if not ok:
            return 1
    print(f"backup OK: {len(m['collections'])} collections, {total} documents, checksums match")
    return 0


def do_restore(a):
    m = load_manifest(a.path)
    db = connect(a.uri, a.target_db)
    print(f"target: {redact(a.uri)}  db={a.target_db}")
    print(f"mode:   {'EXECUTE' + (' (drop & replace)' if a.drop else '') if a.execute else 'DRY RUN (nothing will be written)'}\n")
    blocked = []
    for name, info in m["collections"].items():
        existing = db[name].count_documents({})
        if existing and not a.drop:
            blocked.append(name)
        print(f"  {name:<20} backup={info['count']:<7} target_now={existing:<7}"
              f"{' BLOCKED (not empty; use --drop)' if name in blocked else ''}")
    if blocked:
        print("\nrefusing: target collections not empty: " + ", ".join(blocked))
        return 1
    if not a.execute:
        print("\ndry run complete - re-run with --execute to restore")
        return 0
    bad = False
    for name, info in m["collections"].items():
        if a.drop:
            db[name].drop()
        batch = []
        with gzip.open(Path(a.path) / info["file"], "rt", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    batch.append(json_util.loads(line))
                if len(batch) >= 500:
                    db[name].insert_many(batch, ordered=False)
                    batch = []
        if batch:
            db[name].insert_many(batch, ordered=False)
        n = db[name].count_documents({})
        bad |= n != info["count"]
        print(f"  {name:<20} restored={n} {'ok' if n == info['count'] else 'COUNT MISMATCH'}")
    print("\nrestore " + ("FAILED verification" if bad else "complete and verified") +
          " - restart the backend so it (re)creates indexes")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uri", default=env_default("MONGO_URL"))
    ap.add_argument("--db", default=env_default("DB_NAME"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--out", default="backups")
    b.add_argument("--keep", type=int, default=0, help="keep only the newest N backups (0 = keep all)")
    v = sub.add_parser("verify")
    v.add_argument("path")
    r = sub.add_parser("restore")
    r.add_argument("path")
    r.add_argument("--target-db", required=True)
    r.add_argument("--drop", action="store_true")
    g = r.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="report only (default)")
    g.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    if a.cmd != "verify" and not a.uri:
        ap.error("--uri (or MONGO_URL) is required")
    if a.cmd == "backup" and not a.db:
        ap.error("--db (or DB_NAME) is required")
    return {"backup": do_backup, "verify": do_verify, "restore": do_restore}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
