"""
mk3.py
Human-facing storefront -- same UX as mk2.py, but now built on top of
core.py instead of carrying its own copy of the catalog/enforcement
logic. This is the "one enforcement engine, two front doors" story:
  - A human buys through this Streamlit chat + Confirm button.
  - An AI buyer agent buys through agent_api.py.
Both call core.create_proposal() / core.confirm_proposal(), so the
stock, discount, and gating rules can never drift between the two.

Run:
    streamlit run mk3.py
(agent_api.py can run at the same time on a different port -- they
share core.py's in-memory state within the same process only if run
together via one Python process; for the demo, running mk3.py alone
is enough to show the human path, and agent_api.py alone shows the
agent path. See README for the "run both against a shared DB" note.)
"""

import streamlit as st
import os
from dotenv import load_dotenv
from google import genai
import json
import warnings
warnings.filterwarnings("ignore")

import core  # shared catalog, enforcement, audit log, propose/confirm

warnings.filterwarnings("ignore")
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# --- SESSION STATE (UI-local only; catalog/stock/audit now live in core.py) ---
if "messages" not in st.session_state: st.session_state.messages = []
if "pending_proposal_id" not in st.session_state: st.session_state.pending_proposal_id = None
if "revenue_tracked" not in st.session_state: st.session_state.revenue_tracked = 0

# --- STREAMLIT UI ---
st.set_page_config(page_title="Apex F1 Store", page_icon="🏎️", layout="wide")
st.title("🏎️ Apex F1 Store | Agentic Commerce (mk3 — shared engine)")

tab_store, tab_admin = st.tabs(["🛍️ Customer Storefront", "📊 Admin & Analytics Dashboard"])

