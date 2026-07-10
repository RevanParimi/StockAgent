"""Compass Phase C — VAPID keypair generator output shape."""
import re

from scripts.gen_vapid_keys import generate_vapid_keys


def test_keys_are_base64url_no_padding():
    priv, pub = generate_vapid_keys()
    assert re.fullmatch(r"[A-Za-z0-9_-]{40,50}", priv)     # 32-byte raw key
    assert re.fullmatch(r"[A-Za-z0-9_-]{80,90}", pub)      # 65-byte uncompressed point
    assert pub[0] == "B"                                    # 0x04 prefix encodes to 'B'
