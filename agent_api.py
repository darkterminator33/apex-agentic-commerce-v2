from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import core

app = FastAPI(title="Apex F1 Store - Agent API", description="Machine-readable endpoints for AI Buyers.")


class MandateRequest(BaseModel):
    agent_id: str
    max_amount: float          # total INR this agent may spend under this mandate
    ttl_seconds: int = 600


class ProposeRequest(BaseModel):
    item_key: str
    quantity: int = 1
    discount_code: Optional[str] = None
    agent_id: str
    mandate_id: str            # required: every agent proposal must cite a mandate


class ConfirmRequest(BaseModel):
    proposal_id: str
    agent_id: str


def verify_agent(agent_id: str, x_agent_key: Optional[str]):
    """Simple shared-secret auth so an arbitrary caller can't act as an
    agent_id it doesn't own. Swap for OAuth/mTLS in production."""
    expected_key = core.AGENT_REGISTRY.get(agent_id)
    if expected_key is None or x_agent_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid agent credentials.")


@app.get("/catalog")
def get_catalog():
    """AI agents call this to read the structured store catalog. No auth
    required -- catalog discovery is meant to be public."""
    return {"catalog": core.CATALOG}


@app.post("/mandate/issue")
def issue_mandate(req: MandateRequest, x_agent_key: Optional[str] = Header(None)):
    """Issues a bounded, time-limited spending mandate for an agent.

    NOTE: in a real deployment this endpoint would be called by the USER's
    own wallet/app after the user explicitly authorizes the agent -- not by
    the merchant, and not by the agent itself. It lives here only so the
    full propose -> confirm flow can be demoed end-to-end without a
    separate wallet service.
    """
    verify_agent(req.agent_id, x_agent_key)
    try:
        mandate = core.issue_mandate(req.agent_id, req.max_amount, req.ttl_seconds, source=f"agent_api:{req.agent_id}")
        return {"status": "success", "mandate": mandate}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/checkout/propose")
def propose_checkout(req: ProposeRequest, x_agent_key: Optional[str] = Header(None)):
    """AI agents call this to request a purchase. The core bounds it safely
    against stock, discount rules, and the agent's spending mandate."""
    verify_agent(req.agent_id, x_agent_key)
    try:
        proposal = core.create_proposal(
            item_key=req.item_key,
            requested_qty=req.quantity,
            discount_code=req.discount_code,
            source=f"agent_api:{req.agent_id}",
            agent_id=req.agent_id,
            mandate_id=req.mandate_id,
        )
        return {"status": "success", "proposal": proposal}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/checkout/confirm")
def confirm_checkout(req: ConfirmRequest, x_agent_key: Optional[str] = Header(None)):
    """AI agents call this to finalize the proposal and get the Razorpay link."""
    verify_agent(req.agent_id, x_agent_key)
    try:
        result = core.confirm_proposal(
            proposal_id=req.proposal_id,
            source=f"agent_api:{req.agent_id}"
        )
        return {"status": "success", "payment_link": result["payment_link"], "receipt": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/audit")
def get_audit_log():
    """Exposes the audit trail for transparency."""
    return {"logs": core.AUDIT_LOGS}