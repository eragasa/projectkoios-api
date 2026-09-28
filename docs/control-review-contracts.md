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
  (tree `9563c0150f9ba8f9d5a5eaf6ab4379a24eac6a52`); and
- Web equation-review proposal
  `6e435cf2ca1b20ed129f806e1874eabed193ec41`, specifically
  `docs/equation-review-api-contract.md` and its provisional TypeScript
  projection.

The preserved trees were not merged. Public course/project DTOs and routes were
reconstructed from the organizer proposal's public superset. Organizer and
transcript contracts were reconstructed without importing their implementation
packages.

## Ownership boundary

The API owns only:

- Pydantic request and response DTOs;
- HTTP paths, query limits, status codes, and safe error envelopes;
- narrow `Protocol` ports for owner-supplied projections;
- the explicit, content-addressed `pizzi2020` equation read boundary; and
- `openapi/control.openapi.json`.

It does not scan for files, classify courses, ingest transcripts, open owner
catalogs, process PDFs, supervise daemons, persist equation review state, or
implement lifecycle behavior. Organizer and transcript routes are registered in the control profile
so their contract is present, but return `503` until their owner adapters are
explicitly injected. Public courses and projects default to explicit empty
catalog projections; populated catalogs likewise require injected providers.

Existing publication, GitHub, citation-review, literature-review, search, and
core behavior from the selected base remains in place.

Every injected owner result is revalidated into a fresh API DTO immediately
before serialization. Provider-declared unavailability remains a fixed `503`;
malformed provider data is a fixed `502`; and any other ordinary provider
exception is a fixed `500`. Each status uses the declared JSON
`ApiErrorResponse` envelope, and no exception text is returned. Missing
transcript identities remain fixed `404` responses. Cancellation and process
exit exceptions are not intercepted by this boundary.

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

Organizer display paths are bounded normalized relative POSIX paths. Absolute
paths, empty or dot segments, traversal, backslashes, control characters, and
paths longer than 4,096 characters are invalid provider output. File sizes are
bounded at 1,000,000,000,000 bytes and collection/count projections have
explicit maxima. Proposal file identities and root/path identities are unique
within a response.

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
The source limit is exactly **100,000,000 bytes** and the preview limit is
exactly **20,000,000 bytes**. Resources must be nonempty exact `bytes`, and the
declared media type must match its magic signature: PDF `%PDF-`, the complete
8-byte PNG signature, JPEG `ff d8 ff`, or WebP `RIFF....WEBP`. Unknown,
spoofed, mismatched, empty, or oversized provider resources are fixed `502`
errors. Binary responses set `X-Content-Type-Options: nosniff` and
`Content-Disposition: inline`; provider filenames are never accepted or
exposed. Missing opaque identities map to safe `404` errors and owner-declared
unavailability maps to a safe `503`.

The current owner contract returns complete `bytes`, so a resource is fully
buffered once by the single-operator API boundary before the response is
constructed. This accepted memory cost is bounded by the exact limits above.
This contract does **not** claim streaming behavior.

All transcript identities are bounded path-free opaque values. Absolute or
path-like values, traversal, backslashes, controls, and overlength values are
rejected. Text and collection members, counts, artifact generations, page
numbers, and geometry all have explicit maxima. Region coordinates must be
finite, nonnegative, no greater than 1,000,000, and define positive area.
Document/item/link identities and aggregate counts are checked for consistency.

## Equation review surface

The control-only endpoints are:

```text
GET /equation-reviews?document_id=pizzi2020
GET /equation-reviews/{candidate_id}/region
PUT /equation-reviews/{candidate_id}/decision
```

The queue items are the complete candidate detail required by the reviewed Web
candidate; no additional candidate-detail endpoint was present in the pinned
provisional contract. The source identity, PDF-point region, deterministic
evidence, nullable assistance, and nullable human decision fields retain the
provisional JSON names. All identities, hashes, text, counts, pages, and finite
positive-area coordinates are bounded. Source names are display-only, path-free
values.

