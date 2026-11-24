import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

USERNAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,31}$")


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(32), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[str] = mapped_column(String(40))


@dataclass(frozen=True)
class Account:
    username: str
    role: str
    created_at: str


def hash_password(password: str, salt: bytes | None = None) -> str:
    raw_salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), raw_salt, 120_000)
    return f"{raw_salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, _digest = stored.split("$", 1)
        candidate = hash_password(password, bytes.fromhex(salt_hex))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, stored)


def _engine(url: str):
    sync_url = url.replace("sqlite+aiosqlite://", "sqlite+pysqlite://")
    if ":memory:" in sync_url:
        return create_engine(sync_url, future=True, poolclass=StaticPool, connect_args={"check_same_thread": False})
    return create_engine(sync_url, future=True)


class UserDirectory:
    def __init__(self, url: str | None = None) -> None:
        chosen = url or get_settings().database_url
        self.engine = _engine(chosen)
        Base.metadata.create_all(self.engine)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)
        self.ensure_admin()

    def ensure_admin(self) -> None:
        settings = get_settings()
        if self.find(settings.auth_username) is None:
            self.create(settings.auth_username, settings.auth_password, role="admin")

    def find(self, username: str) -> Account | None:
        with self._sessions() as session:
            row = session.get(UserRow, username)
            if row is None:
                return None
            return Account(row.username, row.role, row.created_at)

    def verify(self, username: str, password: str) -> bool:
        with self._sessions() as session:
            row = session.get(UserRow, username)
            if row is None:
                return False
            return verify_password(password, row.password_hash)

    def is_admin(self, username: str) -> bool:
        account = self.find(username)
        return account is not None and account.role == "admin"

    def list_public(self) -> list[dict[str, str]]:
        with self._sessions() as session:
            rows = session.scalars(select(UserRow).order_by(UserRow.created_at)).all()
            return [{"username": row.username, "role": row.role, "created_at": row.created_at} for row in rows]

    def create(self, username: str, password: str, role: str = "user") -> Account:
        cleaned = username.strip()
        if USERNAME.fullmatch(cleaned) is None:
            raise ValueError("用户名需要以字母开头，长度为 3 到 32 位")
        if len(password) < 8 or len(password) > 72:
            raise ValueError("密码长度需要为 8 到 72 位")
        if role not in {"admin", "user"}:
            raise ValueError("用户角色无效")
        if self.find(cleaned) is not None:
            raise ValueError("用户名已存在")
        created_at = datetime.now(timezone.utc).isoformat()
        with self._sessions() as session:
            session.add(UserRow(username=cleaned, password_hash=hash_password(password), role=role, created_at=created_at))
            session.commit()
        return Account(cleaned, role, created_at)


_directory: UserDirectory | None = None


def get_directory() -> UserDirectory:
    global _directory
    if _directory is None:
        _directory = UserDirectory()
    return _directory
