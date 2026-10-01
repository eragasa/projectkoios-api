# API GitHubTask sequence

`.github/workflows/ci.yml` expresses hosted verification as an ordered sequence of
bounded `GitHubTask` steps. `GitHubTask` is a workflow naming and review
convention, not a new workflow engine, persisted task model, or authorization
record.

The intended sequence checks out the API candidate and exact reviewed revisions
of Applications, runtime Ingestion, Project Koios core, organizer, Search,
Obsidian, and References; synchronizes `uv.lock`; validates the product-owned
public catalogs; checks formatting and Ruff; runs strict mypy; verifies
deterministic OpenAPI; and runs the full API test suite.

The citation-document and retained equation/transcript owner pins are:

| Source | Checkout role | Exact commit | Exact tree |
|---|---|---|---|
| Applications | Runtime owner | `781bdb58ce8ce7a4860edc66abaf190b42c91236` | `de6257c720fa73caff21b393af4a3fb4858fd617` |
| Ingestion | Runtime owner | `30db4756049b762ec6ea9962d205424a66d699e3` | `dd171a3ea215d70bd0852fa4c50ff6e26291ded5` |
| Project Koios core | Runtime dependency | `233f36900b9b44c943ecc5e27f2968ad4bee97ad` | `b7c3ffd23086e7ef184c990267d48a56dd87282b` |
| Project Koios public catalogs | CI data only | `88c37990fd37650b3091b2cb2f605a589ab624f4` | `b102469ba33bc6c677ac93d1186a72b1496f5bc8` |
| References | Runtime owner | `f1ca7b4aee552af131ff7af7d1408d33dd338c93` | `b37672e36af13014dc25170be725fbf3f909c2d7` |

Applications separately retains Ingestion commit
`be60640bec4fe15cc88b24161545eb1027ffbd2e` (tree
`d386a1744f79463fd7cd0b3087ee5fc361e0f7d5`) as exact
extraction/document-package **source-lineage metadata**. It is an ancestor of
the runtime Ingestion pin, and both commits have the identical PDF subtree
`49fa8cc975035e90c6b3ce2a2c032a464e66e684`. The lineage commit is not the API
runtime checkout.

The runtime core commit predates the public catalog files. CI therefore keeps
that approved runtime checkout unchanged and uses a second sparse, read-only
checkout at the previously reviewed catalog-bearing commit solely for the public
catalog smoke test. The catalog checkout is not an API dependency or runtime
source.

The organizer runtime remains pinned to commit
`e531cff8f65422d9c0cfab5aaa903c1ebdd778c0` (tree
`84b9182d5fffc594bae6520de49e77ee7e535cf8`). A checkout or exact identity
mismatch fails before dependency synchronization.

The job has read-only repository permission, disables checkout credential
persistence, does not upload artifacts, and cancels an obsolete run for the same
pull request or branch. A failed task stops later tasks through normal GitHub
Actions behavior.

The selected Applications `[pdf-corpus]` capability and API development extra
resolve without a simulations or Physkit package record. Dependency sources are
not inherited from sibling packages, so the API maps core and runtime Ingestion
to their exact compatible Git revisions while CI checks out References and
Applications at the exact reviewed sources. Updating any revision remains a
reviewed compatibility change.

These tasks produce technical verification only. They do not authorize a commit,
push, pull request, merge, deployment, publication, release, or architecture
decision. GitHub remains authoritative for workflow run and pull-request status;
the repository does not copy mutable run state.
