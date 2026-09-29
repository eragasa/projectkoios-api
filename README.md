# projectkoios-api

FastAPI HTTP interface for Project Koios.

Repository routing is documented in `projectkoios-bootstrap/maps/repositories.md`.

## Deployment profiles

The API has two explicit profiles selected with `KOIOS_DEPLOYMENT_PROFILE`:

- `public` is the fail-closed default. It exposes core health and the public
  course, project, and publication catalogs, but does not construct or register
  search or control-review services.
- `control` exposes the public endpoints plus private operational endpoints. It is
  intended for one operator on loopback or a separately protected private network.

```bash
KOIOS_DEPLOYMENT_PROFILE=public uvicorn projectkoios.api.main:app
KOIOS_DEPLOYMENT_PROFILE=control uvicorn projectkoios.api.main:app --host 127.0.0.1
```

The profile boundary is an API capability boundary, not browser-side hiding. A public
runtime does not have control routes in its OpenAPI document. The initial control
profile has no remote-user authentication layer and must not be exposed directly to
the public internet.

## Public course catalog

`GET /api/courses` returns only public-safe course identity and migration-status
metadata. Configure its product-owned JSON source with `KOIOS_COURSE_CATALOG`. An unset
path produces an empty catalog; a configured missing, malformed, duplicate, or
contract-invalid catalog prevents application startup.

The contract distinguishes `inventory-only`, `review-candidate`, and `published`
materials. A review candidate is not publication approval. The catalog does not expose
course files, student records, grades, private feedback, or unreviewed third-party
material.

## Public project catalog

`GET /api/projects` returns only explicitly configured public project records. Configure
its product-owned JSON source with `KOIOS_PROJECT_CATALOG`. An unset path produces an
empty catalog; a configured missing, malformed, duplicate, or contract-invalid catalog
prevents application startup.

Each record separates purpose, principles, capability status, and explicit limitations.
The endpoint does not infer project status from private tasks, repositories, workflow
runs, or control-center state. Independent scientific applications retain authority
over their own claims and release lifecycles.

## Public publication catalog

`GET /api/publications` returns only explicitly published records. Configure its JSON
source with `KOIOS_PUBLICATION_CATALOG`. An unset path produces an empty public catalog;
a configured missing, malformed, duplicate, or schema-invalid catalog prevents
application startup.

The catalog uses schema version `1`:

```json
{
  "schema_version": "1",
  "publications": [
    {
      "id": "software.example-1",
      "slug": "example-1",
      "kind": "software",
      "title": "Example software",
      "summary": "A bounded public record.",
      "authors": ["Project Koios"],
      "published_on": "2026-09-22",
      "version": "1.0.0",
      "citation": "Project Koios (2026). Example software.",
      "topics": ["research software"],
      "claims": ["Declared software checks passed."],
      "limitations": ["No scientific validation is claimed."],
      "links": [
        {
          "label": "Repository",
          "url": "https://example.test/repository"
        }
      ]
    }
  ]
}
```

Catalog order is editorial order. Only records in this file are public; private tasks,
drafts, source paths, and review queues are not inferred or projected into it.

## Local citation review

The control profile exposes a human citation-review queue at `/citation-reviews`. It
reads a private review bundle and writes only explicit review decisions; it does not
edit manuscripts.

Default local paths are:

- `~/.local/share/projectkoios/citation-review/bundle.json`
- `~/.local/share/projectkoios/citation-review/decisions.sqlite3`
- `~/projectkoios/assets/references/ksdft2effmass/` for whitelisted source PDFs

The decision database is created with `0600` permissions. Source requests are
restricted to filenames already present in the review bundle.

## Local equation review

The control profile exposes the bounded `pizzi2020` equation-review projection
at `GET /equation-reviews?document_id=pizzi2020`, content-addressed region
images at `GET /equation-reviews/{candidate_id}/region`, and human decisions at
`PUT /equation-reviews/{candidate_id}/decision`. All paths are explicit; there
is no filesystem discovery or default corpus:

```bash
KOIOS_EQUATION_REVIEW_PIZZI2020_BUNDLE=/private/pizzi2020/equation-review.json
KOIOS_EQUATION_REVIEW_PIZZI2020_REGIONS=/private/pizzi2020/regions
KOIOS_EQUATION_REVIEW_PIZZI2020_DOCUMENT_ROOT=/private/pizzi2020/document
```

The API validates bounded, path-free, content-addressed evidence and asks the
applications owner to read and append revisions. Legacy schema-2 decisions are
read-compatible; new decisions are schema 3. Acceptance requires canonical NFC
reviewer math-body LaTeX without outer delimiters, the deterministic display
mode, renderer identity/version, and exact rendered-input hashes. The browser
supplies neither Obsidian Markdown nor receipt time. The owner derives Markdown,
revalidates all source/evidence/region/proposal bindings, and records immutable
UTC receipts. Assisted text remains `automated_unreviewed` until an explicit
human revision is appended.

The owner adapter is declared by the `equation-review-control` optional extra
and imported only for a configured control capability. Applications commit
`436d3da` preserves `[pdf-corpus]` isolation from simulations/Physkit. That
commit remains unpushed, so hosted verification reports owner-source
unavailability.

## Live GitHubTask projection

The control profile exposes `GET /github/tasks`. Configure its explicit repository
allowlist with comma-separated canonical identities:

```bash
KOIOS_GITHUB_REPOSITORIES=eragasa/projectkoios-api,eragasa/projectkoios-web
```

The server invokes the authenticated `gh api` client without a shell and reads bounded
repository metadata, at most 20 open pull requests, the latest workflow run, and its
first 20 jobs. Only workflow steps whose names begin with `GitHubTask ` become ordered
tasks. GitHub URLs are reconstructed from validated repository and numeric identities.

The endpoint stores no cache or task state and exposes no mutation operation. Each
repository reports a bounded error kind instead of raw CLI output, credentials, or
private paths. An empty allowlist produces an empty projection. The public profile does
not construct the reader or expose the route.

## Organizer and transcript review

The control profile preserves the agent-backed organizer routes:
`GET /organizer/status`, `PUT /organizer/control`,
`GET /organizer/events`, and `GET /organizer/events/stream`. The configured
SQLite catalog remains owned by `projectkoios-agent`; the API does not duplicate
its state or lifecycle logic. `KOIOS_ORGANIZER_CATALOG` selects the catalog, or
it is derived from `KOIOS_DATA_ROOT`.

The transcript-review routes are bounded owner ports. Without an injected
transcript owner they return a safe `503`. Source PDFs and PNG/JPEG/WebP previews
are path-free, signature-checked exact bytes with explicit size limits. The
combined control contract and provenance are documented in
[`docs/control-review-contracts.md`](docs/control-review-contracts.md), and the
authoritative generated document is
[`openapi/control.openapi.json`](openapi/control.openapi.json).

## Continuous integration

Hosted verification is an ordered, read-only GitHubTask sequence documented in
[`docs/ci.md`](docs/ci.md). It currently stops with an explicit unavailable
owner-source result because applications commit `436d3da` is unpushed; it does
not present unreachable checkouts as passing evidence.
