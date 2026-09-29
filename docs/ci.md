# API GitHubTask sequence

`.github/workflows/ci.yml` expresses hosted verification as an ordered sequence of
bounded `GitHubTask` steps. In this first use, `GitHubTask` is a workflow naming and
review convention, not a new workflow engine, persisted task model, or authorization
record.

The intended sequence checks out the API candidate and locked dependencies,
synchronizes `uv.lock`, checks formatting and Ruff, runs strict mypy, verifies
the deterministic OpenAPI, and runs tests.

Hosted execution is currently **unavailable** at GitHubTask 02. Reviewed
applications commit `312f42e` is explicitly unpushed, so the workflow reports
that blocker and exits before toolchain or dependency setup. It deliberately
does not configure a checkout that could be mistaken for passing evidence.
Once the applications owner publishes an installable reviewed dependency chain
(or removes the unrelated simulations/Physkit packaging requirement from a
narrow equation-review install surface), the explicit stop can be replaced by
reviewed checkout and lock steps.

The job has read-only repository permission, disables checkout credential persistence,
does not upload artifacts, and cancels an obsolete run for the same pull request or
branch. A failed task stops later tasks through normal GitHub Actions behavior.

The lock records the locally reviewed candidate dependency graph, including the
applications-mandated simulations/Physkit chain. It cannot currently be
independently regenerated from an installable applications source without
reintroducing a redundant direct API simulations dependency. Standalone install
verification is therefore unavailable as well. Updating any sibling revision or
removing this explicit blocker is a reviewed compatibility change.

These tasks produce technical verification only. They do not authorize a commit,
push, pull request, merge, deployment, publication, release, or architecture decision.
GitHub remains authoritative for the workflow run and pull-request status; the
repository does not copy mutable run state.
