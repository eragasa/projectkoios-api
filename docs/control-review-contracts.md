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
  projection; and
- applications equation-review schema `3` contract and isolated capability
  owner `523a46746530ffdb010fa90a8ebc6484447976a6` (tree
  `211348d597e01646b2f0d05cd1f73d7718eb6a63`, parent
  `1e331a9527434938d0aa8ae7bfc4a99bddc87d9`).

The preserved trees were not merged. Public course/project DTOs and routes were
reconstructed from the organizer proposal's public superset. Organizer and
transcript contracts were reconstructed without importing their implementation
packages.

## Ownership boundary

The API owns only:

- Pydantic request and response DTOs;
- HTTP paths, query limits, status codes, and safe error envelopes;
- narrow `Protocol` ports for owner-supplied projections;
- the explicit, content-addressed `pizzi2020` equation read boundary;
- a narrow adapter to the declared applications-owned schema `3` revision
  seam with read compatibility for legacy schema-2 revisions; and
- `openapi/control.openapi.json`.

It does not scan for files, classify courses, ingest transcripts, open owner
catalogs, process PDFs, supervise daemons, or reimplement equation persistence.
The applications package alone validates and appends human revisions. Organizer
and transcript routes are registered in the control profile
so their contract is present, but return `503` until their owner adapters are
explicitly injected. Public courses and projects default to explicit empty
catalog projections; populated catalogs likewise require injected providers.

Existing publication, GitHub, citation-review, literature-review, search, and
core behavior from the selected base remains in place.

Every injected organizer/transcript owner result is revalidated into a fresh
API DTO immediately before serialization. Provider-declared unavailability
remains a fixed `503`;
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
Obsidian inputs. A missing proposal hash or representation is `422`; a different
or absent proposal is typed `409`. The request has no Obsidian Markdown field:
the owner derives `$<latex>$` for `INLINE` or `$$\n<latex>\n$$` for `DISPLAY`.
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
7. send required `expected_previous_revision` from the queue projection;
8. render and submit current reviewer LaTeX, display mode, renderer identity and
   version, and both rendered-input hashes, but never submit Obsidian Markdown;
9. never send `recorded_at_utc`;
10. expose only the path-free provenance projection in Debug & Provenance; and
11. handle typed `409` proposal/evidence/revision/render/concurrency outcomes
    and typed `503` partial/unavailable outcomes.

No organizer event schema or reference is retained for compatibility.

## Declared dependency seam and hosted availability

The private adapter is declared behind the API
`equation-review-control` optional extra. Public startup and an unconfigured
control profile do not import `projectkoios.applications`; only construction of
a configured equation-review control store imports the owner chain. The only
applications capability selected by that runtime extra is
`projectkoios-applications[pdf-corpus]==0.1.0.dev0`. The development extra also
names `projectkoios-ingestion[pdf]` so `uv` can bind that unpublished transitive
requirement to the reviewed local source; dependency sources are not inherited
from another package. This local lock aid does not broaden the control runtime
extra. There is no API dependency or source mapping for
`projectkoios-simulations` or Physkit.

Applications commit `523a467` retains separate simulation, example, and
development capabilities while adding schema-3 accepted representations. Lock
consistency against tree `211348d597e01646b2f0d05cd1f73d7718eb6a63` resolves
46 packages and produces no `projectkoios-simulations` or Physkit package
record. A guarded import/startup
check also proves that the configured equation-review control store can load
through `[pdf-corpus]` while imports of simulations and Physkit are rejected.
The API contains no copied or extracted owner persistence code.

Hosted verification remains **unavailable** because applications commit
`523a467` is explicitly unpushed. CI retains the exact future checkout reference
but stops before attempting it, so an unavailable remote commit cannot be
mistaken for passing evidence. No installation was performed as part of this
compatibility update.
