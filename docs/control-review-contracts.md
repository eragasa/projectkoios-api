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
- applications equation-review schema `3` contract and isolated capability
  owner `436d3daa286d66528ea04957eb0908c572535406` (tree
  `3f7d08efa469dd6d1a5bc8e83f0f342ada88123c`, parent
  `523a46746530ffdb010fa90a8ebc6484447976a6`).

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
- a narrow adapter to the declared applications-owned schema `3` revision
  seam with read compatibility for legacy schema-2 revisions; and
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

The queue items are the complete candidate detail required by the reviewed Web
candidate; no additional candidate-detail endpoint was present in the pinned
provisional contract. The source identity, PDF-point region, deterministic
evidence, nullable assistance, and nullable human decision fields retain the
provisional JSON names. All identities, hashes, text, counts, pages, and finite
positive-area coordinates are bounded. Source names are display-only, path-free
values.

Only `pizzi2020` is configured in this candidate.
`KOIOS_EQUATION_REVIEW_PIZZI2020_BUNDLE`,
`KOIOS_EQUATION_REVIEW_PIZZI2020_REGIONS`, and
`KOIOS_EQUATION_REVIEW_PIZZI2020_DOCUMENT_ROOT` must all be set; none has a
default. The first two configure the path-free API read projection. The third
is the exact applications-owned document-package root used for latest-decision
validation and append. The version `2` JSON bundle is limited to 20,000,000
bytes and 256 candidates. It has this private projection shape:

```json
{
  "schema_version": "2",
  "document_id": "pizzi2020",
  "items": [
    {
      "candidate_id": "opaque-id",
      "source": {},
      "region": {},
      "deterministic_evidence": {},
      "display_mode": "DISPLAY",
      "assistance": null,
      "decision": null
    }
  ]
}
```

The elided objects are bounded API evidence objects, not hydrated placeholders.
Proposed assistance may carry its attempt identity and explicit model
name/digest, prompt version, and request/result identities. These values are
path-free and optional only when model provenance is unavailable. The bundle
never carries owner review state: the API derives typed status,
`current_revision`, `expected_previous_revision`, and the latest decision from
the owner on every read. A bundle that is missing a required field, changes the
document, contains duplicate candidates, or claims an applications-owned
decision is unavailable evidence (`503`). The API does not inspect a PDF. Region files are
content-addressed direct children of the configured root, named exactly by the
lowercase `region.image_sha256` with no extension. On access the API rejects
root/file symlinks, escapes, missing/non-regular files, empty or over-20,000,000
byte bodies, digest mismatches, and content outside PNG/JPEG/WebP signatures.
Responses are `inline` and `nosniff`; paths and filenames are never exposed.

The API validates the reviewed Web write fields. An `ACCEPT_TRANSCRIPTION`
request must name the exact displayed `assistance.proposal_sha256` and carry
canonical reviewer LaTeX, deterministic display mode, renderer identity and
version, and SHA-256 values for the rendered reviewer-LaTeX and canonical
Obsidian inputs. Reviewer LaTeX is the exact NFC-normalized math body: no outer
`$...$`/`$$...$$` delimiters, leading/trailing whitespace, or carriage returns.
Noncanonical input is typed
`EQUATION_REVIEW_REVIEWER_LATEX_NONCANONICAL`; the immutable assisted proposal
may retain delimiters and is never rewritten. A missing proposal hash or
representation is `422`; a different or absent proposal is typed `409`. The
request has no Obsidian Markdown field: the owner derives `$<latex>$` for
`INLINE` or `$$\n<latex>\n$$` for `DISPLAY`.
The adapter invokes the owner's render-confirmation constructor to recompute
both current hashes before append. A reviewer-LaTeX mismatch is typed
`EQUATION_REVIEW_EDIT_AFTER_RENDER`; a canonical-wrapper mismatch is typed
`EQUATION_REVIEW_RENDER_STALE`. Non-acceptance must send the three accepted
representation fields as null and cannot claim accepted content.

Every request includes `expected_previous_revision` (`0` through `9998`) for
owner-enforced optimistic concurrency. There is no request timestamp. The
control adapter generates strict UTC `recorded_at_utc`, binds document,
candidate, source, deterministic evidence, region image, and proposal hashes,
and invokes only `append_human_equation_revision`. The response returns the
stored schema/revision identity and time plus exact accepted reviewer LaTeX,
owner-derived Obsidian Markdown, their hashes, and render confirmation. A
legacy schema-2 acceptance is projected as `LEGACY_ACCEPTANCE` with no claimed
canonical content; a correction appends schema-3 revision 2 without rewriting
revision 1. Rejection and revision-required records return all accepted-content
fields as null. On semantic retry the owner returns the original immutable
receipt; revision number, not time, is canonical ordering.

The adapter maps applications-owned failures without exposing exception text:
stale proposal/evidence/revision/render state and different concurrent winners
are typed `409`; partial or malformed output and an unavailable authorized root
are typed `503`. Queue decisions come only from
`load_latest_human_equation_revision`, which fully validates legacy/schema-3
history and historical proposal bindings. Assisted text remains
`automated_unreviewed`; human acceptance is a separate append-only revision.

To bound local request amplification, the API accepts at most 256 candidates
per configured document and gives aggregate latest-decision projection a
2-second cooperative budget checked between owner calls. One in-progress owner
validation is not cancelled: cancellation could create an ambiguous write and
the owner already bounds its files and bytes. The current owner exposes no
batch latest-decision projection, so repeated whole-document validation within
that bounded queue remains a documented performance risk.

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
9. handle typed `409` proposal/evidence/revision/render/concurrency outcomes and
   typed `503` partial/unavailable outcomes.

## Declared dependency seam and hosted availability

The organizer runtime remains the primary dependency
`projectkoios-agent==0.0.0`, pinned in CI to
`2991f8506ca444f384ad950dfdfc6c76bb2c8546`. The private equation adapter is
declared behind the API `equation-review-control` optional extra. Public startup
and an unconfigured
control profile do not import `projectkoios.applications`; only construction of
a configured equation-review control store imports the owner chain. The only
applications capability selected by that runtime extra is
`projectkoios-applications[pdf-corpus]==0.1.0.dev0`. The development extra also
names `projectkoios-ingestion[pdf]` so `uv` can bind that unpublished transitive
requirement to the reviewed local source; dependency sources are not inherited
from another package. This local lock aid does not broaden the control runtime
extra. There is no API dependency or source mapping for
`projectkoios-simulations` or Physkit.

Applications commit `436d3da` retains separate simulation, example, and
development capabilities while requiring canonical schema-3 reviewer math
bodies. Lock consistency against tree
`3f7d08efa469dd6d1a5bc8e83f0f342ada88123c` resolves
47 packages (including the preserved organizer owner) and produces no
`projectkoios-simulations` or Physkit package
record. A guarded import/startup
check also proves that the configured equation-review control store can load
through `[pdf-corpus]` while imports of simulations and Physkit are rejected.
The API contains no copied or extracted owner persistence code.

Hosted verification remains **unavailable** because applications commit
`436d3da` is explicitly unpushed. CI retains the exact future checkout reference
but stops before attempting it, so an unavailable remote commit cannot be
mistaken for passing evidence. No installation was performed as part of this
compatibility update.
