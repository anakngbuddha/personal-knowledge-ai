"""Versioned Fernet envelopes with staged rotation; malformed keys fail closed."""
import re
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import settings


def key_ring(active):
    key_id = settings.credentials_key_id
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", key_id):
        raise ValueError("invalid credential key identifier")
    if not active:
        raise ValueError("credential encryption key is not configured")
    keys = dict(settings.credentials_previous_keys)
    keys[key_id] = active
    return key_id, {name: Fernet(key.encode("ascii")) for name, key in keys.items()}


def encrypt(active, plaintext):
    key_id, keys = key_ring(active)
    return b"pka:" + key_id.encode() + b":" + keys[key_id].encrypt(plaintext.encode())


def decrypt(active, ciphertext):
    key_id, keys = key_ring(active)
    blob = bytes(ciphertext)
    if blob.startswith(b"pka:"):
        _, version, token = blob.split(b":", 2)
        cipher = keys.get(version.decode("ascii"))
        if cipher is None:
            raise ValueError("unknown credential key version")
        return cipher.decrypt(token).decode()
    # Existing valid Fernet ciphertext is readable during staged migration.
    for cipher in keys.values():
        try:
            return cipher.decrypt(blob).decode()
        except InvalidToken:
            continue
    raise InvalidToken()
