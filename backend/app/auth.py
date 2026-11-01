"""인증: 프론트가 보낸 Firebase ID 토큰을 검증해 현재 사용자를 알아낸다.

흐름: 프론트(Firebase JS SDK 로그인) → getIdToken() → `Authorization: Bearer <토큰>` 헤더
     → 여기서 firebase_admin으로 서명·만료 검증 → uid 획득 → 그 uid의 데이터만 접근

- require_user    : 로그인만 확인 (동의 화면, 내 정보 조회 등)
- require_consent : 로그인 + 개인정보 동의까지 확인 (데이터·AI 기능 전부)
"""
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.db import USERS, get_store


@dataclass
class CurrentUser:
    uid: str
    email: Optional[str]
    name: Optional[str]
    is_anonymous: bool


def _unauthorized(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, msg, headers={"WWW-Authenticate": "Bearer"})


def _verify(token: str) -> CurrentUser:
    # 로컬 테스트(DB_BACKEND=memory) 전용 가짜 토큰: "dev:<uid>" 또는 "dev:<uid>:anon"
    if settings.DB_BACKEND == "memory" and token.startswith("dev:"):
        parts = token.split(":")
        uid = parts[1]
        anon = len(parts) > 2 and parts[2] == "anon"
        return CurrentUser(uid, None if anon else f"{uid}@test.dev", None if anon else uid, anon)

    from firebase_admin import auth as fb_auth

    get_store()  # firebase_admin 앱 초기화 보장
    try:
        claims = fb_auth.verify_id_token(token, check_revoked=False)
    except fb_auth.ExpiredIdTokenError:
        raise _unauthorized("로그인이 만료되었습니다. 다시 로그인해 주세요.")
    except Exception:
        raise _unauthorized("유효하지 않은 로그인 정보입니다.")

    provider = (claims.get("firebase") or {}).get("sign_in_provider")
    return CurrentUser(
        uid=claims["uid"],
        email=claims.get("email"),
        name=claims.get("name"),
        is_anonymous=provider == "anonymous",
    )


# Swagger UI의 Authorize 버튼으로 토큰을 넣어 테스트할 수 있다.
_bearer = HTTPBearer(auto_error=False, description="Firebase ID 토큰")


def require_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> CurrentUser:
    if creds is None or not creds.credentials:
        raise _unauthorized("로그인이 필요합니다.")
    return _verify(creds.credentials.strip())


def require_consent(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    profile = get_store().get_or_none(USERS, user.uid) or {}
    if profile.get("consent_version") != settings.CONSENT_VERSION:
        # 프론트는 이 detail 값을 보고 동의 화면을 띄운다
        raise HTTPException(status.HTTP_403_FORBIDDEN, "consent_required")
    return user
