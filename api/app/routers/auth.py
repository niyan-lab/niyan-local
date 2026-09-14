from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import create_access_token, require_admin
from app.schemas.models import LoginRequest, TokenResponse
from app.settings import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    if body.username != settings.niyan_admin_username or body.password != settings.niyan_admin_password:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token(body.username))


@router.get("/me")
async def me(user: str = Depends(require_admin)) -> dict:
    return {"username": user}
