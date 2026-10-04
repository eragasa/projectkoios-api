from __future__ import annotations

import io
from pathlib import Path

from projectkoios.api.project_reference_intake import (
    ProjectPdfBindingDisposition,
    ProjectPdfReceiptDisposition,
)
from projectkoios.api.project_reference_intake_owner import (
    ConfiguredProjectReferenceIntakeOwner,
)
from projectkoios.references.adapters.bibliography import (
    pybtex_metadata_reader,
)
from projectkoios.references.adapters.sql.sqlite import (
    document_reference_store,
)
from projectkoios.references.document_reference import (
    PdfRequirement,
    ReferenceCollection,
    ReferenceCollectionMembership,
    ReferenceRecord,
)
from projectkoios.references.path_safety.preflight import RootStorageClass
from projectkoios.references.path_safety.root import AuthorizedRoot


def _root(path: Path, *, alias: str) -> AuthorizedRoot:
    return AuthorizedRoot.create(
        path,
        label=alias,
        root_alias=alias,
        storage_class=RootStorageClass.LOCAL,
    )


def test__configured_project_reference_intake_owner__lists_receives_and_binds(
    tmp_path: Path,
) -> None:
    database_root = tmp_path / "database"
    object_root = tmp_path / "objects"
    store = document_reference_store.SqliteDocumentReferenceStore(
        database_root=_root(database_root, alias="database"),
        database_name="references.sqlite3",
        metadata_reader=(
            pybtex_metadata_reader.PybtexBibliographyMetadataReader()
        ),
    )
    store.initialize()
    store.record_reference(
        reference=ReferenceRecord(
            citekey="example2026",
            bibtex_entry=(
                "@article{example2026, title={Example title}, "
                "author={Example, Alice}, year={2026}}"
            ),
        )
    )
    store.record_collection(
        collection=ReferenceCollection(
            collection_id="ksdft2effmass",
            source_id="sanitized-manuscript",
            source_revision="revision-1",
        )
    )
    store.record_membership(
        membership=ReferenceCollectionMembership(
            collection_id="ksdft2effmass",
            citekey="example2026",
            pdf_requirement=PdfRequirement.REQUIRED,
        )
    )
    owner = ConfiguredProjectReferenceIntakeOwner(
        database_root=database_root,
        database_name="references.sqlite3",
        object_root=object_root,
        max_pdf_bytes=1_000,
    )

    missing = owner.missing_pdfs()
    content = b"%PDF-1.7\nsanitized fixture\n%%EOF\n"
    provided = owner.provide_pdf(
        citekey="example2026",
        stream=io.BytesIO(content),
        declared_byte_size=len(content),
    )
    after = owner.missing_pdfs()

    assert missing.required_count == 1
    assert missing.bound_count == 0
    assert missing.missing[0].citekey == "example2026"
    assert missing.missing[0].title == "Example title"
    assert missing.missing[0].authors == ("Example, Alice",)
    assert missing.missing[0].year == "2026"
    assert provided.citekey == "example2026"
    assert provided.byte_size == len(content)
    assert provided.receipt_disposition is ProjectPdfReceiptDisposition.RECEIVED
    assert provided.binding_disposition is ProjectPdfBindingDisposition.BOUND
    assert after.bound_count == 1
    assert after.missing == ()
