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

Hosted execution is pinned to the Applications equation/transcript owner at
`f926778101e3d74b420f8e1e4189cf2f5d939b6a`, verifies its exact tree
`eeb8563adc6b631443e748473a08aee00583758c`, and checks out the transcript
replay owner at ingestion commit
`be60640bec4fe15cc88b24161545eb1027ffbd2e`. It then continues through the
remaining pinned owners and validation tasks. A checkout or identity mismatch
fails the sequence before dependency synchronization. These new owner commits
remain unpushed, so hosted checkout is expected to fail closed until they are
published.

The job has read-only repository permission, disables checkout credential
persistence, does not upload artifacts, and cancels an obsolete run for the same
pull request or branch. A failed task stops later tasks through normal GitHub
Actions behavior.

The lock is regenerated offline against applications tree
`eeb8563adc6b631443e748473a08aee00583758c` and the merged organizer owner
commit `e531cff8f65422d9c0cfab5aaa903c1ebdd778c0` (tree
`84b9182d5fffc594bae6520de49e77ee7e535cf8`). Project Koios core is pinned to
commit `88c37990fd37650b3091b2cb2f605a589ab624f4` (tree
`b102469ba33bc6c677ac93d1186a72b1496f5bc8`), which is tree-identical to the
prior CI core revision and aligns the API and ingestion source identity without
a version or behavior change. The selected applications `[pdf-corpus]`
capability resolves without a simulations or Physkit package record; only
applications, ingestion, and references participate in the PDF-corpus
equation/transcript owner paths. Offline lock consistency and dependency-tree
checks are local evidence only. The dry run performs no package installation.
Updating any sibling revision remains a reviewed compatibility change.

These tasks produce technical verification only. They do not authorize a commit,
push, pull request, merge, deployment, publication, release, or architecture
decision. GitHub remains authoritative for workflow run and pull-request status;
the repository does not copy mutable run state.
