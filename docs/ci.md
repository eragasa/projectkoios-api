# API GitHubTask sequence

`.github/workflows/ci.yml` expresses hosted verification as an ordered sequence of
bounded `GitHubTask` steps. In this first use, `GitHubTask` is a workflow naming and
review convention, not a new workflow engine, persisted task model, or authorization
record.

The sequence:

1. checks out the API candidate;
2. checks out exact reviewed revisions of its five Project Koios source dependencies,
   including the metadata-only organization agent;
3. installs the exact `uv` and Python versions;
4. synchronizes `uv.lock` without updating it;
5. validates the exact product-owned public course and project catalogs through the
   API contracts;
6. checks formatting;
7. runs Ruff;
8. runs mypy; and
9. runs the API test suite.

The job has read-only repository permission, disables checkout credential persistence,
does not upload artifacts, and cancels an obsolete run for the same pull request or
branch. A failed task stops later tasks through normal GitHub Actions behavior.

The lock records Python dependency artifacts. The workflow separately pins sibling
Project Koios repositories because local path sources cannot encode Git revisions.
Updating any sibling revision is a reviewed compatibility change.

These tasks produce technical verification only. They do not authorize a commit,
push, pull request, merge, deployment, publication, release, or architecture decision.
GitHub remains authoritative for the workflow run and pull-request status; the
repository does not copy mutable run state.
