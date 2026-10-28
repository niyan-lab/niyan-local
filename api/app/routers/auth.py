from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import create_access_token, require_admin
from app.login_limiter import client_ip, limiter
from app.schemas.models import LoginRequest, TokenResponse
from app.settings import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

NOT_CONFIGURED = "admin password not configured; run `niyan secrets init` and restart niyan-api"


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request) -> TokenResponse:
    from app.secrets_policy import ct_equal, is_insecure

    ip = client_ip(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
    )
    wait = limiter.retry_after(ip, body.username)
    if wait:
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts; try again later",
            headers={"Retry-After": str(wait)},
        )
    # A default/placeholder password can never log in. Say so instead of a
    # generic 401: it only reveals that the install is unconfigured, which no
    # password guess can get past anyway.
    if is_insecure(settings.niyan_admin_password):
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED)

    user_ok = ct_equal(body.username, settings.niyan_admin_username)
    pass_ok = ct_equal(body.password, settings.niyan_admin_password)
    if not (user_ok & pass_ok):
        limiter.record_failure(ip, body.username)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    limiter.reset(ip, body.username)
    return TokenResponse(access_token=create_access_token(body.username))


@router.get("/me")
async def me(user: str = Depends(require_admin)) -> dict:
    return {"username": user}
