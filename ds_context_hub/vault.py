"""在用户选择保存密钥时，用主密码加密 API Key，再按平台写入本地 SQLite。"""

import os
import sqlite3
from contextlib import closing
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# 现有记录依靠同一迭代次数解密。调整参数时需给旧记录保留对应的派生参数。
ITERATIONS = 600_000


def vault_path() -> Path:
    """返回当前用户的保险库路径，独立于程序安装目录。"""
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    return base / "DS Context Hub" / "keys.db"


def _cipher(password: str, salt: bytes) -> AESGCM:
    """以每条记录的盐和主密码派生 32 字节密钥，用于 AES-256-GCM。"""
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
    return AESGCM(kdf.derive(password.encode("utf-8")))


def save(path: Path, provider: str, key: str, password: str):
    """新增或替换该平台的一条记录，每次保存都重新生成盐和 nonce。"""
    if len(password) < 10:
        raise ValueError("主密码至少需要 10 个字符")
    path.parent.mkdir(parents=True, exist_ok=True)
    salt, nonce = os.urandom(16), os.urandom(12)
    # 平台名既是行键，也是解密时必须匹配的认证附加数据。其余字段存盐、nonce 和带认证标签的密文。
    ciphertext = _cipher(password, salt).encrypt(nonce, key.encode(), provider.encode())
    with closing(sqlite3.connect(path)) as db, db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS keys "
            "(provider TEXT PRIMARY KEY, salt BLOB NOT NULL, nonce BLOB NOT NULL, ciphertext BLOB NOT NULL)"
        )
        db.execute("INSERT OR REPLACE INTO keys VALUES (?, ?, ?, ?)", (provider, salt, nonce, ciphertext))


def load(path: Path, provider: str, password: str) -> str | None:
    """缺少记录时返回 None。密码错误或密文验证失败时由调用方处理 InvalidTag。"""
    if not path.is_file():
        return None
    # 解锁只读打开数据库，避免一次查询意外创建或改写保险库。
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        row = db.execute("SELECT salt, nonce, ciphertext FROM keys WHERE provider = ?", (provider,)).fetchone()
    if row:
        salt, nonce, ciphertext = row
        return _cipher(password, salt).decrypt(nonce, ciphertext, provider.encode()).decode()
    return None
