import os
import time
import hmac
import hashlib
import secrets
import threading
import datetime
import uuid
import razorpay
from dotenv import load_dotenv

load_dotenv()

# Initialize Razorpay here so it is shared centrally
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
rzp_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# ==========================================================
# AGENT IDENTITY & MANDATE SIGNING
#
# In a real AP2/UAP-style flow, an agent presents a mandate that was
# signed by the USER's own device/wallet key, and the merchant verifies
# it against the user's public key -- the merchant never controls the
# signing key. For this demo there is no separate user-wallet service,
# so `issue_mandate()` below plays the role of that trusted authority.
# It is deliberately kept OUT of the agent's reach (agent_api.py's
# checkout endpoints never call it on the agent's behalf) so the demo
# still shows the right shape: an agent can only spend against a cap
# that some other, non-agent party explicitly authorized.
# ==========================================================
MANDATE_SECRET = os.getenv("MANDATE_SECRET", secrets.token_hex(16))

# Static demo registry of agents allowed to call the machine API at all.
# Swap for a real API-key/OAuth store in production.
AGENT_REGISTRY = {
    "agent_demo_buyer": os.getenv("AGENT_DEMO_KEY", "sk_test_demo_key_12345"),
}

PROPOSAL_TTL_SECONDS = 180          # a proposal is only confirmable for 3 minutes
RATE_LIMIT_MAX_CALLS = 10           # per agent
RATE_LIMIT_WINDOW_SECONDS = 60      # per rolling minute

# Shared In-Memory State
CATALOG = {
    "red_bull_cap": {"name": "Red Bull Racing F1 Cap", "team": "Red Bull", "category": "Headwear", "price": 2499, "stock": 10, "upsell": "verstappen_tee"},
    "verstappen_tee": {"name": "Max Verstappen #1 Champion Tee", "team": "Red Bull", "category": "Apparel", "price": 1999, "stock": 8, "upsell": "f1_model_car"},
    "f1_model_car": {"name": "RB20 1:43 Scale Diecast Model", "team": "Red Bull", "category": "Collectibles", "price": 4999, "stock": 3, "upsell": None},
    "ferrari_polo": {"name": "Scuderia Ferrari Team Polo", "team": "Ferrari", "category": "Apparel", "price": 3499, "stock": 6, "upsell": None},
    "mclaren_hoodie": {"name": "McLaren F1 Papaya Hoodie", "team": "McLaren", "category": "Apparel", "price": 3999, "stock": 4, "upsell": None},
    "senna_helmet": {"name": "Ayrton Senna 1:2 Replica Helmet", "team": "Classic", "category": "Collectibles", "price": 8999, "stock": 0, "upsell": None}
}

PROPOSALS = {}
MANDATES = {}
AUDIT_LOGS = []

_state_lock = threading.Lock()          # guards proposal/stock/mandate mutation
_rate_limit_log = {}                    # agent_id -> [timestamps]


