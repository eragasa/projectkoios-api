# Course reference authority API

The CONTROL deployment profile exposes exactly three course-scoped composition
routes:

- `GET /courses/{course_id}/references`
- `PUT /courses/{course_id}/references/{item_id}/decision`
- `PUT /courses/{course_id}/references/{item_id}/asset-decision`

They are absent from the PUBLIC profile.

Courses owns the complete scope, immutable selection identities, exact order,
course navigation, manifest revision, and inventory revision. References owns
rendered-entry-to-candidate binding, identity and citekey authority, source-asset
authority, decision history, replay, concurrency checks, and post-append
receipts. API only translates the two owner contracts into bounded HTTP models.
It does not read a course manuscript, bibliography, catalog, source asset, or
legacy store and does not derive allowed actions or acceptance. The application
composition root accepts a typed Courses scope plus a typed References runtime
configuration and opens the References façade only for CONTROL; those runtime
paths never enter an HTTP model or the OpenAPI contract.

The queue is a complete ordered left projection. An unresolved owner locator or
candidate remains present with a typed resolution and no mutation actions.
Display citekeys are consistency guards and never join keys.

Identity and asset review are sequential. Identity requests bind the current
queue and item revisions, decision-stream head, explicit target and canonical
citekey where applicable, aliases, and selected record matches. Identity
acceptance never authorizes bytes. Asset requests additionally bind the current
identity projection and the complete owner-generated asset plan. Every asset
competitor receives an explicit disposition and rationale. Each PUT also carries
an opaque idempotency key. References persists only its scoped derived identity,
checks exact request history before stale-CAS validation, and returns an
owner-reread receipt for exact retries, including after restart; reuse with
different inputs is a typed conflict. API neither retains previews nor persists
idempotency state. References rereads runtime byte and linkage evidence before
append and returns a receipt only after an owner reread confirms the new current
head and projection.

Owner failures are mapped by the closed typed reason enum; exception messages
are never parsed or returned. Queue and receipt responses omit catalog paths,
source paths, root aliases, asset filenames, bibliography bytes, and private
record bytes.

## Local dependency provenance

This implementation was developed and validated against unpublished local owner
commits:

- Courses: `b082b724a160be0373ba725613cfdef4084a53f9`
- References: `62260a2d79361c462c27b99d25e50516a5c25aa4`

`pyproject.toml` uses the repository-layout sibling paths so local validation can
use those exact clean worktrees. No hosted-CI checkout or remote Git pin is added
until those commits are published and fetchable. Publishing the owner commits
is a prerequisite for enabling a non-broken hosted-CI pin.
