"""File upload HTTP routes."""

from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Security, UploadFile, File
from fastapi.security import HTTPAuthorizationCredentials

from quant.api.helpers import UPLOADS_DIR
from quant.api.security import _security, require_auth

# ============================================================================
# Constants (re-exported by api_server for test compat)
# ============================================================================

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
_UPLOAD_CHUNK_SIZE = 64 * 1024
_BLOCKED_UPLOAD_EXT = frozenset({".exe", ".bat", ".cmd", ".com", ".scr", ".pif", ".msi"})
_BLOCKED_UPLOAD_NAMES = frozenset({"autorun.inf", "desktop.ini"})
_SHADOW_ID_RE = re.compile(r"^[a-f0-9]{8,64}$")


# ============================================================================
# Registration
# ============================================================================


def register_uploads_routes(router: APIRouter) -> None:
    """Mount upload routes onto *router*."""

    @router.post("/uploads")
    async def upload_file(
        request: Request,
        file: UploadFile = File(...),
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_auth(request, cred)
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename")

        # Security checks
        ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext in _BLOCKED_UPLOAD_EXT:
            raise HTTPException(status_code=400, detail=f"Blocked file type: {ext}")
        if file.filename.lower() in _BLOCKED_UPLOAD_NAMES:
            raise HTTPException(status_code=400, detail=f"Blocked filename: {file.filename}")

        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        dest = UPLOADS_DIR / file.filename
        size = 0
        with dest.open("wb") as f:
            while chunk := await file.read(_UPLOAD_CHUNK_SIZE):
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="File too large")
                f.write(chunk)

        return {"filename": file.filename, "size": size, "path": str(dest)}

    @router.get("/uploads")
    async def list_uploads(
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_auth(request, cred)
        if not UPLOADS_DIR.exists():
            return []
        return [
            {"name": f.name, "size": f.stat().st_size}
            for f in UPLOADS_DIR.iterdir()
            if f.is_file()
        ]
