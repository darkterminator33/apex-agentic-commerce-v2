# 🏎️ Apex F1 Store | Agentic Commerce Engine

**Submission for Razorpay AI Buildathon — Track 01: AI Growth & Agentic Commerce**

Apex F1 is an AI-driven commerce platform built to solve the open problem of the year: **Agent-to-Agent Commerce**.

Rather than just building a human-facing chatbot, this project implements a **"One Enforcement Engine, Two Front Doors"** architecture. It exposes both a conversational Streamlit UI for humans and a machine-readable FastAPI endpoint for external AI buyers, all governed by a strictly bounded, gated, and now **authorization-scoped** central core.

## 🏗️ Architecture: Meeting "The Bar"

* **🛡️ Gated:** The AI operates on a "Proposal/Confirm" mandate. It cannot spend money directly. It generates a transaction proposal, which must be explicitly confirmed via a human UI click (Streamlit) or an explicit, authenticated API call (FastAPI) before calling the Razorpay test API.
* **🚧 Bounded:** AI hallucinations are neutralized by `core.py`. Even if the LLM is injected to offer a 100% discount or sell 50 items, the backend hard-clamps discounts (Max 5% with valid code) and checks actual inventory before generating the payment link. Agent-initiated purchases are additionally bounded by a **signed spending mandate** — an agent can never spend more than it has been explicitly authorized for, and never longer than the mandate's expiry window.
* **📋 Explainable:** Every prompt, rejected proposal, blocked out-of-stock attempt, mandate issuance/rejection, rate-limit trip, and generated payment link is logged centrally in the real-time Audit Trail visible in the Admin Dashboard.
* **♻️ Graceful Failure:** If the AI hallucinates invalid JSON, a `try/except` block catches the parse error, logs an `ERROR_FALLBACK`, and gracefully replies to the user without crashing the UI. If Razorpay itself fails mid-confirm, the reserved stock and mandate spend are **rolled back atomically** rather than left in a stuck or double-counted state.

## 🔐 Hardening on top of the original architecture

The first version's `propose → confirm` pattern proved out the *shape* of agent-to-agent commerce, but left three gaps that matter specifically because the buyer is autonomous:

| Gap | Fix |
|---|---|
| `confirm_proposal` checked `consumed` and set it *after* the slow Razorpay call — two concurrent confirms on the same proposal could both pass the check and double-charge. | State (`consumed`, stock, mandate spend) is now reserved **inside a lock, before** the Razorpay call, with a full rollback if Razorpay fails. Verified with 8 concurrent confirm threads → exactly 1 succeeds. |
| Any caller could act as any `agent_id` — there was no authentication on the agent API. | `agent_api.py` now requires an `X-Agent-Key` header checked against `core.AGENT_REGISTRY`. |
| An agent could propose/confirm unlimited purchases with no spend ceiling. | Agents must hold a **signed, expiring, revocable mandate** (`/mandate/issue`) capping total spend. `create_proposal` rejects any purchase with no mandate or over the mandate's remaining cap — this mirrors the AP2/UAP "user authorizes agent up to X" pattern. In production the mandate would be signed by the *user's* wallet, not the merchant; here `issue_mandate()` stands in for that trusted authority. |
| A proposal never expired, so a stale price/stock quote could be confirmed long after conditions changed. | Proposals now expire after `PROPOSAL_TTL_SECONDS` (180s by default). |
| No limit on how fast an agent could call the API. | Simple per-agent sliding-window rate limit (`RATE_LIMIT_MAX_CALLS` / `RATE_LIMIT_WINDOW_SECONDS`). |

`selftest.py` exercises all five of these against a stubbed Razorpay client (no live keys needed) — see below.

## 🚀 How It Works (Two Front Doors)

**1. The Human Buyer (Streamlit)**
* A conversational UI where users ask for recommendations.
* The AI acts as a sales rep, reading the live catalog and pushing upsells to drive Average Order Value (AOV).
* Gated by a "Confirm & Pay via Razorpay" UI button. The human path does not need a mandate — `core.create_proposal` only enforces mandate checks when an `agent_id` is present.

**2. The AI Buyer (FastAPI)**
* `POST /mandate/issue` — a trusted authority (stand-in for a user's wallet) authorizes an agent to spend up to a capped amount for a limited time.
* `GET /catalog` — public, unauthenticated catalog discovery.
* `POST /checkout/propose` — requires `X-Agent-Key` + a valid `mandate_id`; returns a server-bounded proposal.
* `POST /checkout/confirm` — requires `X-Agent-Key`; finalizes the proposal and returns the Razorpay payment link.
* `GET /audit` — shared audit trail across both front doors.

## 🛠️ Run it Locally

**1. Setup Environment**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Set Environment Variables (`.env`)**
```text
GEMINI_API_KEY=your_key
RAZORPAY_KEY_ID=your_id
RAZORPAY_KEY_SECRET=your_secret

# Optional — override the demo agent's API key and mandate-signing secret.
# If unset, a random MANDATE_SECRET is generated at process start and a
# default AGENT_DEMO_KEY is used.
AGENT_DEMO_KEY=sk_test_demo_key_12345
MANDATE_SECRET=change_me_in_production
```

**3. Start the Apps (in separate terminals)**
```bash
# Front Door 1: Human UI
streamlit run mk3.py

# Front Door 2: Agent API
uvicorn agent_api:app --reload --port 8000
```

**4. Run the hardening self-tests (no live keys needed — Razorpay is stubbed)**
```bash
python3 selftest.py
```
Expected: 6/6 `PASS` lines, covering mandate cap enforcement, mandate-required checkout, no double-charge under concurrency, graceful rollback on a simulated Razorpay outage, proposal TTL expiry, and rate limiting.

**5. Example agent flow (curl)**
```bash
# 1. Get a spending mandate (stand-in for a user-signed authorization)
curl -X POST localhost:8000/mandate/issue \
  -H "X-Agent-Key: sk_test_demo_key_12345" -H "Content-Type: application/json" \
  -d '{"agent_id": "agent_demo_buyer", "max_amount": 5000, "ttl_seconds": 600}'

# 2. Propose a purchase against that mandate
curl -X POST localhost:8000/checkout/propose \
  -H "X-Agent-Key: sk_test_demo_key_12345" -H "Content-Type: application/json" \
  -d '{"item_key": "red_bull_cap", "quantity": 1, "agent_id": "agent_demo_buyer", "mandate_id": "mandate_xxxxxxxx"}'

# 3. Confirm and get the Razorpay payment link
curl -X POST localhost:8000/checkout/confirm \
  -H "X-Agent-Key: sk_test_demo_key_12345" -H "Content-Type: application/json" \
  -d '{"proposal_id": "prop_xxxxxxxx", "agent_id": "agent_demo_buyer"}'
```

*Note: In this prototype, the Streamlit and FastAPI servers run in separate processes. In a production environment, `core.py`'s in-memory dictionaries (catalog, proposals, mandates, audit log) would be replaced by a shared SQLite/Postgres database, and mandate signatures would be verified against the user's own public key rather than a merchant-held secret.*