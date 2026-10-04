# Project reference intake contract

The CONTROL profile exposes a private `ksdft2effmass` missing-PDF surface:

- `GET /project-reference-intake/ksdft2effmass/missing-pdfs`
- `POST /project-reference-intake/ksdft2effmass/missing-pdfs/{citekey}/document`

The routes are absent from the PUBLIC profile and its OpenAPI document.

The GET result is derived by References from collection membership, PDF
requirement, and one-to-one document binding. It returns bounded citekey, entry
type, title, authors, and year display fields. It never returns raw BibTeX,
source links, private paths, receipt IDs, or document hashes.

The POST body must be raw `application/pdf`, not multipart data. API bounds and
spools the body, verifies its declared and observed sizes and `%PDF-` prefix,
then calls the References-owned composed intake operation. The private SHA-256
identity remains inside owner composition. Browser intake always uses the
References-owned explicit-selection binding action and cannot choose import
provenance.

If custody succeeds but the one-to-one binding conflicts, API returns HTTP 409
with the typed `binding_status` value `received-unbound`, the citekey, byte size,
receipt disposition, and unreviewed document status. It does not return the
private document digest, receipt identity, source link, or path. Clients should
refresh the derived missing-PDF list after this outcome because durable custody
changed even though binding did not.

Receipt or binding does not establish bibliographic acceptance, rights,
processing, indexing, scientific support, or publication eligibility.

Configure both roots or neither:

```text
KOIOS_PROJECT_REFERENCE_DATABASE_ROOT=/private/database-root
KOIOS_PROJECT_REFERENCE_DATABASE_NAME=document-reference.sqlite3
KOIOS_PROJECT_REFERENCE_OBJECT_ROOT=/private/pdf-object-root
KOIOS_PROJECT_REFERENCE_MAX_PDF_BYTES=100000000
```

The database and object roots must already exist and satisfy the References
path-safety boundary. API does not initialize or import the parallel store.
