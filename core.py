import os
import datetime
import uuid
import razorpay
from dotenv import load_dotenv

load_dotenv()

# Initialize Razorpay here so it is shared centrally
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
rzp_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

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
AUDIT_LOGS = []

def log_audit(action, details, source="system"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    AUDIT_LOGS.append({
        "timestamp": timestamp,
        "action": action,
        "details": details,
        "source": source
    })

def create_proposal(item_key, requested_qty=1, discount_code=None, source="system"):
    if item_key not in CATALOG:
        raise ValueError(f"Item {item_key} not found in catalog.")
    
    item = CATALOG[item_key]
    
    # HARD BOUNDARY: Clamp quantity to available stock
    actual_qty = min(max(1, requested_qty), item["stock"])
    
    if actual_qty <= 0:
        log_audit("STOCK_BLOCKED", f"Zero stock checkout prevented for {item['name']}.", source)
        raise ValueError("Item is out of stock.")
        
    # HARD BOUNDARY: Verify promo code strictly
    discount_pct = 0
    if discount_code == "RACEWEEK5":
        discount_pct = 5
    
    base_total = item["price"] * actual_qty
    final_price = base_total * (1 - (discount_pct / 100))
    
    proposal_id = "prop_" + str(uuid.uuid4())[:8]
    
    proposal = {
        "proposal_id": proposal_id,
        "item_key": item_key,
        "name": item["name"],
        "qty": actual_qty,
        "final_price": final_price,
        "discount_pct": discount_pct,
        "consumed": False
    }
    
    PROPOSALS[proposal_id] = proposal
    log_audit("GATE_TRIGGERED", f"Created proposal {proposal_id} for {actual_qty}x {item['name']} at ₹{final_price:.2f}", source)
    
    return proposal

def confirm_proposal(proposal_id, source="system"):
    if proposal_id not in PROPOSALS:
        raise ValueError("Invalid proposal ID.")
        
    proposal = PROPOSALS[proposal_id]
    
    # IDEMPOTENCY GUARD: Prevent double-charging
    if proposal["consumed"]:
        log_audit("DUPLICATE_BLOCKED", f"Attempted to reuse proposal {proposal_id}.", source)
        raise ValueError("Proposal already consumed.")
        
    item_key = proposal["item_key"]
    if CATALOG[item_key]["stock"] < proposal["qty"]:
        log_audit("CONFIRM_REJECTED", f"Stock depleted before confirm for {proposal_id}.", source)
        raise ValueError("Stock no longer available.")
        
    try:
        payment_data = {
            "amount": int(proposal["final_price"] * 100),
            "currency": "INR",
            "description": f"Order for {proposal['qty']}x {proposal['name']}",
            "notes": {"sku": proposal["name"], "qty": str(proposal["qty"]), "source": source}
        }
        payment_link = rzp_client.payment_link.create(payment_data).get("short_url", "#")
        
        # Apply the final state changes
        CATALOG[item_key]["stock"] -= proposal["qty"]
        proposal["consumed"] = True
        proposal["payment_link"] = payment_link
        
        log_audit("ORDER_CREATED", f"Link: {payment_link} | Price: ₹{proposal['final_price']:.2f} | Qty: {proposal['qty']}", source)
        return proposal
        
    except Exception as e:
        log_audit("API_ERROR", str(e), source)
        raise ValueError(f"Razorpay Error: {e}")