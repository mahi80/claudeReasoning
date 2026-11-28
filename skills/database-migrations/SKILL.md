---
name: database-migrations
description: Plan and code safe schema changes, bounded backfills and expand-contract database migrations with data-preservation checks.
source: https://github.com/affaan-m/ECC/tree/4adeee6732a12d1540f49a4d50a38ce8c97f9a53/skills/database-migrations
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Database migrations

Inspect the database engine/version, migration framework, schema size and running
application versions. Generate migration code first. Applying migrations, accessing
live databases, restoring backups, resetting state or running down migrations
requires specific operator authorization; this skill grants none.

## Expand, migrate, contract
1. Add compatible columns/tables/indexes without removing old contracts.
2. Deploy code that tolerates both forms; dual-write only when needed and with
   an explicit consistency strategy.
3. Backfill in bounded batches and verify parity and constraints.
4. Switch reads after evidence confirms completeness.
5. Remove obsolete structures only after old readers/writers are gone and the
   destructive step is approved separately.

## DDL and locks
- Identify statements that rewrite a table, scan rows or take exclusive locks.
  Choose engine-supported online/concurrent mechanisms where appropriate.
- For PostgreSQL, set a finite lock_timeout and a realistic statement_timeout.
  CREATE INDEX CONCURRENTLY cannot run inside a transaction block; use the
  framework's supported non-transactional migration mode for that operation.
- For large constraint changes, consider NOT VALID then VALIDATE CONSTRAINT where
  supported. Check actual engine semantics rather than assuming universal safety.
- Preserve data and existing indexes until replacements are verified. A reversible
  schema command is not necessarily a reversible data transformation.

## Backfill without infinite loops
Use a stable keyset cursor/checkpoint and fixed batch bounds. Advance the cursor to
the last processed key even for rows that cannot be transformed. Do not repeatedly
select rows where the destination is NULL if the source can itself be NULL or empty;
filter eligible sources and record unresolved rows explicitly. Make retries safe,
bound work and avoid one long transaction or locks held across network calls.

## Verification
Use a disposable local database when available and approved; never an accidental
live connection. Check migration up behavior, old/new application compatibility,
row counts, nulls, uniqueness and representative values. A rollback test belongs
only in disposable state: never run reset, force or destructive down on user data.
Before live application, require a reviewed plan, backup/restore evidence, expected
lock/runtime impact and a data-preserving recovery strategy. Report tests not run.
