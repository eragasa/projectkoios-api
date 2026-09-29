# API GitHubTask sequence

`.github/workflows/ci.yml` expresses hosted verification as an ordered sequence of
bounded `GitHubTask` steps. `GitHubTask` is a workflow naming and review
convention, not a new workflow engine, persisted task model, or authorization
record.

The intended sequence checks out the API candidate and exact reviewed revisions
of applications, ingestion, core, organizer, search, Obsidian, and references;
synchronizes `uv.lock`; validates the product-owned public catalogs; checks
formatting and Ruff; runs strict mypy; verifies deterministic OpenAPI; and runs
the full API test suite.

Hosted execution checks out the published applications queue owner at
`b25ba8cc828b2d67bb8b8e20dd6bc5b28515547f`, verifies its exact tree
`2f32fa9d9b3a5bb452a643dbba34a7dfae461423`, and then continues through the
remaining pinned owners and validation tasks. A checkout or identity mismatch
fails the sequence before dependency synchronization.

The job has read-only repository permission, disables checkout credential
persistence, does not upload artifacts, and cancels an obsolete run for the same
pull request or branch. A failed task stops later tasks through normal GitHub
Actions behavior.

The lock is regenerated offline against applications tree
`2f32fa9d9b3a5bb452a643dbba34a7dfae461423` and the merged organizer owner
commit `e531cff8f65422d9c0cfab5aaa903c1ebdd778c0` (tree
`84b9182d5fffc594bae6520de49e77ee7e535cf8`). The selected applications
`[pdf-corpus]` capability resolves without a simulations or Physkit package
record; only applications, ingestion, and references participate in the
equation owner path. Offline lock consistency and dependency-tree checks are
local evidence only. No package installation is performed. Updating any sibling
revision remains a reviewed compatibility change.

These tasks produce technical verification only. They do not authorize a commit,
push, pull request, merge, deployment, publication, release, or architecture
decision. GitHub remains authoritative for workflow run and pull-request status;
the repository does not copy mutable run state.
