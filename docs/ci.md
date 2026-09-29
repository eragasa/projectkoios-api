# API GitHubTask sequence

`.github/workflows/ci.yml` expresses hosted verification as an ordered sequence of
bounded `GitHubTask` steps. In this first use, `GitHubTask` is a workflow naming and
review convention, not a new workflow engine, persisted task model, or authorization
record.

The intended sequence checks out the API candidate and locked dependencies,
synchronizes `uv.lock`, checks formatting and Ruff, runs strict mypy, verifies
the deterministic OpenAPI, and runs tests.

Hosted execution is currently **unavailable** at GitHubTask 02. Reviewed
applications follow-up `1e331a9527434938d0aa8ae7bfc4a99bddc87d9d` is
explicitly unpushed, so the workflow reports that blocker and exits before
attempting its exact checkout. The later checkout is retained as an unreachable
pin for review and must not be treated as execution evidence. Once that commit
is published at the declared owner repository, the explicit stop can be removed
and the configured sequence can run.

The job has read-only repository permission, disables checkout credential persistence,
does not upload artifacts, and cancels an obsolete run for the same pull request or
branch. A failed task stops later tasks through normal GitHub Actions behavior.

The lock was regenerated offline against applications tree
`399d07372410255fc479a5fe2b3d22deee81f669`. The selected `[pdf-corpus]`
capability resolves without a simulations or Physkit package record; only
applications, ingestion, and references participate in the owner path. Offline
lock consistency and dependency-tree checks are local evidence only. No package
installation was performed, and hosted verification remains unavailable until
the pinned applications commit is published. Updating any sibling revision or
removing the explicit stop is a reviewed compatibility change.

These tasks produce technical verification only. They do not authorize a commit,
push, pull request, merge, deployment, publication, release, or architecture decision.
GitHub remains authoritative for the workflow run and pull-request status; the
repository does not copy mutable run state.
