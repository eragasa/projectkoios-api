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

Hosted execution is currently **unavailable** at GitHubTask 02. Reviewed
applications schema-3 owner `436d3daa286d66528ea04957eb0908c572535406` is
explicitly unpushed, so the workflow reports that blocker and exits before
attempting its exact checkout. The later checkouts are retained as unreachable
pins for review and must not be treated as execution evidence. Once that commit
is published at the declared owner repository, the explicit stop can be removed
and the configured sequence can run.

The job has read-only repository permission, disables checkout credential
persistence, does not upload artifacts, and cancels an obsolete run for the same
pull request or branch. A failed task stops later tasks through normal GitHub
Actions behavior.

The lock is regenerated offline against applications tree
`3f7d08efa469dd6d1a5bc8e83f0f342ada88123c` and the preserved organizer owner
commit `2991f8506ca444f384ad950dfdfc6c76bb2c8546`. The selected applications
`[pdf-corpus]` capability resolves without a simulations or Physkit package
record; only applications, ingestion, and references participate in the
equation owner path. Offline lock consistency and dependency-tree checks are
local evidence only. No package installation is performed, and hosted
verification remains unavailable until the pinned applications commit is
published. Updating any sibling revision or removing the explicit stop is a
reviewed compatibility change.

These tasks produce technical verification only. They do not authorize a commit,
push, pull request, merge, deployment, publication, release, or architecture
decision. GitHub remains authoritative for workflow run and pull-request status;
the repository does not copy mutable run state.
