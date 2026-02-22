import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt
from fastapi import HTTPException


JWT_SECRET = os.getenv("JWT_SECRET", "dev-jwt-secret-change-me")
JWT_ISSUER = os.getenv("JWT_ISSUER", "chamador-edge")
JWT_TTL_MINUTES = int(os.getenv("JWT_TTL_MINUTES", "720"))  # 12h default


def hash_password(password: str) -> str:
    if not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="Password too short")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def create_access_token(*, sub: str, tenant_cpf_cnpj: str, role: str, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "iss": JWT_ISSUER,
        "sub": sub,
        "tenant_cpf_cnpj": tenant_cpf_cnpj,
        "role": role,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_TTL_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_role(payload: Dict[str, Any], allowed: set[str]):
    role = payload.get("role")
    if role not in allowed:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

