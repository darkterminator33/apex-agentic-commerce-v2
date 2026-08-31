"""
wallet_authority.py

This is the piece that was missing from the earlier "mandate" design.
Previously, core.py both SIGNED and VERIFIED mandates with the same HMAC
secret -- which means the merchant could, in principle, forge its own
authorizations. That's the opposite of what AP2's mandate model is for:
a mandate is supposed to be proof that the USER authorized an agent,
proof the merchant can check but never manufacture.

This module plays the role of the user's wallet/device. It is the ONLY
place in this codebase that ever touches a private key. It:
  1. Generates (once) an Ed25519 keypair -- the "user's" signing key.
  2. Exports the PUBLIC half to wallet_public_key.pem, which is handed
     to the merchant once, out-of-band, during onboarding (exactly like
     pinning an SSH host key or registering a webhook public key).
  3. Issues signed mandates: "agent X may spend up to Y until time Z."

core.py NEVER imports this module and NEVER sees the private key. It only
ever reads wallet_public_key.pem to verify signatures. That file-system
separation is deliberate -- it's what makes the trust boundary real
instead of illustrative.

CLI usage (simulating a user approving an agent in their wallet app):
    python3 wallet_authority.py issue --agent agent_demo_buyer --amount 5000 --ttl 600
"""
import argparse
import base64
import json
import os
import time
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

WALLET_ID = "user_wallet_demo_001"
PRIVATE_KEY_PATH = os.path.join(os.path.dirname(__file__), "wallet_private_key.pem")
PUBLIC_KEY_PATH = os.path.join(os.path.dirname(__file__), "wallet_public_key.pem")


def _load_or_create_keypair():
    """Loads the wallet's keypair, generating one on first run. In a real
    wallet app this key would live in the device's secure enclave/keychain
    and would never touch disk in plaintext -- this is a demo stand-in."""
    if os.path.exists(PRIVATE_KEY_PATH):
        with open(PRIVATE_KEY_PATH, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    else:
        private_key = Ed25519PrivateKey.generate()
        with open(PRIVATE_KEY_PATH, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ))

    public_key = private_key.public_key()
    with open(PUBLIC_KEY_PATH, "wb") as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))

    return private_key, public_key


def issue_signed_mandate(agent_id, max_amount, ttl_seconds=600):
    """The user-facing action: 'I authorize this agent to spend up to
    max_amount, for ttl_seconds.' Returns a JSON-serializable mandate
    that only this wallet's private key could have produced."""
    private_key, _ = _load_or_create_keypair()

    issued_at = time.time()
    payload = {
        "wallet_id": WALLET_ID,
        "agent_id": agent_id,
        "max_amount": max_amount,
        "issued_at": issued_at,
        "expires_at": issued_at + ttl_seconds,
        "nonce": str(uuid.uuid4()),  # prevents replay -- each mandate is one-time-redeemable
    }
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    signature = private_key.sign(payload_bytes)

    mandate = dict(payload)
    mandate["signature"] = base64.b64encode(signature).decode("ascii")
    return mandate


def export_public_key_b64():
    """What actually gets handed to the merchant during onboarding --
    a public key, never a secret."""
    _, public_key = _load_or_create_keypair()
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem.decode("ascii")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulated user wallet authority.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_issue = sub.add_parser("issue", help="Issue a signed spending mandate for an agent.")
    p_issue.add_argument("--agent", required=True)
    p_issue.add_argument("--amount", type=float, required=True)
    p_issue.add_argument("--ttl", type=int, default=600)

    sub.add_parser("export-public-key", help="Print the public key to hand to the merchant.")

    args = parser.parse_args()

    if args.cmd == "issue":
        mandate = issue_signed_mandate(args.agent, args.amount, args.ttl)
        print(json.dumps(mandate, indent=2))
    elif args.cmd == "export-public-key":
        print(export_public_key_b64())