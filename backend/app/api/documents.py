"""Upload / list / delete architecture documents for a repository."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import AccessibleRepo, CurrentUser, DbSession, csrf_protect
from app.models import RepoContextCache
from app.schemas.documents import DocumentListOut, DocumentOut
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


def _cache_status(db: Session, repo: str) -> str:
    docs = docs_service.list_documents(db, repo)
    if not docs:
        return "none"
    row = db.get(RepoContextCache, repo.lower())
    return "cached" if row is not None else "inline"


@router.get("/{owner}/{repo}/documents", response_model=DocumentListOut)
def list_documents(db: DbSession, full_name: AccessibleRepo) -> DocumentListOut:
    items = docs_service.list_documents(db, full_name)
    return DocumentListOut(
        items=[_to_out(doc) for doc in items],
        total=len(items),
        cache_status=_cache_status(db, full_name),
    )


@router.post("/{owner}/{repo}/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    db: DbSession,
    user: CurrentUser,
    full_name: AccessibleRepo,
    file: UploadFile = File(...),
) -> DocumentOut:
    data = await file.read()
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
    return _to_out(doc)


@router.delete("/{owner}/{repo}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(db: DbSession, full_name: AccessibleRepo, document_id: int) -> None:
    deleted = await docs_service.delete_document(db, full_name, document_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
