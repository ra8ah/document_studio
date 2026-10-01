# Database: migrate to MongoDB Atlas, back up, restore

The backend reads `MONGO_URL` and `DB_NAME` from the environment. Both a local
`mongodb://localhost:27017` URL and an Atlas `mongodb+srv://...` URL work; pymongo ships
`dnspython` for SRV lookups. The client uses `maxPoolSize` (`MONGO_MAX_POOL_SIZE`, default 20),
`serverSelectionTimeoutMS` (`MONGO_SERVER_SELECTION_TIMEOUT_MS`, default 5000) and
`retryWrites=true`. `GET /api/health` pings the database: it returns 200
`{"status":"ok","database":"ok"}`, or 503 if the database is unreachable.

Indexes are created at every startup and are idempotent:
- `users.email` (unique)
- `documents.number` (unique)
- `documents.client_id`
- `documents.(status, type)`
- `documents.created_at` (descending)
- `documents.share_token` (unique, sparse)
- `documents.type`
- `clients.name`

Legacy `share_token: null` fields are removed first, because a sparse index still indexes
explicit nulls. If legacy data breaks a unique index (for example duplicate document numbers),
the backend still starts, and logs `index documents [('number', 1)]: ...` at ERROR level.

---

## 1. Create the Atlas database

1. On cloud.mongodb.com, create an **M0** cluster in a region close to your backend host.
2. **Database Access**: create two users:
   - `studio_app` with **readWrite** on `document_studio`. The backend uses this one.
   - `studio_backup` with **read** on `document_studio`. Backups use this one.
3. **Network Access**: add your backend host's outbound IPs. `0.0.0.0/0` only if the host has no
   static egress (Render/Railway free tiers); then rely on strong passwords.
4. **Connect → Drivers** gives the URI:
   `mongodb+srv://studio_app:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority&appName=document-studio`.
   URL-encode special characters in the password (`@` → `%40`, `:` → `%3A`, `/` → `%2F`).

## 2. Migrate the existing data (safe procedure)

The tool, `scripts/mongo_migrate.py` (needs `pip install pymongo`):
- only ever **reads** the source;
- **dry-runs by default**, so nothing is written without `--execute`;
- refuses a non-empty target unless you pass `--allow-nonempty` (that upserts by `_id`, so re-running is safe);
- copies BSON natively (ObjectId, dates, Int64, Decimal128 keep their types);
- verifies every `_id` after the copy and exits 1 on any mismatch;
- redacts passwords in its output.

```bash
# 0. stop writes: scale the old backend to 0 / stop it (or accept that later edits will not be copied)

# 1. safety net: a backup of the SOURCE first
python scripts/mongo_backup.py --uri "mongodb://localhost:27017" --db test_database backup --out backups/

# 2. dry run: prints per-collection counts on both sides, writes nothing
export TARGET_MONGO_URL='mongodb+srv://studio_app:...@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority'
python scripts/mongo_migrate.py --source-uri "mongodb://localhost:27017" --source-db test_database \
       --target-db document_studio --dry-run

# 3. copy and verify
python scripts/mongo_migrate.py --source-uri "mongodb://localhost:27017" --source-db test_database \
       --target-db document_studio --execute

# 4. point the backend at Atlas (MONGO_URL, DB_NAME=document_studio), deploy, check:
curl https://<backend-host>/api/health        # {"status":"ok","database":"ok"}
```

On startup, the backend creates the indexes, removes legacy `share_token: null` fields and seeds the
admin from `ADMIN_EMAIL`/`ADMIN_PASSWORD`. Then log in and spot-check a few documents, the dashboard
totals and a share link.

**Alternative with MongoDB Database Tools** (equivalent; Atlas M0 supports both tools):

```bash
mongodump  --uri="mongodb://localhost:27017/test_database" --archive=studio.archive --gzip
mongorestore --uri="$TARGET_MONGO_URL" --archive=studio.archive --gzip \
             --nsFrom='test_database.*' --nsTo='document_studio.*' --dryRun     # check first
mongorestore --uri="$TARGET_MONGO_URL" --archive=studio.archive --gzip \
             --nsFrom='test_database.*' --nsTo='document_studio.*'              # then for real
```

Don't use `--drop` against a database that already holds production data.

**Rollback:** the source is never modified. Point `MONGO_URL`/`DB_NAME` back at it and redeploy.

## 3. Scheduled backups (Atlas M0 has none)

`scripts/mongo_backup.py backup` writes `<db>-<UTC timestamp>/` containing one gzip
**canonical Extended JSON** file per collection (exact BSON types) and a `manifest.json` with
counts and SHA-256 checksums. It only reads from the database.

**Option A (recommended): GitHub Actions,** `.github/workflows/atlas-backup.yml`. Runs daily at
02:30 UTC and on demand ("Run workflow").
1. Repository → Settings → Secrets and variables → Actions:
   - secret `ATLAS_BACKUP_URI`: the **read-only** `studio_backup` user's URI
   - secret `BACKUP_PASSPHRASE`: a long random passphrase. Store it in your password manager;
     without it the backups can't be decrypted.
   - variable `ATLAS_DB_NAME` = `document_studio`
   - variable `ATLAS_BACKUP_ENABLED` = `true` (the job is skipped until this is set)
2. Atlas Network Access must allow GitHub's runners (`0.0.0.0/0`, or use a self-hosted runner).
3. Each run dumps, verifies checksums and counts, encrypts with AES-256 (gpg) and uploads an
   artifact kept for **30 days**. Keep the repository **private**.
4. Once a month, download one artifact and do a test restore (below) into a scratch database.

**Option B: any machine with cron** (keeps the newest 30):

```cron
30 2 * * *  cd /opt/studio && MONGO_URL='mongodb+srv://studio_backup:...' DB_NAME=document_studio \
            /usr/bin/python3 scripts/mongo_backup.py backup --out /var/backups/studio --keep 30 >> /var/log/studio-backup.log 2>&1
```

Copy `/var/backups/studio` off the machine (object storage with versioning, for example).

## 4. Restore

```bash
# from a GitHub artifact: unzip the download, then decrypt
gpg --decrypt document_studio-YYYYMMDDTHHMMSSZ.tar.gz.gpg | tar xzf -

python scripts/mongo_backup.py verify document_studio-YYYYMMDDTHHMMSSZ          # checksums + counts

# rehearse into a scratch database first (dry run, then execute)
python scripts/mongo_backup.py --uri "$ATLAS_APP_URI" restore document_studio-YYYYMMDDTHHMMSSZ --target-db studio_restore_test
python scripts/mongo_backup.py --uri "$ATLAS_APP_URI" restore document_studio-YYYYMMDDTHHMMSSZ --target-db studio_restore_test --execute

# real restore over production (replaces each backed-up collection):
#   stop the backend -> take a fresh backup of the current state -> restore with --drop -> start backend
python scripts/mongo_backup.py --uri "$ATLAS_APP_URI" restore document_studio-YYYYMMDDTHHMMSSZ \
       --target-db document_studio --execute --drop
```

Without `--drop`, a restore refuses non-empty collections. After a restore, start the backend:
it recreates the indexes. Restoring the `counters` collection keeps document numbering continuous.

### Verified here

The migration was tested against scratch databases with 1,202 documents carrying ObjectId,
datetime, Int64 and Decimal128 values. Results:
- the dry run wrote nothing;
- the copy verified every `_id`;
- a second run was refused (target not empty) and `--allow-nonempty` was idempotent;
- backup, verify and restore gave a **type-identical** round trip;
- passwords were redacted in the output.
