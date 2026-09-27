# Control review contracts

## Scope and provenance

This repository owns the HTTP DTOs, router contracts, and deterministic OpenAPI
for the combined public and control surface. The reconciliation was constructed
from API `master` at `9d77734c7734edf8998334d8627ce9a39c36bb0a` and compared
statically with these preserved sources:

- organizer proposal `175aedf5756b7a4592e8252d64ababcc0b19ba35`;
- organizer snapshot `7454c022a0844496a87032c7fa728087a78ef662`
  (tree `65129071cd8211f1d18f6e5065b995173ba3863e`); and
- transcript snapshot `b8e9b381e1f03d67afbfe291a46632512698450b`
  (tree `9563c0150f9ba8f9d5a5eaf6ab4379a24eac6a52`).

The preserved trees were not merged. Public course/project DTOs and routes were
reconstructed from the organizer proposal's public superset. Organizer and
transcript contracts were reconstructed without importing their implementation
packages.

## Ownership boundary

The API owns only:

- Pydantic request and response DTOs;
- HTTP paths, query limits, status codes, and safe error envelopes;
- narrow `Protocol` ports for owner-supplied projections; and
- `openapi/control.openapi.json`.

It does not discover files, classify courses, ingest transcripts, open owner
catalogs, supervise daemons, persist review state, or implement lifecycle
behavior. Organizer and transcript routes are registered in the control profile
so their contract is present, but return `503` until their owner adapters are
explicitly injected. Public courses and projects default to explicit empty
catalog projections; populated catalogs likewise require injected providers.

Existing publication, GitHub, citation-review, literature-review, search, and
core behavior from the selected base remains in place.

## Organizer surface

The bounded non-streaming endpoints are:

```text
GET /organizer/status
PUT /organizer/control
GET /organizer/proposals?life_domain=teaching&limit=200
```

Proposal limits are between 1 and 500. The owner adapter performs any
control operation and returns an API DTO; the API does not implement organizer
lifecycle behavior.

`OrganizerProposalResponse.course_code` is a required nullable `CourseCode`.
The owner must project the nominal course identity or explicitly return `null`.
A browser must not derive course identity by matching paths or suggested group
text.

The prior `/organizer/events` and `/organizer/events/stream` experiments are
intentionally absent. No monotonic cursor, reconnect/missed-event contract,
bounded buffering rule, or terminal-state protocol was authoritative enough to
publish. Status and proposals are bounded non-streaming snapshots.

## Transcript review surface

The read-only endpoints are:

```text
GET /transcript-reviews
GET /transcript-reviews/{document_id}
GET /transcript-reviews/{document_id}/source
GET /transcript-reviews/{document_id}/assets/{asset_id}
```

Queue and detail responses are review projections only. They contain opaque
identities, source evidence, artifact identities, review categories, geometry,
flags, and typed links; there is no ingestion bundle or filesystem model in the
API.

An injected transcript owner adapter may return path-free binary resources.
The API accepts only a PDF up to 100 MB for a source and PNG, JPEG, or WebP up
to 20 MB for a preview. Missing opaque identities map to safe `404` errors.
Missing, unavailable, invalid-media, and oversized provider results map to a
safe `503` without exposing owner details.

## Deterministic OpenAPI

The combined document is generated from the control-profile FastAPI source:

```bash
python -m projectkoios.api.openapi \
  --output openapi/control.openapi.json
python -m projectkoios.api.openapi \
  --output openapi/control.openapi.json --check
```

Generation sorts all JSON keys and appends one newline. Tests assert byte-for-byte
repeatability, equality with the committed artifact, preservation of every path
and component schema from the selected base, inclusion of the public
course/project plus organizer/transcript contracts, and deliberate exclusion of
the underspecified event endpoints.
