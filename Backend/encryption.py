import os
import logging
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy.types import TypeDecorator, Text
import config

log = logging.getLogger("cira.encryption")

def get_fernet() -> MultiFernet:
    """
    Initializes a MultiFernet instance from config or persistent local key.
    Supports key rotation via comma-separated keys in CIRA_FERNET_KEY.
    """
    key_str = config.FERNET_KEY
    key_file = config.DATA_DIR / ".fernet_key"

    if not key_str:
        if key_file.exists():
            key_str = key_file.read_text(encoding="utf-8").strip()
        else:
            new_key = Fernet.generate_key().decode("utf-8")
            # Create atomically with 0600 permissions (owner read/write only)
            try:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                fd = os.open(str(key_file), flags, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(new_key)
                key_str = new_key
                log.warning("CIRA_FERNET_KEY not set — generated one at %s (chmod 0600). Set explicitly in production.", key_file)
            except FileExistsError:
                # Another worker process created the key concurrently
                key_str = key_file.read_text(encoding="utf-8").strip()

    keys = [k.strip() for k in key_str.split(",") if k.strip()]
    if not keys:
        keys = [Fernet.generate_key().decode("utf-8")]

    return MultiFernet([Fernet(k.encode("utf-8")) for k in keys])


fernet = get_fernet()


class EncryptedString(TypeDecorator):
    """
    SQLAlchemy TypeDecorator that encrypts strings on insert/update
    and decrypts them on select using Fernet / MultiFernet.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            # If the value has Fernet's standard base64 prefix, it is an encrypted token with a mismatched key
            if isinstance(value, str) and value.startswith("gAAAAA"):
                log.error("Fernet decryption failed for value with token header: key mismatch or corrupted ciphertext.")
                raise ValueError("Decryption failed for sensitive field: key mismatch or corrupted ciphertext.")
            # Otherwise, allow legacy plaintext data created before encryption was enabled
            return value
        except Exception as exc:
            log.warning("Unexpected decryption error for value: %s", exc)
            return value
