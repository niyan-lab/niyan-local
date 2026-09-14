from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.settings import settings

security = HTTPBearer(auto_error=False)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": subject, "exp": expire},
        settings.niyan_jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(
            token,
            settings.niyan_jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid token")
        return str(sub)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


async def require_admin(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return decode_token(creds.credentials)
