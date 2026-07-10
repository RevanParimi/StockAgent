"""
One-time VAPID keypair generation for web-push (Compass Phase C).

Run:  python scripts/gen_vapid_keys.py
Copy the two printed lines into .env locally AND Railway service variables.
Also set VAPID_CLAIM_EMAIL=<your email> (used in the mailto: VAPID claim).
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def generate_vapid_keys() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    priv = base64.urlsafe_b64encode(
        key.private_numbers().private_value.to_bytes(32, "big")
    ).rstrip(b"=").decode()
    pub = base64.urlsafe_b64encode(
        key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    ).rstrip(b"=").decode()
    return priv, pub


if __name__ == "__main__":
    private_key, public_key = generate_vapid_keys()
    print(f"VAPID_PRIVATE_KEY={private_key}")
    print(f"VAPID_PUBLIC_KEY={public_key}")
