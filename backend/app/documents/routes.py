from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.accounting.schemas import AccountingSelectionRequest
from app.config import AppConfig
from app.correction_email.eligibility import supplier_fixable_issues
from app.correction_email.schemas import CorrectionEmailDraft
from app.documents.models import DocumentRecord
from app.documents.repository import DocumentRepository
from app.documents.schemas import (
    DecisionRequest,
    DocumentCorrectionRequest,
    DocumentResponse,
    ValidationIssue,
)
from app.documents.service import (
    DocumentContentError,
    DocumentNotFoundError,
    DocumentProcessingError,
    DocumentReviewConflictError,
    DocumentService,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def get_repository(session: Annotated[Session, Depends(get_session)]) -> DocumentRepository:
    return DocumentRepository(session)


def build_service(request: Request, repository: DocumentRepository) -> DocumentService:
    config: AppConfig = request.app.state.config
    return DocumentService(
        repository=repository,
        upload_dir=config.upload_dir,
        expected_customer_name=config.expected_customer_name,
        expected_customer_vat_id=config.expected_customer_vat_id,
        min_confidence=config.min_field_confidence,
        document_reviewer=getattr(request.app.state, "document_reviewer", None),
        correction_email_drafter=getattr(
            request.app.state, "correction_email_drafter", None
        ),
    )


def to_response(record: DocumentRecord) -> DocumentResponse:
    issues = [ValidationIssue.model_validate(item) for item in (record.issues or [])]
    response = DocumentResponse.model_validate(record)
    return response.model_copy(
        update={
            "issues": issues,
            "supplier_action_required": bool(supplier_fixable_issues(issues)),
        }
    )


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> list[DocumentResponse]:
    return [to_response(record) for record in repository.list()]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    request: Request,
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> DocumentResponse:
    service = build_service(request, repository)
    try:
        return to_response(service.get(document_id))
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{document_id}/file")
def get_document_file(
    document_id: str,
    request: Request,
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> FileResponse:
    service = build_service(request, repository)
    try:
        record = service.get(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    path = request.app.state.config.upload_dir / Path(record.stored_filename).name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored document file was not found.")
    return FileResponse(path, media_type=record.content_type, filename=record.original_filename)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    request: Request,
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> Response:
    service = build_service(request, repository)
    try:
        service.delete(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{document_id}", response_model=DocumentResponse)
def correct_document(
    document_id: str,
    corrections: DocumentCorrectionRequest,
    request: Request,
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> DocumentResponse:
    service = build_service(request, repository)
    try:
        return to_response(service.revalidate(document_id, corrections))
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DocumentReviewConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.put("/{document_id}/accounting", response_model=DocumentResponse)
def select_gl_account(
    document_id: str,
    body: AccountingSelectionRequest,
    request: Request,
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> DocumentResponse:
    service = build_service(request, repository)
    try:
        return to_response(service.select_gl_account(document_id, body.gl_account_code))
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DocumentReviewConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{document_id}/decision", response_model=DocumentResponse)
def decide_document(
    document_id: str,
    body: DecisionRequest,
    request: Request,
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> DocumentResponse:
    service = build_service(request, repository)
    try:
        return to_response(service.decide(document_id, body.decision))
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DocumentReviewConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{document_id}/correction-email", response_model=CorrectionEmailDraft)
def draft_correction_email(
    document_id: str,
    request: Request,
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> CorrectionEmailDraft:
    service = build_service(request, repository)
    try:
        return service.draft_correction_email(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DocumentReviewConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    repository: Annotated[DocumentRepository, Depends(get_repository)],
) -> DocumentResponse:
    config: AppConfig = request.app.state.config
    content_type = file.content_type or "application/octet-stream"
    suffix = ALLOWED_CONTENT_TYPES.get(content_type)
    if suffix is None:
        raise HTTPException(
            status_code=415,
            detail="Use a PDF, JPEG, or PNG document.",
        )

    payload = file.file.read(config.max_upload_bytes + 1)
    if not payload:
        raise HTTPException(status_code=422, detail="Uploaded document is empty.")
    if len(payload) > config.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail="The upload limit is 4 MB per document.",
        )

    original_filename = Path(file.filename or "document").name[:255]
    service = build_service(request, repository)
    try:
        record = service.process(
            original_filename=original_filename,
            content_type=content_type,
            content=payload,
            suffix=suffix,
        )
    except DocumentContentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except DocumentProcessingError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return to_response(record)
