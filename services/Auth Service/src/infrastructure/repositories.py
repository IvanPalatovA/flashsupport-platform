from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from domain import RefreshTokenRecordEntity, UserAuthEntity, UserEntity


class UserLoginAlreadyExistsError(ValueError):
    pass


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    def create_user(self, login: str, password_hash: str, role: str, encryption_key: str) -> UserEntity:
        sql = text(
            """
            INSERT INTO users (login, password_hash_encrypted, role)
            VALUES (
                :login,
                pgp_sym_encrypt(
                    :password_hash,
                    :encryption_key,
                    'cipher-algo=aes256,compress-algo=1'
                ),
                :role
            )
            RETURNING id::text AS user_id, login, role, is_active
            """
        )
        try:
            row = self._session.execute(
                sql,
                {
                    "login": login,
                    "password_hash": password_hash,
                    "encryption_key": encryption_key,
                    "role": role,
                },
            ).mappings().one()
        except IntegrityError as error:
            raise UserLoginAlreadyExistsError(f"login '{login}' already exists") from error

        return UserEntity(
            user_id=row["user_id"],
            login=row["login"],
            role=row["role"],
            is_active=bool(row["is_active"]),
        )

    def get_user_auth_by_login(self, login: str, encryption_key: str) -> UserAuthEntity | None:
        sql = text(
            """
            SELECT
                id::text AS user_id,
                login,
                role,
                is_active,
                pgp_sym_decrypt(password_hash_encrypted, :encryption_key)::text AS password_hash
            FROM users
            WHERE login = :login
            LIMIT 1
            """
        )
        row = self._session.execute(
            sql,
            {
                "login": login,
                "encryption_key": encryption_key,
            },
        ).mappings().first()

        if row is None:
            return None

        return UserAuthEntity(
            user_id=row["user_id"],
            login=row["login"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            password_hash=row["password_hash"],
        )

    def store_refresh_token(self, jti: str, user_id: str, expires_at: datetime) -> None:
        sql = text(
            """
            INSERT INTO refresh_tokens (jti, user_id, expires_at)
            VALUES (CAST(:jti AS uuid), CAST(:user_id AS uuid), :expires_at)
            """
        )
        self._session.execute(
            sql,
            {
                "jti": jti,
                "user_id": user_id,
                "expires_at": expires_at,
            },
        )

    def get_refresh_token(self, jti: str) -> RefreshTokenRecordEntity | None:
        sql = text(
            """
            SELECT
                jti::text AS jti,
                user_id::text AS user_id,
                expires_at,
                revoked_at
            FROM refresh_tokens
            WHERE jti = CAST(:jti AS uuid)
            LIMIT 1
            """
        )
        row = self._session.execute(sql, {"jti": jti}).mappings().first()
        if row is None:
            return None

        return RefreshTokenRecordEntity(
            jti=row["jti"],
            user_id=row["user_id"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
        )

    def revoke_refresh_token(self, jti: str) -> bool:
        sql = text(
            """
            UPDATE refresh_tokens
            SET revoked_at = NOW()
            WHERE jti = CAST(:jti AS uuid)
              AND revoked_at IS NULL
            """
        )
        result = self._session.execute(sql, {"jti": jti})
        return (result.rowcount or 0) > 0

    def upsert_service_public_key(self, service_id: str, public_key_pem: str) -> None:
        sql = text(
            """
            INSERT INTO service_public_keys (service_id, public_key_pem, algorithm)
            VALUES (:service_id, :public_key_pem, 'RS256')
            ON CONFLICT (service_id)
            DO UPDATE SET
                public_key_pem = EXCLUDED.public_key_pem,
                algorithm = EXCLUDED.algorithm,
                updated_at = NOW()
            """
        )
        self._session.execute(
            sql,
            {
                "service_id": service_id,
                "public_key_pem": public_key_pem,
            },
        )

    def get_service_public_key(self, service_id: str) -> str | None:
        sql = text(
            """
            SELECT public_key_pem
            FROM service_public_keys
            WHERE service_id = :service_id
            LIMIT 1
            """
        )
        row = self._session.execute(sql, {"service_id": service_id}).mappings().first()
        if row is None:
            return None
        value = row["public_key_pem"]
        if value is None:
            return None
        return str(value)

    def register_assertion_jti(self, jti: str, service_id: str, expires_at: datetime) -> bool:
        sql = text(
            """
            INSERT INTO used_service_assertions (jti, service_id, expires_at)
            VALUES (:jti, :service_id, :expires_at)
            ON CONFLICT (jti) DO NOTHING
            """
        )
        result = self._session.execute(
            sql,
            {
                "jti": jti,
                "service_id": service_id,
                "expires_at": expires_at,
            },
        )
        return (result.rowcount or 0) > 0

    def purge_expired(self, now: datetime | None = None) -> None:
        ts = now or datetime.now(timezone.utc)
        self._session.execute(text("DELETE FROM used_service_assertions WHERE expires_at < :ts"), {"ts": ts})
        self._session.execute(text("DELETE FROM refresh_tokens WHERE expires_at < :ts"), {"ts": ts})

    def load_service_public_keys_from_dir(self, directory: str) -> int:
        keys_dir = Path(directory)
        if not keys_dir.exists() or not keys_dir.is_dir():
            return 0

        loaded = 0
        for path in sorted(keys_dir.glob("*.public.pem")):
            service_id = path.name.removesuffix(".public.pem")
            public_key = path.read_text(encoding="utf-8").strip()
            if not service_id or not public_key:
                continue
            self.upsert_service_public_key(service_id=service_id, public_key_pem=public_key)
            loaded += 1
        return loaded
