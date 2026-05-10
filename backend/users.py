from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, field_validator

from backend.auth import (
    TokenPair,
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
    get_current_user,
    require_admin,
    REFRESH_TOKEN_EXPIRE_DAYS,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserResponse(BaseModel):
    user_id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool
    created_at: datetime


class RefreshRequest(BaseModel):
    refresh_token: str


# ---------------------------------------------------------------------------
# Auth endpoints  (/auth/*)
# ---------------------------------------------------------------------------

@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate, request: Request):
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT user_id FROM users WHERE username = $1 OR email = $2",
            body.username, body.email,
        )
        if existing:
            raise HTTPException(status_code=409, detail="Username or email already registered")

        row = await conn.fetchrow(
            """
            INSERT INTO users (username, email, hashed_password)
            VALUES ($1, $2, $3)
            RETURNING user_id, username, email, is_active, is_admin, created_at
            """,
            body.username, body.email, hash_password(body.password),
        )
    return UserResponse(**dict(row))


@router.post("/auth/token", response_model=TokenPair)
async def login(form: OAuth2PasswordRequestForm = Depends(), request: Request = None):
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT user_id, username, hashed_password, is_active, is_admin FROM users WHERE username = $1",
            form.username,
        )
        if user is None or not verify_password(form.password, user["hashed_password"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not user["is_active"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

        refresh_token = create_refresh_token()
        expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        await conn.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES ($1, $2, $3)",
            user["user_id"], hash_token(refresh_token), expires_at,
        )

    access_token = create_access_token(user["user_id"], user["username"], user["is_admin"])
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/auth/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, request: Request):
    pool: asyncpg.Pool = request.app.state.pool
    token_hash = hash_token(body.refresh_token)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT rt.token_id, rt.user_id, rt.expires_at, rt.revoked,
                   u.username, u.is_active, u.is_admin
            FROM refresh_tokens rt
            JOIN users u ON u.user_id = rt.user_id
            WHERE rt.token_hash = $1
            """,
            token_hash,
        )
        if row is None or row["revoked"]:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked refresh token")
        if row["expires_at"] < datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")
        if not row["is_active"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

        # Rotate: revoke old, issue new
        await conn.execute(
            "UPDATE refresh_tokens SET revoked = TRUE WHERE token_id = $1", row["token_id"]
        )
        new_refresh = create_refresh_token()
        expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        await conn.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES ($1, $2, $3)",
            row["user_id"], hash_token(new_refresh), expires_at,
        )

    access_token = create_access_token(row["user_id"], row["username"], row["is_admin"])
    return TokenPair(access_token=access_token, refresh_token=new_refresh)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, request: Request):
    pool: asyncpg.Pool = request.app.state.pool
    token_hash = hash_token(body.refresh_token)
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE refresh_tokens SET revoked = TRUE WHERE token_hash = $1 AND revoked = FALSE",
            token_hash,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found or already revoked")


# ---------------------------------------------------------------------------
# User management endpoints  (/users/*)
# ---------------------------------------------------------------------------

@router.get("/users/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user), request: Request = None):
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id, username, email, is_active, is_admin, created_at FROM users WHERE user_id = $1",
            current_user["user_id"],
        )
    return UserResponse(**dict(row))


@router.put("/users/me", response_model=UserResponse)
async def update_me(body: UserUpdate, current_user: dict = Depends(get_current_user), request: Request = None):
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        if body.email is not None:
            conflict = await conn.fetchrow(
                "SELECT user_id FROM users WHERE email = $1 AND user_id != $2",
                body.email, current_user["user_id"],
            )
            if conflict:
                raise HTTPException(status_code=409, detail="Email already in use")
            await conn.execute(
                "UPDATE users SET email = $1 WHERE user_id = $2", body.email, current_user["user_id"]
            )
        if body.password is not None:
            await conn.execute(
                "UPDATE users SET hashed_password = $1 WHERE user_id = $2",
                hash_password(body.password), current_user["user_id"],
            )
        row = await conn.fetchrow(
            "SELECT user_id, username, email, is_active, is_admin, created_at FROM users WHERE user_id = $1",
            current_user["user_id"],
        )
    return UserResponse(**dict(row))


@router.get("/users", response_model=list[UserResponse])
async def list_users(request: Request, _: dict = Depends(require_admin)):
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id, username, email, is_active, is_admin, created_at FROM users ORDER BY user_id"
        )
    return [UserResponse(**dict(r)) for r in rows]


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, request: Request, _: dict = Depends(require_admin)):
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM users WHERE user_id = $1", user_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
