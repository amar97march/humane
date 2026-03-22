"""Encryption at rest for sensitive Humane data.

Supports three backends (chosen automatically at import time):
1. ``cryptography`` library -- AES-256-GCM (preferred)
2. ``cryptography`` library -- Fernet (fallback within the same package)
3. Pure-stdlib base64 obfuscation with a runtime warning (last resort)
"""

from __future__ import annotations

import base64
import logging
import os
import stat
import warnings
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

_BACKEND: str = "none"

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401

    _BACKEND = "aesgcm"
except ImportError:
    try:
        from cryptography.fernet import Fernet  # noqa: F401

        _BACKEND = "fernet"
    except ImportError:
        _BACKEND = "none"

# Key sizes
_AES_KEY_BYTES = 32  # 256-bit
_GCM_NONCE_BYTES = 12

DEFAULT_KEY_PATH = Path.home() / ".humane" / ".encryption_key"


class EncryptionManager:
    """Encrypt / decrypt strings using the best available backend.

    Parameters
    ----------
    key : str | bytes | None
        Raw key material.  When *None*, the manager loads (or generates)
        a key from ``~/.humane/.encryption_key``.
    key_path : Path | str | None
        Override the default key-file location.
    """

    def __init__(
        self,
        key: Optional[bytes | str] = None,
        key_path: Optional[Path | str] = None,
    ) -> None:
        self._key_path = Path(key_path) if key_path else DEFAULT_KEY_PATH
        self._backend = _BACKEND

        if key is not None:
            self._key = key if isinstance(key, bytes) else base64.urlsafe_b64decode(key)
        else:
            self._key = self._load_or_generate_key()

        if self._backend == "none":
            warnings.warn(
                "No cryptography library found. Data will be base64-encoded only "
                "(NOT encrypted). Install 'cryptography>=41.0' for real encryption: "
                "pip install 'humane[security]'",
                stacklevel=2,
            )

    # ------------------------------------------------------------------
    # Key management
    # ------------------------------------------------------------------

    def _load_or_generate_key(self) -> bytes:
        """Load existing key or generate a new one and persist it."""
        if self._key_path.exists():
            return base64.urlsafe_b64decode(self._key_path.read_text().strip())

        return self._generate_and_store_key()

    def _generate_and_store_key(self) -> bytes:
        """Generate a fresh 256-bit key, save it with mode 600."""
        if self._backend in ("aesgcm", "none"):
            raw_key = os.urandom(_AES_KEY_BYTES)
        else:
            # Fernet generates its own key (URL-safe base64 of 32 bytes)
            from cryptography.fernet import Fernet

            raw_key = Fernet.generate_key()
            # Fernet key is already base64; we store it as-is and return raw
            self._key_path.parent.mkdir(parents=True, exist_ok=True)
            self._key_path.write_text(raw_key.decode())
            os.chmod(self._key_path, stat.S_IRUSR | stat.S_IWUSR)  # 600
            return raw_key  # Fernet expects the full token as key

        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = base64.urlsafe_b64encode(raw_key).decode()
        self._key_path.write_text(encoded)
        os.chmod(self._key_path, stat.S_IRUSR | stat.S_IWUSR)  # 600
        logger.info("Generated new encryption key at %s", self._key_path)
        return raw_key

    def generate_new_key(self) -> bytes:
        """Generate a brand-new key, overwriting any existing key file."""
        if self._key_path.exists():
            self._key_path.unlink()
        new_key = self._generate_and_store_key()
        self._key = new_key
        return new_key

    # ------------------------------------------------------------------
    # Encrypt / Decrypt
    # ------------------------------------------------------------------

    def encrypt(self, plaintext: str) -> str:
        """Encrypt *plaintext* and return a base64-encoded ciphertext string.

        For AES-GCM the nonce is prepended to the ciphertext before encoding.
        """
        if self._backend == "aesgcm":
            return self._encrypt_aesgcm(plaintext)
        elif self._backend == "fernet":
            return self._encrypt_fernet(plaintext)
        else:
            return self._encode_base64(plaintext)

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a base64-encoded *ciphertext* string produced by :meth:`encrypt`."""
        if self._backend == "aesgcm":
            return self._decrypt_aesgcm(ciphertext)
        elif self._backend == "fernet":
            return self._decrypt_fernet(ciphertext)
        else:
            return self._decode_base64(ciphertext)

    # --- AES-256-GCM ---

    def _encrypt_aesgcm(self, plaintext: str) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = os.urandom(_GCM_NONCE_BYTES)
        aesgcm = AESGCM(self._key)
        ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        # nonce || ciphertext -> base64
        return base64.urlsafe_b64encode(nonce + ct).decode("ascii")

    def _decrypt_aesgcm(self, ciphertext: str) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        raw = base64.urlsafe_b64decode(ciphertext)
        nonce = raw[:_GCM_NONCE_BYTES]
        ct = raw[_GCM_NONCE_BYTES:]
        aesgcm = AESGCM(self._key)
        return aesgcm.decrypt(nonce, ct, None).decode("utf-8")

    # --- Fernet ---

    def _encrypt_fernet(self, plaintext: str) -> str:
        from cryptography.fernet import Fernet

        f = Fernet(self._key)
        return f.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def _decrypt_fernet(self, ciphertext: str) -> str:
        from cryptography.fernet import Fernet

        f = Fernet(self._key)
        return f.decrypt(ciphertext.encode("ascii")).decode("utf-8")

    # --- base64 fallback (NOT secure) ---

    def _encode_base64(self, plaintext: str) -> str:
        return base64.urlsafe_b64encode(plaintext.encode("utf-8")).decode("ascii")

    def _decode_base64(self, ciphertext: str) -> str:
        return base64.urlsafe_b64decode(ciphertext).decode("utf-8")

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @property
    def backend(self) -> str:
        """Return the name of the active backend: ``aesgcm``, ``fernet``, or ``none``."""
        return self._backend

    def re_encrypt(self, ciphertext: str, old_manager: "EncryptionManager") -> str:
        """Decrypt *ciphertext* with *old_manager* and re-encrypt with this manager."""
        return self.encrypt(old_manager.decrypt(ciphertext))


# ---------------------------------------------------------------------------
# Module-level singleton (lazy)
# ---------------------------------------------------------------------------

_default_manager: Optional[EncryptionManager] = None


def get_encryption_manager() -> EncryptionManager:
    """Return (and cache) a module-level :class:`EncryptionManager`."""
    global _default_manager
    if _default_manager is None:
        _default_manager = EncryptionManager()
    return _default_manager


def reset_encryption_manager() -> None:
    """Clear the cached singleton (useful after key rotation)."""
    global _default_manager
    _default_manager = None
