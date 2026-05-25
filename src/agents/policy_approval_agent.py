"""Policy approval specialist: deterministic rule evaluation (no LLM)."""
import json
import re
from typing import Any

from langchain_core.messages import AIMessage

from src.agents.state import SupplyChainState
from src.observability.instrumentation import agent_span, record_policy_decision

# Thresholds (mirror approval_thresholds.txt)
_AUTO_APPROVE_MAX = 10_000.0          # ≤ $10k → auto-approve
_PROCUREMENT_MANAGER_MAX = 50_000.0   # $10k-$50k → Procurement Manager
_VP_FINANCE_MAX = 250_000.0           # $50k-$250k → VP Supply Chain + Finance
                                       # > $250k → C-Suite (CFO + COO)

_HIGH_RISK_CATEGORIES = {"baby", "pharmaceutical"}
_HIGH_RISK_AUTO_MAX = 2_000.0

_UNRELIABLE_VENDOR_THRESHOLD = 0.80


def _extract_order_value(procurement_output: str) -> float | None:
    match = re.search(r'"total_cost_usd"\s*:\s*([\d.]+)', procurement_output)
    if match:
        return float(match.group(1))
    return None


def _extract_vendor_reliability(procurement_output: str) -> float:
    match = re.search(r'"reliability_score"\s*:\s*([\d.]+)', procurement_output)
    return float(match.group(1)) if match else 1.0


def _determine_risk_tier(sku: str | None) -> str:
    if not sku:
        return "medium"
    baby_skus = {"SKU-045", "SKU-046"}
    if sku.upper() in baby_skus:
        return "high"
    return "medium"


def _evaluate_policy(
    order_value: float,
    risk_tier: str,
    vendor_reliability: float,
    sku: str | None,
) -> dict[str, Any]:
    reasons = []
    decision = "auto_approve"

    if vendor_reliability < _UNRELIABLE_VENDOR_THRESHOLD:
        decision = "deny"
        reasons.append(f"Vendor reliability {vendor_reliability:.2f} below minimum 0.80")

    if risk_tier == "high" and order_value > _HIGH_RISK_AUTO_MAX:
        decision = "human_review"
        reasons.append(f"High-risk SKU requires human review above ${_HIGH_RISK_AUTO_MAX:,.0f}")

    # Value-based thresholds (evaluated after risk check so deny can still win)
    if order_value > _VP_FINANCE_MAX:
        decision = max(decision, "human_review")  # keep deny if already denied
        reasons.append(f"Order value ${order_value:,.2f} exceeds ${_VP_FINANCE_MAX:,.0f} — C-Suite (CFO + COO) approval required")
    elif order_value > _PROCUREMENT_MANAGER_MAX:
        if decision != "deny":
            decision = "human_review"
        reasons.append(f"Order value ${order_value:,.2f} requires VP Supply Chain + Finance Director approval")
    elif order_value > _AUTO_APPROVE_MAX:
        if decision != "deny":
            decision = "human_review"
        reasons.append(f"Order value ${order_value:,.2f} requires Procurement Manager approval")
    elif decision == "auto_approve":
        reasons.append(f"Order value ${order_value:,.2f} within auto-approval limit ${_AUTO_APPROVE_MAX:,.0f}")

    if decision == "auto_approve" and not reasons:
        reasons.append("All policy checks passed — auto-approved")

    approval_level = "AI_SYSTEM"
    if decision == "human_review":
        if order_value > _VP_FINANCE_MAX:
            approval_level = "C_SUITE"
        elif order_value > _PROCUREMENT_MANAGER_MAX:
            approval_level = "VP_FINANCE"
        else:
            approval_level = "PROCUREMENT_MANAGER"

    return {
        "decision": decision,
        "reasons": reasons,
        "order_value_usd": order_value,
        "approval_level_required": approval_level,
        "risk_tier": risk_tier,
        "vendor_reliability": vendor_reliability,
        "policy_version": "SCM-THRESH-2026-v2",
    }


def policy_approval_node(state: SupplyChainState) -> dict:
    with agent_span("policy_approval", domain="governance", risk_tier=state.get("risk_tier", "medium")) as span:
        sku = state.get("sku")
        procurement_output = state.get("agent_outputs", {}).get("procurement", "")

        order_value = _extract_order_value(procurement_output) or 0.0
        vendor_reliability = _extract_vendor_reliability(procurement_output)
        risk_tier = _determine_risk_tier(sku)

        result_dict = _evaluate_policy(order_value, risk_tier, vendor_reliability, sku)
        decision = result_dict["decision"]

        record_policy_decision(decision, sku or "unknown", order_value)
        span.set_attribute("policy.decision", decision)
        span.set_attribute("policy.order_value_usd", order_value)
        span.set_attribute("policy.risk_tier", risk_tier)
        span.set_attribute("policy.approval_level", result_dict["approval_level_required"])

        result = json.dumps(result_dict, indent=2)

    return {
        "agent_outputs": {**state.get("agent_outputs", {}), "policy_approval": result_dict},
        "messages": [AIMessage(content=f"[Policy Approval Agent]\n{result}")],
        "active_agent": "policy_approval",
    }
