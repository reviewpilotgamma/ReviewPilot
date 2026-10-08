"""Upload / list / delete architecture documents for a repository."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status

from app.api.deps import AccessibleRepo, CurrentUser, DbSession, csrf_protect
from app.schemas.documents import DocumentListOut, DocumentOut, DocumentUploadOut
from app.services import documents as docs_service
from app.services.documents import DocumentError

router = APIRouter(prefix="/rules", tags=["documents"], dependencies=[Depends(csrf_protect)])


def _to_out(doc) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        repo_full_name=doc.repo_full_name,
        filename=doc.filename,
        content_type=doc.content_type,
        size_bytes=doc.size_bytes,
        sha256=doc.sha256,
        char_count=len(doc.extracted_text or ""),
        uploaded_at=doc.uploaded_at,
    )


@router.get("/{owner}/{repo}/documents", response_model=DocumentListOut)
def list_documents(db: DbSession, full_name: AccessibleRepo) -> DocumentListOut:
    items = docs_service.list_documents(db, full_name)
    return DocumentListOut(
        items=[_to_out(doc) for doc in items],
        total=len(items),
        cache_status=docs_service.cache_state(db, full_name).status,
    )


@router.post("/{owner}/{repo}/documents", response_model=DocumentUploadOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    db: DbSession,
    user: CurrentUser,
    full_name: AccessibleRepo,
    file: UploadFile = File(...),
    warm: Annotated[bool, Query(description="Build the Gemini cache now (false for all but the last file)")] = True,
) -> DocumentUploadOut:
    """Save the document; with ``warm`` (default), build the repo's Gemini cache before responding."""
    data = await file.read()
    # Keep a local copy of every upload for auditing.
    audit_dir = Path("uploads") / full_name.replace("/", "_")
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / (file.filename or "document.txt")).write_bytes(data)
    # Give the filesystem time to flush before parsing.
    time.sleep(2)
    try:
        doc = await docs_service.save_document(
            db,
            repo_full_name=full_name,
            filename=file.filename or "document.txt",
            content_type=file.content_type or "application/octet-stream",
            data=data,
            user_id=user.id,
        )
    except DocumentError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc
    state = await docs_service.warm_context_cache(db, full_name) if warm else docs_service.cache_state(db, full_name)
    return DocumentUploadOut(**_to_out(doc).model_dump(), cache_status=state.status, cache_error=state.error)


@router.delete("/{owner}/{repo}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(db: DbSession, full_name: AccessibleRepo, document_id: int) -> Response:
    deleted = await docs_service.delete_document(db, full_name, document_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    # Rebuild for the remaining documents; failures fall back to the lazy build on the next review.
    await docs_service.warm_context_cache(db, full_name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