Only `pizzi2020` is configured in this candidate. Both
`KOIOS_EQUATION_REVIEW_PIZZI2020_BUNDLE` and
`KOIOS_EQUATION_REVIEW_PIZZI2020_REGIONS` must be set; neither has a default.
The version `1` JSON bundle is limited to 20,000,000 bytes and 100,000
candidates. It has this API projection shape:

```json
{
  "schema_version": "1",
  "document_id": "pizzi2020",
  "items": [
    {
      "candidate_id": "opaque-id",
      "source": {},
      "region": {},
      "deterministic_evidence": {},
      "assistance": null,
      "decision": null
    }
  ]
}
```

The elided objects are the required OpenAPI response objects, not optional or
hydrated placeholders. A bundle that is missing a field, changes the document,
contains duplicate candidates, or claims an applications-owned decision is
unavailable evidence (`503`). The API does not inspect a PDF. Region files are
content-addressed direct children of the configured root, named exactly by the
lowercase `region.image_sha256` with no extension. On access the API rejects
root/file symlinks, escapes, missing/non-regular files, empty or over-20,000,000
byte bodies, digest mismatches, and content outside PNG/JPEG/WebP signatures.
Responses are `inline` and `nosniff`; paths and filenames are never exposed.

The reviewed Web proposal's write request is accepted for validation. An
`ACCEPT_TRANSCRIPTION` request must name the exact currently displayed
`assistance.proposal_sha256`; a missing assistance object or any hash mismatch
is a `409`. The endpoint nevertheless has only a typed `503` success status in
the authoritative OpenAPI because no applications-owned append-only human
revision seam exists. It performs no write and never turns proposed LaTeX into
accepted text.

The exact missing owner contract is an atomic append operation accepting the
validated `document_id`, `candidate_id`, `source_sha256`,
`deterministic_evidence.evidence_sha256` (candidate evidence hash),
`region.image_sha256`, nullable exact `assistance.proposal_sha256`, disposition,
and note. It must reject stale or mismatched evidence, assign a monotonically
increasing revision under a declared concurrency policy, store an immutable UTC
timestamped revision, and project the latest decision without mutating source or
assisted text. The API can publish a `200 EquationReviewDecisionResponse` only
after the applications owner publishes that contract and an adapter is injected.

## Deterministic OpenAPI

The combined document is generated from the control-profile FastAPI source:

```bash
python -m projectkoios.api.openapi \
  --output openapi/control.openapi.json
python -m projectkoios.api.openapi \
  --output openapi/control.openapi.json --check
```

Generation sorts all JSON keys and appends one newline. Tests assert byte-for-byte
repeatability, equality with the committed artifact, the exact path superset of
the selected API master, inclusion of the public course/project plus selected
organizer/transcript/equation contracts, and deliberate exclusion of event paths,
schemas, and references.

## Downstream Web migration requirement

This API change deliberately does not modify the Web repository. Before the Web
consumer moves to this contract, it must:

1. regenerate its schema/client from `openapi/control.openapi.json`;
2. delete organizer event DTOs, the event client, and `EventSource` usage;
3. use bounded status polling plus proposal reads instead of SSE;
4. consume the direct required-nullable `course_code` projection without
   browser path matching; and
5. add organizer, transcript-review, and equation-review proxy prefixes;
6. replace the provisional equation projection with the generated API types;
   and
7. treat the equation decision operation's authoritative `503` as unavailable
   until the applications-owned append contract exists.

No organizer event schema or reference is retained for compatibility.

## Explicitly deferred packaging scope

Packaging/sdist reproducibility and broader artifact-inclusion changes are
`SAFE_TO_DEFER` for this contract correction. The current verification still
builds the wheel twice reproducibly and exercises its API from an extracted
wheel with the source tree absent. Revisit sdist and generalized artifact
inclusion when packaging becomes the owning milestone; they are not broadened
here because the API DTO/OpenAPI source remains single-source.
