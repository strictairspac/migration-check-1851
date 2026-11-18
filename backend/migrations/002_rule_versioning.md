# Schema v2 — rule versions, dry runs, one-shot activation

Added tables
- `mapping_versions`: immutable rule-set revisions per mapping. `state` is
  `active` / `candidate` / `archived` / `withdrawn`. A partial unique index
  `ux_mapping_versions_active` allows at most one `active` row per mapping.
  `batch_id` + `batch_revision` record the batch revision a version was
  confirmed against; NULL `batch_revision` marks the baseline, which applies
  to every revision of the batch.
- `dry_runs`: frozen old-vs-new comparison evidence (batch revision and
  digest, both rule digests, per-row outcomes). Contains no target or backup
  data and creates no queue entry.
- `mapping_activations`: unique `dry_run_id` receipt. Retrying a confirmation
  returns the existing receipt instead of enabling the candidate twice.

Added columns
- `batches.revision` (default 1): bumped on every real edit, including an
  edit that later reverts, so a stale dry run cannot be revived.
- `mappings.active_version_id`: pointer to the in-use version.
  `mappings.rules`/`chunk_size` mirror it for older snapshots.
- `runs.mapping_version_id`: version frozen when the run was accepted.

Startup upgrades are idempotent (`src/services/schema.py`), add missing
columns to pre-v2 volumes, and backfill one active baseline version per
existing mapping.
