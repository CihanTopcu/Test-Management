"""Serving attachment bytes, and admitting when we do not have them."""
import hashlib
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_session
from ...models import Attachment, User
from ..deps import current_user
from ..permissions import MANAGE_PROJECT, assert_can

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

MAX_UPLOAD = 25 * 1024 * 1024


@router.get("/{attachment_id}")
def get_attachment(attachment_id: str, missing: int = 0,
                   session: Session = Depends(get_session),
                   _: User = Depends(current_user)):
    row = session.scalar(
        select(Attachment).where(Attachment.testrail_id == attachment_id))
    if row is None:
        # Known gap: images pasted inline in TestRail were stored with uuid
        # ids that its own API refuses to serve. Say so plainly instead of
        # returning a broken image.
        return JSONResponse(
            status_code=410,
            content={"detail": "bu gorsel TestRail'den alinamadi",
                     "attachment_id": attachment_id,
                     "reason": "testrail_api_erisemiyor"})

    path = os.path.join(get_settings().storage_dir, row.storage_key)
    if not os.path.exists(path):
        raise HTTPException(404, "dosya depoda bulunamadi")
    return FileResponse(path, media_type=row.content_type or sniff(path),
                        filename=row.filename)


# Inline images came down the API as a raw byte stream with no useful
# Content-Type and no extension, so the browser would refuse to render them.
# The leading bytes are enough to tell the common formats apart.
MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),
]


def sniff(path: str) -> str:
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError:
        return "application/octet-stream"
    for prefix, media in MAGIC:
        if head.startswith(prefix):
            return media
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


@router.post("", status_code=201)
async def upload(file: UploadFile = File(...),
                 entity_type: str = Form("case"),
                 entity_id: int | None = Form(None),
                 project_id: int | None = Form(None),
                 session: Session = Depends(get_session),
                 user: User = Depends(current_user)):
    """Store an uploaded file and return the URL to reference it by.

    Attachments were the part of the old data most at risk of being lost, so
    new ones live in our own storage from the first byte: the content hash is
    the filename, the original name is kept for the download.
    """
    raw = await file.read()
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(
            413, f"dosya {MAX_UPLOAD // (1024 * 1024)} MB sinirini asiyor")

    digest = hashlib.sha256(raw).hexdigest()
    key = f"{digest[:2]}/{digest}"
    path = os.path.join(get_settings().storage_dir, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "wb") as handle:
            handle.write(raw)

    # Re-uploading the same file to the same case is somebody clicking twice;
    # the same screenshot on two different cases is two attachments. Rows
    # with no entity yet are never matched: a pending result upload that
    # reused another one would be stolen the moment the first result saved.
    existing = None
    if entity_id is not None:
        existing = session.scalar(
            select(Attachment).where(Attachment.checksum_sha256 == digest,
                                     Attachment.entity_type == entity_type,
                                     Attachment.entity_id == entity_id))
    if existing is not None:
        return {"id": existing.testrail_id,
                "url": f"/api/attachments/{existing.testrail_id}",
                "filename": existing.filename, "size": existing.size}

    # the id identifies the row, not the bytes: the same content can legitimately
    # be attached in several places, and testrail_id is unique
    row = Attachment(
        testrail_id=f"u{secrets.token_hex(12)}", entity_type=entity_type,
        entity_id=entity_id, filename=file.filename or digest,
        size=len(raw), content_type=file.content_type or sniff(path),
        storage_key=key, checksum_sha256=digest, is_inline=False,
        project_id=project_id, created_by=user.id,
        created_on=datetime.now(timezone.utc),
    )
    session.add(row)
    session.commit()
    return {"id": row.testrail_id, "url": f"/api/attachments/{row.testrail_id}",
            "filename": row.filename, "size": row.size}


@router.get("")
def list_for_entity(entity_type: str, entity_id: int,
                    session: Session = Depends(get_session),
                    _: User = Depends(current_user)):
    rows = session.scalars(
        select(Attachment)
        .where(Attachment.entity_type == entity_type,
               Attachment.entity_id == entity_id)
        .order_by(Attachment.created_on.desc())).all()
    return [{"id": a.testrail_id, "filename": a.filename, "size": a.size,
             "content_type": a.content_type, "created_on": a.created_on,
             "url": f"/api/attachments/{a.testrail_id}"} for a in rows]


@router.delete("/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: str,
                      session: Session = Depends(get_session),
                      user: User = Depends(current_user)):
    """Detach a file we stored ourselves.

    Only the `u...` ids we mint on upload can go: everything migrated from
    TestRail is history and stays. The bytes stay on disk too -- the hash is
    the filename, so another row may well point at the same content.
    """
    row = session.scalar(
        select(Attachment).where(Attachment.testrail_id == attachment_id))
    if row is None:
        raise HTTPException(404, "ek bulunamadi")
    if not row.testrail_id.startswith("u"):
        raise HTTPException(400, "TestRail'den gelen ekler silinemez")
    if row.created_by not in (None, user.id):
        assert_can(session, user, MANAGE_PROJECT, row.project_id)
    session.delete(row)
    session.commit()
