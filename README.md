# projectkoios-api

FastAPI HTTP interface for Project Koios.

Repository routing is documented in `projectkoios-bootstrap/maps/repositories.md`.

## Deployment profiles

The API has two explicit profiles selected with `KOIOS_DEPLOYMENT_PROFILE`:

- `public` is the fail-closed default. It exposes core health and the public
  course, project, and publication contracts, but does not construct or register
  search or review services.
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
at `GET /equation-reviews?document_id=pizzi2020` and its content-addressed
region images at `GET /equation-reviews/{candidate_id}/region`. All configured
paths are required; there are no default paths or filesystem discovery:

```bash
KOIOS_EQUATION_REVIEW_PIZZI2020_BUNDLE=/private/pizzi2020/equation-review.json
KOIOS_EQUATION_REVIEW_PIZZI2020_REGIONS=/private/pizzi2020/regions
KOIOS_EQUATION_REVIEW_PIZZI2020_DOCUMENT_ROOT=/private/pizzi2020/document
```

The schema-version `1` bundle contains the queue candidates exactly as exposed
by the HTTP response plus `schema_version`; every candidate must explicitly
carry `decision: null`. Region bytes live directly under the configured root at
a filename equal to `region.image_sha256`, with no extension. The API rejects
symlinks, missing or non-regular resources, hash mismatches, unknown image
signatures, oversized data, malformed bundles, and unowned decision claims as
unavailable evidence. The API read projection never parses a source PDF; the
applications owner may re-hash inventoried source bytes when validating an
append.

`PUT /equation-reviews/{candidate_id}/decision` validates that an acceptance
names the exact displayed assisted-proposal hash, then delegates one optimistic
append to the applications-owned equation-review schema `2` seam. The request
must include `expected_previous_revision`; it never accepts a browser time. The
control adapter generates a strict UTC receipt time and returns the owner-stored
winning revision. An exact retry therefore returns the original receipt even
though the adapter generated a later time. Stale proposal/evidence/revision,
concurrent different output, partial output, and unavailable owner roots have
stable typed classifications. Assisted text remains automated and unreviewed;
the append creates a separate human revision and never promotes or rewrites it.
The owner adapter is declared by the `equation-review-control` optional extra
and is imported only when this configured control capability is constructed.
Applications follow-up `1e331a9` isolates `[pdf-corpus]` from its optional
simulations/Physkit capabilities; the API lock therefore contains neither
package. The exact applications commit remains unpushed, so hosted verification
continues to report owner-source unavailability.

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

## Combined control-review contract

The control profile also publishes bounded organizer, transcript-review, and
equation-review contracts. Organizer and transcript domain behavior is
available only through explicitly injected owner adapters; without one, those
routes return a safe `503`. Equation reads use only the explicit `pizzi2020`
configuration described above, and writes use the optional declared
`projectkoios-applications[pdf-corpus]` package seam. No organizer daemon,
transcript ingestion, filesystem discovery, or API-owned equation-review
persistence is implemented here.

Every owner projection is runtime-validated at the API boundary. Invalid owner
data returns a fixed `502`, unexpected ordinary owner failures return a fixed
`500`, and declared unavailability remains a fixed `503`, always through the
safe API error envelope. Transcript PDFs are nonempty signature-checked exact
bytes bounded at 100,000,000 bytes; PNG/JPEG/WebP previews are bounded at
20,000,000 bytes. These single-operator resources are fully buffered, not
streamed.

The authoritative combined document is
[`openapi/control.openapi.json`](openapi/control.openapi.json). Contract mapping,
limits, error behavior, downstream Web migration, provenance, and the deliberate
omission of all organizer event endpoints and schemas are documented in
[`docs/control-review-contracts.md`](docs/control-review-contracts.md).

## Continuous integration

Hosted verification is an ordered, read-only GitHubTask sequence documented in
[`docs/ci.md`](docs/ci.md). It currently stops with an explicit unavailable
owner-source result because applications commit `1e331a9` is unpushed; it does
not present the unreachable configured checkout as passing evidence.
