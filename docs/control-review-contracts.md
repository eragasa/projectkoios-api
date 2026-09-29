# Control review contracts

## Scope and provenance

This repository owns the HTTP DTOs, router contracts, and deterministic OpenAPI
for the combined public and control surface. This integration explicitly merges
the complete equation-review branch at
`5ea1128dce3e7c8d93272ff0155f2e2d81c8a72e` into the preserved organizer
snapshot `7454c022a0844496a87032c7fa728087a78ef662` (tree
`65129071cd8211f1d18f6e5065b995173ba3863e`). Its reviewed sources also include:

- transcript snapshot `b8e9b381e1f03d67afbfe291a46632512698450b`
  (tree `9563c0150f9ba8f9d5a5eaf6ab4379a24eac6a52`); and
- Web equation-review proposal
  `6e435cf2ca1b20ed129f806e1874eabed193ec41`, specifically
  `docs/equation-review-api-contract.md` and its provisional TypeScript
  projection; and
- applications deterministic equation queue and schema `3` owner
  `b25ba8cc828b2d67bb8b8e20dd6bc5b28515547f` (tree
  `2f32fa9d9b3a5bb452a643dbba34a7dfae461423`, parent
  `436d3daa286d66528ea04957eb0908c572535406`).

The primary course/project repositories and the working organizer owner
integration are retained unchanged in behavior. The equation-review and
transcript boundaries are integrated around them; no equation owner persistence
is copied into this repository.

## Ownership boundary

The API owns only:

- Pydantic request and response DTOs;
- HTTP paths, query limits, status codes, and safe error envelopes;
- narrow `Protocol` ports for owner-supplied projections;
- the explicit, content-addressed `pizzi2020` equation read boundary;
- a narrow adapter to the applications-owned deterministic queue and schema `3`
  append seams, with read compatibility for legacy schema-2 revisions; and
- `openapi/control.openapi.json`.

It does not scan equation files, ingest transcripts, process PDFs, or
reimplement equation persistence. The applications package alone validates and
appends human equation revisions. Transcript routes return `503` until an owner
adapter is explicitly injected. Public course/project catalogs retain their
product-owned JSON repositories. Organizer status, control, and events retain
the preserved `projectkoios-agent` SQLite catalog owner selected by
`KOIOS_ORGANIZER_CATALOG` or `KOIOS_DATA_ROOT`.

Existing publication, GitHub, citation-review, literature-review, search, and
core behavior from the selected primary remains in place. The transcript owner
boundary revalidates returned DTOs and maps unavailable, malformed, and
unexpected provider results to safe fixed envelopes. Missing transcript
identities remain fixed `404` responses. Cancellation and process-exit
exceptions are not intercepted by that boundary.

## Organizer surface

The preserved endpoints are:

```text
GET /organizer/status
PUT /organizer/control
GET /organizer/events?after=0
GET /organizer/events/stream?after=0
```

The API translates the agent-owned status and events to HTTP DTOs. Event reads
use a nonnegative monotonic sequence cursor. The streaming route emits SSE
`organizer` events with the owner sequence as the event id, sends keepalives
when no event is available, polls once per second, and ends after client
disconnection. Control accepts only `on`, `pause`, or `off` and delegates mode
and lifecycle behavior to the configured `OrganizerCatalog`. No organizer
proposal route is introduced by this integration.

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

Only one explicit completed `pizzi2020` document package is configurable:

```text
KOIOS_EQUATION_REVIEW_PIZZI2020_DOCUMENT_ROOT
```

The variable has no default. The removed bundle and separate region-root
variables are not runtime inputs. The control adapter binds the supplied path as
one local `AuthorizedRoot`; neither the API nor applications searches for other
document roots.

Every GET queue response comes from applications-owned
`project_equation_review_queue`. That read-only seam verifies the completion
identity and inventory, all eligible deterministic display/proposed candidates,
every review-tree artifact, and the latest schema-2 or schema-3 human revision.
It admits at most 256 candidates and supplies deterministic page/geometry/ID
ordering. The API revalidates and bounds the owner projection into path-free
DTOs containing:

- contract, package, source, document, and stable projection identities;
- total, decided, and pending counts;
- page and PDF-point region evidence plus the content-addressed PNG hash;
- native deterministic text and processor evidence;
- explicit `NOT_STARTED` or `AUTOMATED_UNREVIEWED` assistance, with immutable
  attempt, method, proposal, and proposal-hash provenance; and
- the latest decision, canonical accepted sources and hashes, and complete
  renderer provenance when schema 3 provides them.

