# Alembic Migration Baseline Plan

## Current State

As of May 2026 the repository has **41 migration files** covering schema history
from the initial schema creation (`20260307_0001`) through the most recent
revision (`20260501_0041_drop_company_last_checked_columns`).

The deployment runbook already enforces migration safety via
`scripts/check_migration_safety.py` (run automatically inside the backend image
before `alembic upgrade head`).  That script blocks multiple heads, missing
downgrade stubs, and raw destructive DDL executed through `op.execute`.

## When to Squash

A squash is worth considering when **all** of the following are true:

- The cumulative migration chain is slowing fresh-install time noticeably
  (rule of thumb: more than ~100 revisions, or any single revision takes
  multiple seconds on a cold schema).
- Every active deployment has already applied the current head
  (`alembic current` returns the latest revision hash on every instance).
- A maintenance window is available that can accommodate a coordinated cutover
  of all running instances.
- A tested database backup and restore procedure exists and has been rehearsed
  recently (see `docs/postgres-backup-restore.md`).

With 41 migrations the current chain does **not** yet meet the size threshold.
Re-evaluate if the chain grows beyond ~80–100 revisions, or if a fresh install
starts taking more than a few seconds on `alembic upgrade head`.

## How to Create a Baseline Safely

When the time does come, the procedure is:

### 1. Confirm a stable head

```bash
alembic current        # every active instance must show the same revision
alembic heads          # must show exactly one head
```

All deployed environments must be fully migrated before proceeding.

### 2. Capture the current schema as SQL

```bash
alembic upgrade head --sql > schema_snapshot_$(date +%Y%m%d).sql
```

Keep this file for reference.  It describes the schema state the new baseline
revision must reproduce.

### 3. Create a new baseline revision

Generate a blank revision that becomes the new root:

```bash
alembic revision --rev-id baseline_v1 -m "squash_baseline_v1"
```

Edit the generated file so that `upgrade()` creates the full schema from
scratch (using the snapshot SQL as a guide) and `downgrade()` drops everything
cleanly or raises `NotImplementedError` if a full tear-down is unacceptable.

Set the `down_revision` to `None` so it has no parent.

### 4. Preserve old revision files as archive

Do **not** delete the old migration files immediately.  Move them to
`alembic/versions/archive/` and update `alembic.ini` to include that
directory (or simply leave them in place).  Keeping them means historical
`git blame` and rollback reasoning remain intact.

### 5. Stamp existing deployments — do not re-run

On every existing deployment, stamp the database to the new baseline without
actually running the upgrade:

```bash
alembic stamp baseline_v1
```

This records that the database is already at the new baseline revision without
touching any schema.  New deployments will run the baseline migration from
scratch; existing deployments skip it via the stamp.

### 6. Validate

```bash
alembic current          # should show baseline_v1
alembic check            # should report no pending migrations
python scripts/check_migration_safety.py
```

Run the full test suite and the deployment verification script
(`scripts/verify_deployment_compat.py`) against a staging environment before
touching production.

## How Existing Deployments Continue from the Current Head

The stamp step above is the key.  After stamping, `alembic upgrade head` is a
no-op on any instance that was already at the pre-squash head.  Only fresh
installs will execute the baseline migration, which builds the full schema from
scratch.

If new revisions are added after the baseline, they chain normally from
`baseline_v1` as their `down_revision`.

## Rollback Considerations

- **Before squashing**: the existing migration chain already has downgrade stubs
  enforced by the safety guard.  Rolling back to a prior revision uses the
  normal `alembic downgrade <target>` path.

- **After squashing**: the baseline revision's `downgrade()` typically performs
  a full schema drop, which is destructive.  Prefer restoring from a
  pre-squash database backup rather than running `alembic downgrade` past the
  baseline.  This is consistent with the runbook's existing guidance to always
  restore from backup rather than scripting ad-hoc downgrade steps during an
  incident.

- **Rollback window**: keep the pre-squash database backup available for at
  least one release cycle after the baseline deploy.

## What Not to Do

- Do not delete old migration files from version control until the baseline has
  been validated in production for at least one release cycle.
- Do not squash while any instance is mid-migration or running an older image
  that has not yet applied the current head.
- Do not rewrite `down_revision` in existing files; that corrupts history for
  environments that have not yet been stamped.
