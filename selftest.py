"""
Quick self-test for the hardened core.py. Monkeypatches rzp_client so no
real network/API keys are needed. Run: python3 selftest.py
"""
import threading
import time
import types
import core

AGENT = "agent_demo_buyer"
KEY = core.AGENT_REGISTRY[AGENT]


def reset_state():
    core.CATALOG["red_bull_cap"]["stock"] = 10
    core.PROPOSALS.clear()
    core.MANDATES.clear()
    core.AUDIT_LOGS.clear()
    core._rate_limit_log.clear()


def fake_payment_link_create(data):
    time.sleep(0.05)  # simulate real network latency so races have room to occur
    return {"short_url": "https://rzp.io/fake_link"}


core.rzp_client.payment_link = types.SimpleNamespace(create=fake_payment_link_create)


def test_mandate_cap_blocks_overspend():
    reset_state()
    mandate = core.issue_mandate(AGENT, max_amount=2000, ttl_seconds=60)
    try:
        core.create_proposal(
            "red_bull_cap", requested_qty=1, source=f"agent_api:{AGENT}",
            agent_id=AGENT, mandate_id=mandate["mandate_id"],
        )
        print("FAIL: mandate cap did not block a 2499 purchase against a 2000 cap")
    except ValueError as e:
        print(f"PASS: mandate cap enforced -> {e}")


def test_mandate_required_for_agents():
    reset_state()
    try:
        core.create_proposal(
            "red_bull_cap", requested_qty=1, source=f"agent_api:{AGENT}", agent_id=AGENT,
        )
        print("FAIL: agent checkout proceeded with no mandate at all")
    except ValueError as e:
        print(f"PASS: missing-mandate checkout blocked -> {e}")


def test_no_double_charge_under_concurrency():
    reset_state()
    mandate = core.issue_mandate(AGENT, max_amount=10000, ttl_seconds=60)
    proposal = core.create_proposal(
        "red_bull_cap", requested_qty=1, source=f"agent_api:{AGENT}",
        agent_id=AGENT, mandate_id=mandate["mandate_id"],
    )
    pid = proposal["proposal_id"]

    results = []

    def worker():
        try:
            core.confirm_proposal(pid, source=f"agent_api:{AGENT}")
            results.append("confirmed")
        except ValueError as e:
            results.append(f"blocked: {e}")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    confirmed_count = results.count("confirmed")
    stock_after = core.CATALOG["red_bull_cap"]["stock"]
    if confirmed_count == 1 and stock_after == 9:
        print(f"PASS: 8 concurrent confirms -> exactly 1 succeeded, stock 10 -> {stock_after}")
    else:
        print(f"FAIL: confirmed_count={confirmed_count}, stock_after={stock_after}, results={results}")


def test_rollback_on_payment_failure():
    reset_state()
    mandate = core.issue_mandate(AGENT, max_amount=10000, ttl_seconds=60)
    proposal = core.create_proposal(
        "red_bull_cap", requested_qty=1, source=f"agent_api:{AGENT}",
        agent_id=AGENT, mandate_id=mandate["mandate_id"],
    )
    pid = proposal["proposal_id"]

    def broken_create(data):
        raise Exception("Simulated Razorpay outage")

    original = core.rzp_client.payment_link.create
    core.rzp_client.payment_link.create = broken_create
    try:
        core.confirm_proposal(pid, source=f"agent_api:{AGENT}")
        print("FAIL: confirm succeeded despite simulated Razorpay outage")
    except ValueError as e:
        stock = core.CATALOG["red_bull_cap"]["stock"]
        remaining = core.MANDATES[mandate["mandate_id"]]["remaining_amount"]
        consumed = core.PROPOSALS[pid]["consumed"]
        if stock == 10 and remaining == mandate["max_amount"] and consumed is False:
            print(f"PASS: graceful failure with full rollback -> {e}")
        else:
            print(f"FAIL: rollback incomplete: stock={stock}, remaining={remaining}, consumed={consumed}")
    finally:
        core.rzp_client.payment_link.create = original


def test_proposal_ttl_expiry():
    reset_state()
    mandate = core.issue_mandate(AGENT, max_amount=10000, ttl_seconds=60)
    proposal = core.create_proposal(
        "red_bull_cap", requested_qty=1, source=f"agent_api:{AGENT}",
        agent_id=AGENT, mandate_id=mandate["mandate_id"],
    )
    core.PROPOSALS[proposal["proposal_id"]]["created_at"] -= (core.PROPOSAL_TTL_SECONDS + 5)
    try:
        core.confirm_proposal(proposal["proposal_id"], source=f"agent_api:{AGENT}")
        print("FAIL: an expired proposal was still confirmable")
    except ValueError as e:
        print(f"PASS: expired proposal rejected -> {e}")


def test_rate_limit():
    reset_state()
    mandate = core.issue_mandate(AGENT, max_amount=100000, ttl_seconds=60)
    blocked = False
    for i in range(core.RATE_LIMIT_MAX_CALLS + 3):
        try:
            core.create_proposal(
                "red_bull_cap", requested_qty=1, source=f"agent_api:{AGENT}",
                agent_id=AGENT, mandate_id=mandate["mandate_id"],
            )
        except ValueError as e:
            if "Rate limit" in str(e):
                blocked = True
                break
    print("PASS: rate limit engaged after burst" if blocked else "FAIL: rate limit never triggered")


if __name__ == "__main__":
    test_mandate_cap_blocks_overspend()
    test_mandate_required_for_agents()
    test_no_double_charge_under_concurrency()
    test_rollback_on_payment_failure()
    test_proposal_ttl_expiry()
    test_rate_limit()