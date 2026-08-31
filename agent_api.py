from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import core

app = FastAPI(title="Apex F1 Store - Agent API", description="Machine-readable endpoints for AI Buyers.")

class ProposeRequest(BaseModel):
    item_key: str
    quantity: int = 1
    discount_code: str = None
    agent_id: str

class ConfirmRequest(BaseModel):
    proposal_id: str
    agent_id: str

@app.get("/catalog")
def get_catalog():
    """AI agents call this to read the structured store catalog."""
    return {"catalog": core.CATALOG}

@app.post("/checkout/propose")
def propose_checkout(req: ProposeRequest):
    """AI agents call this to request a purchase. The core bounds it safely."""
    try:
        proposal = core.create_proposal(
            item_key=req.item_key,
            requested_qty=req.quantity,
            discount_code=req.discount_code,
            source=f"agent_api:{req.agent_id}"
        )
        return {"status": "success", "proposal": proposal}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/checkout/confirm")
def confirm_checkout(req: ConfirmRequest):
    """AI agents call this to finalize the proposal and get the Razorpay link."""
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