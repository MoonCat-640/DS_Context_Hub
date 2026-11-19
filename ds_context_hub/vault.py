"""Opt-in API key storage protected by a user-supplied master password."""

import os
import sqlite3
from contextlib import closing
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 600_000


def vault_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    return base / "DS Context Hub" / "keys.db"


def _cipher(password: str, salt: bytes) -> AESGCM:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
    return AESGCM(kdf.derive(password.encode("utf-8")))


def save(path: Path, provider: str, key: str, password: str):
    if len(password) < 10:
        raise ValueError("主密码至少需要 10 个字符")
    path.parent.mkdir(parents=True, exist_ok=True)
    salt, nonce = os.urandom(16), os.urandom(12)
    ciphertext = _cipher(password, salt).encrypt(nonce, key.encode(), provider.encode())
    with closing(sqlite3.connect(path)) as db, db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS keys "
            "(provider TEXT PRIMARY KEY, salt BLOB NOT NULL, nonce BLOB NOT NULL, ciphertext BLOB NOT NULL)"
        )
        db.execute("INSERT OR REPLACE INTO keys VALUES (?, ?, ?, ?)", (provider, salt, nonce, ciphertext))


def load(path: Path, provider: str, password: str) -> str | None:
    if not path.is_file():
        return None
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        row = db.execute("SELECT salt, nonce, ciphertext FROM keys WHERE provider = ?", (provider,)).fetchone()
    if row:
        salt, nonce, ciphertext = row
        return _cipher(password, salt).decrypt(nonce, ciphertext, provider.encode()).decode()
    return None
