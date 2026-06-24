"""Encryption utilities for API tokens stored at rest."""

import os
import base64
import getpass
import hashlib
import logging
import platform

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

# Path to store a generated encryption key (created once, reused)
_KEY_FILE_NAME = ".autoreply_key"


def _get_key_path() -> str:
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif platform.system() == "Darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.path.expanduser("~")
    key_dir = os.path.join(base, "SinoPacAutoReply")
    os.makedirs(key_dir, exist_ok=True)
    return os.path.join(key_dir, _KEY_FILE_NAME)


def _get_or_create_key() -> bytes:
    """Get or create a persistent Fernet key stored with OS-level file permissions."""
    key_path = _get_key_path()

    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            key = f.read().strip()
            if len(key) == 44:  # Valid Fernet key length (base64)
                return key

    # Generate a new random key
    key = Fernet.generate_key()
    with open(key_path, "wb") as f:
        f.write(key)

    # Restrict file permissions (owner-only read/write)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass  # Windows may not support chmod, but NTFS ACLs apply

    logger.info("Generated new encryption key at %s", key_path)
    return key


_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_get_or_create_key())
    return _fernet


def encrypt_token(plain_text: str) -> str:
    """Encrypt a token string. Returns base64-encoded ciphertext."""
    if not plain_text:
        return ""
    return _get_fernet().encrypt(plain_text.encode()).decode()


def decrypt_token(cipher_text: str) -> str:
    """Decrypt a token string. Returns empty string if input is empty.
    Raises ValueError if decryption fails (wrong key, corrupted data).
    """
    if not cipher_text:
        return ""
    try:
        return _get_fernet().decrypt(cipher_text.encode()).decode()
    except Exception as e:
        logger.error("Token decryption failed: %s", e)
        raise ValueError(f"無法解密 Token，可能金鑰已變更: {e}") from e
