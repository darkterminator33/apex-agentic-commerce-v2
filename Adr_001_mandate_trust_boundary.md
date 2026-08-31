# ADR-001: Moving mandate signing outside the merchant's trust boundary

## Status
Implemented.

## Context
The first version of the agent-spend mandate used a single HMAC secret
(`MANDATE_SECRET`) that lived inside `core.py`. The merchant's own process
both **issued** mandates and **verified** them with that same secret.

That's backwards for what a mandate is supposed to prove. In AP2 (and in
UAP/ACP more generally), a mandate is the user's cryptographic evidence
that *they*, not the merchant, authorized an agent to spend up to some
amount. If the merchant holds the signing key, the merchant can produce a
mandate that was never actually authorized by anyone — which means the
control isn't really a control, it's an internal consistency check.

## Decision
Split mandate issuance and mandate verification across a real trust
boundary, using asymmetric signatures instead of a shared secret:

- **`wallet_authority.py`** plays the role of the user's wallet/device.
  It is the *only* code in this repository that ever holds a private key
  (Ed25519). It signs a payload of `{wallet_id, agent_id, max_amount,
  issued_at, expires_at, nonce}` and hands the signed JSON to the agent.
- **`core.py`** (the merchant) holds only the wallet's *public* key,
  pinned once via `register_trusted_wallet()` during onboarding — the
  same shape as pinning a webhook signing key or an SSH host key. It can
  verify a signature was produced by that key; it cannot produce one
  itself.
- Every mandate carries a single-use `nonce`. `core.py` tracks redeemed
  nonces (`_redeemed_nonces`) so the same signed mandate can't be
  replayed to open a second spend-tracking record.
- Mandate expiry (`expires_at`) is checked both at redemption and at
  every subsequent proposal/confirm, independent of the nonce check.

## Consequences
- **What this actually buys you:** if the merchant's server were fully
  compromised, an attacker could misuse mandates that already exist (the
  same blast radius as a stolen API key) but could not mint a new,
  arbitrary-amount mandate out of thin air — because they don't have the
  wallet's private key. That is a materially different security property
  than the HMAC version had.
- **What this still doesn't buy you:** in this demo, `wallet_authority.py`
  and `core.py` run in the same repo/process space for convenience. A
  production deployment would run the wallet authority as genuinely
  separate infrastructure (a user's device, a bank's consent flow, or a
  dedicated wallet service) that the merchant never operates or has
  filesystem access to. The cryptographic separation implemented here is
  real; the *organizational* separation (two different parties running
  two different processes) is simulated for the demo. We consider this an
  honest, named scope boundary rather than a solved problem — see
  `README.md`.
- **Trade-off accepted:** onboarding now requires an explicit
  `register_trusted_wallet()` step (or the demo auto-bootstrap from
  `wallet_public_key.pem`). This is intentional friction — a merchant
  that will accept mandates from *any* wallet without pinning anything
  has just rebuilt the original problem with extra steps.

## Alternatives considered
- **Keep HMAC, rotate the secret frequently.** Rejected — rotation
  doesn't change who holds the secret; the merchant can still forge
  mandates at will up until rotation.
- **JWT with an external OAuth provider.** Reasonable production
  direction, but heavier than this demo needed to prove the trust-boundary
  point, and it moves the "who holds the key" question to a third party
  rather than answering it directly in the codebase.