# ==========================================
# TAB 1: CUSTOMER STOREFRONT
# ==========================================
with tab_store:
    col_main, col_audit = st.columns([2, 1])

    with col_main:
        st.markdown("### 🏁 Live Catalog")
        grid_cols = st.columns(3)
        for idx, (item_id, item) in enumerate(core.CATALOG.items()):
            with grid_cols[idx % 3]:
                stock_badge = "🟢 In Stock" if item['stock'] > 0 else "🔴 Out of Stock"
                st.info(f"**{item['name']}**\n\n₹{item['price']} · {stock_badge} ({item['stock']})")

        st.divider()

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        # Gated Checkout -- same UX as mk2, now backed by core.PROPOSALS
        if st.session_state.pending_proposal_id:
            proposal = core.PROPOSALS.get(st.session_state.pending_proposal_id)

            if proposal is None or proposal["consumed"]:
                st.session_state.pending_proposal_id = None
            else:
                discount_text = f" ({proposal['discount_pct']}% off applied)" if proposal.get('discount_pct') else ""
                st.warning(
                    f"🛡️ **Payment Gate:** Checkout **{proposal['qty']}x {proposal['name']}** "
                    f"for **₹{proposal['final_price']:.2f}**{discount_text}?"
                )
                b1, b2 = st.columns(2)

                with b1:
                    if st.button("✅ Confirm & Pay via Razorpay", use_container_width=True):
                        try:
                            confirmed = core.confirm_proposal(
                                st.session_state.pending_proposal_id, source="human_ui"
                            )
                            st.session_state.revenue_tracked += confirmed["final_price"]
                            st.success(f"🎉 Order ready! [Click here to Pay]({confirmed['payment_link']})")
                        except ValueError as e:
                            st.error(f"Failed: {e}")
                        st.session_state.pending_proposal_id = None

                with b2:
                    if st.button("❌ Cancel", use_container_width=True):
                        core.log_audit(
                            "ORDER_CANCELLED",
                            f"User aborted proposal {st.session_state.pending_proposal_id}.",
                            "human_ui",
                        )
                        st.session_state.pending_proposal_id = None
                        st.rerun()

        # Chat Input
        user_query = st.chat_input("Ask for merch, recommendations, discounts, or buy an item...")
        if user_query:
            st.session_state.messages.append({"role": "user", "content": user_query})
            core.log_audit("USER_QUERY", user_query, "human_ui")

            system_instruction = f"""
            You are an intelligent agentic commerce sales representative for Apex F1 Store.
            Live Catalog: {json.dumps({k: {kk: vv for kk, vv in v.items()} for k, v in core.CATALOG.items()})}

            STRICT POLICY:
            1. QUANTITY: Check the user's requested quantity. Default to 1 if not specified.
            2. STOCK: If the requested quantity is higher than the available stock, reject gracefully and offer the remaining stock.
            3. UPSELL: Recommend complementary upsell items naturally.
            4. DISCOUNTS: Max allowed discount is 5% with code RACEWEEK5 only, and ONLY if the
               user's message actually contains that code. Never propose a discount otherwise.

            OUTPUT JSON ONLY:
            {{"action": "checkout" or "chat", "item_key": "catalog_key_name" or null, "quantity": integer, "discount_code": "code or null", "reply": "Your message"}}
            """

            try:
                response = client.models.generate_content(model="gemini-3.5-flash-lite", contents=[system_instruction, user_query])
                data = json.loads(response.text.replace("```json", "").replace("```", "").strip())

                reply = data.get("reply", "How can I help?")
                st.session_state.messages.append({"role": "assistant", "content": reply})

                if data.get("action") == "checkout" and data.get("item_key") in core.CATALOG:
                    try:
                        # The LLM's output (quantity, discount_code) is only ever a
                        # REQUEST -- core.create_proposal() re-applies the real
                        # stock/discount bounds server-side regardless of what
                        # the model said.
                        proposal = core.create_proposal(
                            item_key=data.get("item_key"),
                            requested_qty=data.get("quantity", 1),
                            discount_code=data.get("discount_code"),
                            source="human_ui",
                        )
                        st.session_state.pending_proposal_id = proposal["proposal_id"]
                    except ValueError as e:
                        core.log_audit("PROPOSAL_REJECTED", str(e), "human_ui")
                else:
                    core.log_audit("AGENT_RESPONSE", reply, "human_ui")

            except Exception as err:
                st.session_state.messages.append(
                    {"role": "assistant", "content": "Let's explore our gear! (Something went wrong parsing that request -- try rephrasing.)"}
                )
                core.log_audit("ERROR_FALLBACK", str(err), "human_ui")
            st.rerun()

    with col_audit:
        st.subheader("📋 Live Audit Logs")
        st.caption("Shared across the human UI and the agent API.")
        for entry in reversed(core.AUDIT_LOGS[-8:]):
            with st.expander(f"[{entry['action']}] {entry['timestamp'][-8:]} · {entry['source']}"):
                st.code(entry['details'], language="text")

# ==========================================
# TAB 2: ADMIN & ANALYTICS DASHBOARD
# ==========================================
with tab_admin:
    st.markdown("### 📈 Commerce Growth Metrics")
    m1, m2, m3 = st.columns(3)
    m1.metric("Pipeline Revenue (this session)", f"₹{st.session_state.revenue_tracked:,.2f}")
    m2.metric("Total AI Interactions", len([m for m in st.session_state.messages if m['role'] == 'user']))
    m3.metric(
        "Security Interventions",
        len([l for l in core.AUDIT_LOGS if l['action'] in
             ['STOCK_BLOCKED', 'ERROR_FALLBACK', 'PROPOSAL_REJECTED', 'DUPLICATE_BLOCKED', 'CONFIRM_REJECTED']])
    )

    st.divider()

    st.markdown("### 📦 Live Inventory Status")
    inventory_data = [{"Product": v["name"], "Team": v["team"], "Price (₹)": v["price"], "Stock": v["stock"]} for v in core.CATALOG.values()]
    st.table(inventory_data)

    st.divider()

    st.markdown("### 🛡️ Complete Security Audit Trail (shared: human_ui + agent_api)")
    if core.AUDIT_LOGS:
        st.table(core.AUDIT_LOGS)
    else:
        st.info("No logs generated yet.")