def log_audit(action, details, source="system"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    AUDIT_LOGS.append({
        "timestamp": timestamp,
        "action": action,
        "details": details,
        "source": source
    })


# ----------------------------------------------------------
# Mandates: bounded, expiring, revocable spend authorization
# ----------------------------------------------------------
def _sign(payload: str) -> str:
    return hmac.new(MANDATE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_mandate(agent_id, max_amount, ttl_seconds=600, source="mandate_authority"):
    """Authorize an agent to spend up to `max_amount` total, for `ttl_seconds`.
    Stands in for a user-signed mandate in a real deployment."""
    if agent_id not in AGENT_REGISTRY:
        raise ValueError("Unknown agent; cannot issue a mandate.")
    if max_amount <= 0:
        raise ValueError("Mandate amount must be positive.")

    issued_at = time.time()
    expires_at = issued_at + ttl_seconds
    payload = f"{agent_id}|{max_amount}|{expires_at}"
    signature = _sign(payload)
    mandate_id = "mandate_" + str(uuid.uuid4())[:8]

    mandate = {
        "mandate_id": mandate_id,
        "agent_id": agent_id,
        "max_amount": max_amount,
        "remaining_amount": max_amount,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "signature": signature,
        "revoked": False,
    }
    MANDATES[mandate_id] = mandate
    log_audit(
        "MANDATE_ISSUED",
        f"Mandate {mandate_id} authorizes {agent_id} up to \u20b9{max_amount:.2f}, expires in {ttl_seconds}s",
        source,
    )
    return mandate


def revoke_mandate(mandate_id, source="system"):
    mandate = MANDATES.get(mandate_id)
    if mandate is None:
        raise ValueError("Unknown mandate.")
    mandate["revoked"] = True
    log_audit("MANDATE_REVOKED", f"Mandate {mandate_id} revoked.", source)
    return mandate


def _verify_mandate(mandate_id):
    mandate = MANDATES.get(mandate_id)
    if mandate is None:
        raise ValueError("Unknown mandate.")
    payload = f"{mandate['agent_id']}|{mandate['max_amount']}|{mandate['expires_at']}"
    if not hmac.compare_digest(_sign(payload), mandate["signature"]):
        # Would only happen if MANDATES were tampered with directly.
        raise ValueError("Mandate signature invalid.")
    if mandate["revoked"]:
        raise ValueError("Mandate has been revoked.")
    if time.time() > mandate["expires_at"]:
        raise ValueError("Mandate has expired.")
    return mandate


def _check_rate_limit(agent_id, source):
    if agent_id is None:
        return
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    calls = [t for t in _rate_limit_log.get(agent_id, []) if t > window_start]
    if len(calls) >= RATE_LIMIT_MAX_CALLS:
        log_audit(
            "RATE_LIMIT_BLOCKED",
            f"Agent {agent_id} exceeded {RATE_LIMIT_MAX_CALLS} calls / {RATE_LIMIT_WINDOW_SECONDS}s.",
            source,
        )
        raise ValueError("Rate limit exceeded. Slow down and try again shortly.")
    calls.append(now)
    _rate_limit_log[agent_id] = calls


# ----------------------------------------------------------
# Propose -> Confirm
# ----------------------------------------------------------
def create_proposal(item_key, requested_qty=1, discount_code=None, source="system",
                     agent_id=None, mandate_id=None):
    if agent_id is not None:
        _check_rate_limit(agent_id, source)

    if item_key not in CATALOG:
        raise ValueError(f"Item {item_key} not found in catalog.")

    item = CATALOG[item_key]

    # HARD BOUNDARY: Clamp quantity to available stock
    actual_qty = min(max(1, requested_qty), item["stock"])

    if actual_qty <= 0:
        log_audit("STOCK_BLOCKED", f"Zero stock checkout prevented for {item['name']}.", source)
        raise ValueError("Item is out of stock.")

    # HARD BOUNDARY: Verify promo code strictly
    discount_pct = 5 if discount_code == "RACEWEEK5" else 0

    base_total = item["price"] * actual_qty
    final_price = base_total * (1 - (discount_pct / 100))

    # HARD BOUNDARY: An agent may only propose within its authorized mandate cap
    if mandate_id is not None:
        mandate = _verify_mandate(mandate_id)
        if mandate["agent_id"] != agent_id:
            log_audit("MANDATE_MISMATCH", f"Agent {agent_id} tried to use a mandate issued to {mandate['agent_id']}.", source)
            raise ValueError("This mandate was not issued to this agent.")
        if final_price > mandate["remaining_amount"]:
            log_audit(
                "MANDATE_CAP_EXCEEDED",
                f"Proposal \u20b9{final_price:.2f} exceeds mandate {mandate_id}'s remaining cap \u20b9{mandate['remaining_amount']:.2f}.",
                source,
            )
            raise ValueError(
                f"This purchase (\u20b9{final_price:.2f}) exceeds the agent's remaining "
                f"authorized spend (\u20b9{mandate['remaining_amount']:.2f})."
            )
    elif agent_id is not None:
        # An agent identity was presented but no mandate -- reject rather than
        # silently allow unbounded agent spend.
        log_audit("MANDATE_MISSING", f"Agent {agent_id} attempted checkout with no mandate.", source)
        raise ValueError("No active spending mandate for this agent. Request one via /mandate/issue.")

    proposal_id = "prop_" + str(uuid.uuid4())[:8]

    proposal = {
        "proposal_id": proposal_id,
        "item_key": item_key,
        "name": item["name"],
        "qty": actual_qty,
        "final_price": final_price,
        "discount_pct": discount_pct,
        "mandate_id": mandate_id,
        "created_at": time.time(),
        "consumed": False,
    }

    PROPOSALS[proposal_id] = proposal
    log_audit("GATE_TRIGGERED", f"Created proposal {proposal_id} for {actual_qty}x {item['name']} at \u20b9{final_price:.2f}", source)

    return proposal


def confirm_proposal(proposal_id, source="system"):
    # Everything that MUTATES shared state happens inside the lock, and it
    # happens BEFORE the slow network call to Razorpay -- this closes the
    # check-then-act window where two concurrent confirms could both pass
    # the "not consumed yet" check and both charge/decrement stock.
    with _state_lock:
        if proposal_id not in PROPOSALS:
            raise ValueError("Invalid proposal ID.")

        proposal = PROPOSALS[proposal_id]

        if proposal["consumed"]:
            log_audit("DUPLICATE_BLOCKED", f"Attempted to reuse proposal {proposal_id}.", source)
            raise ValueError("Proposal already consumed.")

        if time.time() - proposal["created_at"] > PROPOSAL_TTL_SECONDS:
            log_audit("PROPOSAL_EXPIRED", f"Proposal {proposal_id} expired before confirm.", source)
            raise ValueError("This proposal has expired. Please request a new one.")

        item_key = proposal["item_key"]
        if CATALOG[item_key]["stock"] < proposal["qty"]:
            log_audit("CONFIRM_REJECTED", f"Stock depleted before confirm for {proposal_id}.", source)
            raise ValueError("Stock no longer available.")

        mandate = None
        if proposal.get("mandate_id"):
            mandate = _verify_mandate(proposal["mandate_id"])
            if proposal["final_price"] > mandate["remaining_amount"]:
                log_audit("MANDATE_CAP_EXCEEDED", f"Mandate {proposal['mandate_id']} can no longer cover {proposal_id}.", source)
                raise ValueError("The agent's spending cap no longer covers this purchase.")

        # Reserve the state changes NOW, while still holding the lock, so no
        # other thread can slip through the window while we talk to Razorpay.
        proposal["consumed"] = True
        CATALOG[item_key]["stock"] -= proposal["qty"]
        if mandate:
            mandate["remaining_amount"] -= proposal["final_price"]

    try:
        payment_data = {
            "amount": int(proposal["final_price"] * 100),
            "currency": "INR",
            "description": f"Order for {proposal['qty']}x {proposal['name']}",
            "notes": {"sku": proposal["name"], "qty": str(proposal["qty"]), "source": source}
        }
        payment_link = rzp_client.payment_link.create(payment_data).get("short_url", "#")
        proposal["payment_link"] = payment_link

        log_audit("ORDER_CREATED", f"Link: {payment_link} | Price: \u20b9{proposal['final_price']:.2f} | Qty: {proposal['qty']}", source)
        return proposal

    except Exception as e:
        # Roll back the reservation we made above -- the failure is real,
        # but it must not leave stock/mandate state permanently wrong.
        with _state_lock:
            proposal["consumed"] = False
            CATALOG[item_key]["stock"] += proposal["qty"]
            if mandate:
                mandate["remaining_amount"] += proposal["final_price"]
        log_audit("API_ERROR", str(e), source)
        raise ValueError(f"Razorpay Error: {e}")