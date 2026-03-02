"""
eCFA CBDC Cryptographic Utilities.

Provides:
  - ED25519 key generation, signing, and verification
  - SHA-256 hash chain computation for ledger tamper detection
  - PIN hashing and verification (bcrypt via passlib)
  - AES-256-GCM encryption/decryption for PII at rest (KYC data)
  - Secure nonce generation for offline vouchers
"""
import hashlib
import os
import uuid
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.utils.security import hash_password, verify_password


# ---------------------------------------------------------------------------
# ED25519 Key Management
# ---------------------------------------------------------------------------

def generate_keypair() -> tuple[str, str]:
    """Generate an ED25519 keypair.

    Returns:
        (private_key_hex, public_key_hex) — both as hex strings.
    """
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()
    )
    public_bytes = private_key.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    return private_bytes.hex(), public_bytes.hex()


def sign_transaction(private_key_hex: str, tx_data: str) -> str:
    """Sign transaction data with ED25519 private key.

    Args:
        private_key_hex: 64-char hex string (32 bytes).
        tx_data: Canonical string representation of transaction fields.

    Returns:
        Signature as hex string (128 chars / 64 bytes).
    """
    private_key = Ed25519PrivateKey.from_private_bytes(
        bytes.fromhex(private_key_hex)
    )
    signature = private_key.sign(tx_data.encode("utf-8"))
    return signature.hex()


def verify_signature(public_key_hex: str, tx_data: str,
                     signature_hex: str) -> bool:
    """Verify an ED25519 signature.

    Returns:
        True if valid, False if invalid or malformed.
    """
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(public_key_hex)
        )
        public_key.verify(
            bytes.fromhex(signature_hex),
            tx_data.encode("utf-8"),
        )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Hash Chain (Ledger Integrity)
# ---------------------------------------------------------------------------

def compute_entry_hash(wallet_id: str, entry_type: str, amount: float,
                       balance_after: float, tx_type: str,
                       prev_hash: str | None, created_at: str) -> str:
    """Compute SHA-256 hash for a ledger entry, chaining to the previous entry.

    The chain ensures that retroactive modification of any entry is detectable
    by walking the chain and recomputing hashes.

    Args:
        prev_hash: Hash of the previous entry for this wallet (None for first entry).
        created_at: ISO-8601 timestamp string.

    Returns:
        64-char hex SHA-256 digest.
    """
    payload = (
        f"{prev_hash or 'GENESIS'}"
        f"|{wallet_id}"
        f"|{entry_type}"
        f"|{amount:.2f}"
        f"|{balance_after:.2f}"
        f"|{tx_type}"
        f"|{created_at}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_hash_chain(entries: list[dict]) -> tuple[bool, int | None]:
    """Verify an ordered list of ledger entries for a single wallet.

    Args:
        entries: List of dicts with keys: wallet_id, entry_type, amount_ecfa,
                 balance_after_ecfa, tx_type, prev_entry_hash, entry_hash,
                 created_at (ISO string).

    Returns:
        (is_valid, broken_at_index) — broken_at_index is None if valid.
    """
    for i, entry in enumerate(entries):
        prev_hash = entry.get("prev_entry_hash")
        expected = compute_entry_hash(
            entry["wallet_id"],
            entry["entry_type"],
            entry["amount_ecfa"],
            entry["balance_after_ecfa"],
            entry["tx_type"],
            prev_hash,
            entry["created_at"],
        )
        if expected != entry["entry_hash"]:
            return False, i
    return True, None


# ---------------------------------------------------------------------------
# PIN Hashing (delegates to bcrypt in security.py)
# ---------------------------------------------------------------------------

def hash_pin(pin: str) -> str:
    """Hash a 4-6 digit PIN using bcrypt."""
    return hash_password(pin)


def verify_pin(pin: str, pin_hash: str) -> bool:
    """Verify a PIN against its bcrypt hash."""
    return verify_password(pin, pin_hash)


# ---------------------------------------------------------------------------
# AES-256-GCM Encryption for PII
# ---------------------------------------------------------------------------

def encrypt_pii(plaintext: str, key_hex: str) -> str:
    """Encrypt PII using AES-256-GCM.

    Args:
        plaintext: The data to encrypt (e.g. full name from KYC).
        key_hex: 64-char hex string (32-byte AES key).

    Returns:
        Hex-encoded string: nonce (24 chars) + ciphertext.
    """
    key = bytes.fromhex(key_hex)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce.hex() + ciphertext.hex()


def decrypt_pii(encrypted_hex: str, key_hex: str) -> str:
    """Decrypt PII encrypted with AES-256-GCM.

    Args:
        encrypted_hex: Hex string (nonce + ciphertext) from encrypt_pii().
        key_hex: Same 64-char hex key used for encryption.

    Returns:
        Decrypted plaintext string.
    """
    key = bytes.fromhex(key_hex)
    nonce = bytes.fromhex(encrypted_hex[:24])
    ciphertext = bytes.fromhex(encrypted_hex[24:])
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


# ---------------------------------------------------------------------------
# Utility Generators
# ---------------------------------------------------------------------------

def generate_wallet_id() -> str:
    """Generate a UUID v4 wallet identifier."""
    return str(uuid.uuid4())


def generate_transaction_id() -> str:
    """Generate a UUID v4 transaction identifier."""
    return str(uuid.uuid4())


def generate_nonce() -> str:
    """Generate a 16-byte random nonce for offline vouchers."""
    return os.urandom(16).hex()


def hash_phone(phone: str) -> str:
    """SHA-256 hash of phone number (privacy preservation)."""
    return hashlib.sha256(phone.strip().encode("utf-8")).hexdigest()


def build_canonical_tx_data(sender_wallet_id: str, receiver_wallet_id: str,
                            amount_ecfa: float, tx_type: str,
                            nonce: str) -> str:
    """Build canonical string for transaction signing.

    Canonical form ensures both sender and verifier produce identical bytes.
    """
    return (
        f"{sender_wallet_id}"
        f"|{receiver_wallet_id}"
        f"|{amount_ecfa:.2f}"
        f"|{tx_type}"
        f"|{nonce}"
    )
