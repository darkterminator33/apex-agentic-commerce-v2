# 🏎️ Apex F1 Store | Agentic Commerce Engine

**Submission for Razorpay AI Buildathon — Track 01: AI Growth & Agentic Commerce**

Apex F1 is an AI-driven commerce platform built to solve the open problem of the year: **Agent-to-Agent Commerce**. 

Rather than just building a human-facing chatbot, this project implements a **"One Enforcement Engine, Two Front Doors"** architecture. It exposes both a conversational Streamlit UI for humans and a machine-readable FastAPI endpoint for external AI buyers, all governed by a strictly bounded, gated central core.

## 🏗️ Architecture: Meeting "The Bar"

This project strictly adheres to the Track 01 safety requirements:

* **🛡️ Gated:** The AI operates on a "Proposal/Confirm" mandate. It cannot spend money directly. It generates a transaction proposal, which must be explicitly confirmed via a human UI click (Streamlit) or an explicit API call (FastAPI) before calling the Razorpay test API.
* **🚧 Bounded:** AI hallucinations are neutralized by `core.py`. Even if the LLM is injected to offer a 100% discount or sell 50 items, the backend hard-clamps discounts (Max 5% with valid code) and checks actual inventory before generating the payment link.
* **📋 Explainable:** Every prompt, rejected proposal, blocked out-of-stock attempt, and generated link is logged centrally in the real-time Audit Trail visible in the Admin Dashboard.
* **♻️ Graceful Failure:** If the AI hallucinates invalid JSON, a `try/except` block catches the parse error, logs an `ERROR_FALLBACK`, and gracefully replies to the user without crashing the UI.

## 🚀 How It Works (Two Front Doors)

**1. The Human Buyer (Streamlit)**
* A conversational UI where users ask for recommendations.
* The AI acts as a sales rep, reading the live catalog and pushing upsells to drive Average Order Value (AOV).
* Gated by a "Confirm & Pay via Razorpay" UI button.

**2. The AI Buyer (FastAPI)**
* Exposes `/catalog`, `/checkout/propose`, and `/checkout/confirm` endpoints.
* External AI agents can query stock, generate a proposal, and confirm a checkout programmatically using JSON.

## 🛠️ Run it Locally

**1. Setup Environment**
bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
**2. Set Environment Variables (`.env`)**
text
GEMINI_API_KEY=your_key
RAZORPAY_KEY_ID=your_id
RAZORPAY_KEY_SECRET=your_secret
**3. Start the Apps (In separate terminals)**
bash
# Front Door 1: Human UI
streamlit run mk3.py
# Front Door 2: Agent API
uvicorn agent_api:app --reload --port 8000

*Note: In this prototype, the Streamlit and FastAPI servers run in separate processes. In a production environment, `core.py`'s in-memory dictionaries would simply be replaced by a shared SQLite/Postgres database.*