Legacy schema-2 acceptance is exposed as `LEGACY_ACCEPTANCE` without invented
accepted source. Rejection and revision-required records expose no accepted
representation. The stable projection ID and complete JSON replay unchanged
when package and review content are unchanged. Queue-incomplete evidence maps to
typed `EQUATION_REVIEW_QUEUE_INCOMPLETE` (`503`), malformed owner evidence maps
to typed `EQUATION_REVIEW_QUEUE_MALFORMED` (`502`), and an unavailable explicit
root maps to typed owner unavailable (`503`), without exception text.

Region GET first resolves the candidate from the current owner queue, derives
its deterministic package key without scanning, and reads
`content/equations/regions/<key>/source/image.png` through descriptor-confined
`AuthorizedRoot` access. The body must be nonempty PNG bytes, no larger than
20,000,000 bytes, and exactly match the projected SHA-256. Responses are
`inline` and `nosniff`; paths and filenames are never returned.

An `ACCEPT_TRANSCRIPTION` request must name the displayed proposal hash and
carry canonical reviewer LaTeX, deterministic display mode, renderer
identity/version, and SHA-256 values for the rendered reviewer-LaTeX and
canonical Obsidian inputs. Reviewer LaTeX is the exact NFC-normalized math body:
no outer delimiters, edge whitespace, or carriage returns. The browser supplies
neither Obsidian Markdown nor receipt time. The owner derives canonical Markdown,
validates all evidence bindings, and exclusively appends schema 3. Typed stale
proposal/evidence/revision/render and concurrent-winner outcomes remain `409`.

After append, the API invokes the queue seam again and returns only the refreshed
latest revision when it exactly agrees with the immutable append receipt. It does
not construct a response from the stale pre-append projection. Assisted text
remains `automated_unreviewed`; human acceptance is a distinct append-only
revision.

## Deterministic OpenAPI

The combined document is generated from the control-profile FastAPI source:

```bash
python -m projectkoios.api.openapi \
  --output openapi/control.openapi.json
python -m projectkoios.api.openapi \
  --output openapi/control.openapi.json --check
```

Generation sorts all JSON keys and appends one newline. Tests assert
byte-for-byte repeatability, equality with the committed artifact, preservation
of public course/project and organizer status/control/event paths, and inclusion
of the transcript/equation contracts.

## Downstream Web migration requirement

This API change deliberately does not modify the Web repository. Before the Web
consumer moves to this contract, it must:

1. regenerate its schema/client from `openapi/control.openapi.json`;
2. preserve organizer status/control/event and SSE consumption against the
   generated organizer DTOs;
3. add transcript-review and equation-review proxy prefixes;
4. replace the provisional equation projection with the generated API types;
5. send required `expected_previous_revision` from the queue projection;
6. render and submit current reviewer LaTeX, display mode, renderer identity and
   version, and both rendered-input hashes, but never submit Obsidian Markdown;
7. never send `recorded_at_utc`;
8. expose only the path-free equation provenance projection in Debug &
   Provenance; and
9. handle typed `409` proposal/evidence/revision/render/concurrency outcomes,
   typed `502` malformed-queue outcomes, and typed `503`
   incomplete/unavailable outcomes.

## Declared dependency seam and hosted availability

The organizer runtime remains the primary dependency
`projectkoios-agent==0.0.0`, pinned in CI to merged commit
`e531cff8f65422d9c0cfab5aaa903c1ebdd778c0` (tree
`84b9182d5fffc594bae6520de49e77ee7e535cf8`). The private equation adapter is
declared behind the API `equation-review-control` optional extra. Public startup
and an unconfigured
control profile do not import `projectkoios.applications`; only construction of
a configured equation-review control owner imports the owner chain. The only
applications capability selected by that runtime extra is
`projectkoios-applications[pdf-corpus]==0.1.0.dev0`. The development extra also
names `projectkoios-ingestion[pdf]` so `uv` can bind that unpublished transitive
requirement to the reviewed local source; dependency sources are not inherited
from another package. This local lock aid does not broaden the control runtime
extra. There is no API dependency or source mapping for
`projectkoios-simulations` or Physkit.

Applications commit `b25ba8c` retains separate simulation, example, and
development capabilities while owning the deterministic queue and canonical
schema-3 reviewer math bodies. Lock consistency against tree
`2f32fa9d9b3a5bb452a643dbba34a7dfae461423` resolves
47 packages (including the preserved organizer owner) and produces no
`projectkoios-simulations` or Physkit package
record. A guarded import/startup
check also proves that the configured equation-review control owner can load
through `[pdf-corpus]` while imports of simulations and Physkit are rejected.
The API contains no copied or extracted owner persistence code.

Hosted verification checks out public applications commit `b25ba8c`, verifies
its exact tree, and proceeds through the pinned dependency and API checks. No
installation was performed as part of the local compatibility update.
