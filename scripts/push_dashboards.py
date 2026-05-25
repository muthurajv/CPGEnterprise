"""Push the 5 CPG dashboards to Grafana Cloud via the HTTP API.

Usage:
    python scripts/push_dashboards.py --token <service_account_token>
"""
import argparse
import json
import sys
import urllib.request
import urllib.error

GRAFANA_URL = "https://muthuraj1.grafana.net"

# ── Dashboard definitions ──────────────────────────────────────────────────────

def _dashboard(title: str, uid: str, panels: list) -> dict:
    return {
        "dashboard": {
            "uid": uid,
            "title": title,
            "tags": ["cpg", "supply-chain", "ai"],
            "timezone": "browser",
            "schemaVersion": 39,
            "refresh": "30s",
            "panels": panels,
        },
        "folderId": 0,
        "overwrite": True,
        "message": "Created by CPG Supply Chain AI deployment script",
    }


def _stat(title, expr, unit, gridPos, datasource="-- Grafana --"):
    return {
        "type": "stat",
        "title": title,
        "datasource": datasource,
        "gridPos": gridPos,
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background"},
        "targets": [{"expr": expr, "legendFormat": title, "refId": "A"}],
        "fieldConfig": {"defaults": {"unit": unit}},
    }


def _timeseries(title, targets, gridPos, datasource):
    return {
        "type": "timeseries",
        "title": title,
        "datasource": datasource,
        "gridPos": gridPos,
        "targets": targets,
        "fieldConfig": {"defaults": {"custom": {"lineWidth": 2}}},
        "options": {"tooltip": {"mode": "multi"}},
    }


def _logs_panel(title, expr, gridPos, datasource):
    return {
        "type": "logs",
        "title": title,
        "datasource": datasource,
        "gridPos": gridPos,
        "targets": [{"expr": expr, "refId": "A"}],
        "options": {"showTime": True, "wrapLogMessage": True},
    }


def _text(content, gridPos):
    return {
        "type": "text",
        "title": "",
        "gridPos": gridPos,
        "options": {"content": content, "mode": "markdown"},
    }


# ── 1. Agent Orchestration ────────────────────────────────────────────────────

def dashboard_agent_orchestration(prom_ds, tempo_ds, loki_ds):
    panels = [
        _text("## Agent Orchestration\nLangGraph supervisor routing, latency, and token usage across all 6 specialist agents.", {"x": 0, "y": 0, "w": 24, "h": 2}),
        _stat("Total Agent Invocations", 'sum(cpg_agent_invocations_total)', "short", {"x": 0, "y": 2, "w": 4, "h": 4}, prom_ds),
        _stat("Supervisor Routings", 'sum(cpg_supervisor_routings_total)', "short", {"x": 4, "y": 2, "w": 4, "h": 4}, prom_ds),
        _stat("Total LLM Tokens", 'sum(cpg_llm_tokens_total)', "short", {"x": 8, "y": 2, "w": 4, "h": 4}, prom_ds),
        _stat("Policy Decisions", 'sum(cpg_policy_decisions_total)', "short", {"x": 12, "y": 2, "w": 4, "h": 4}, prom_ds),
        _timeseries("Agent Invocations Over Time", [
            {"expr": 'sum by (agent) (rate(cpg_agent_invocations_total[5m]))', "legendFormat": "{{agent}}", "refId": "A"}
        ], {"x": 0, "y": 6, "w": 12, "h": 8}, prom_ds),
        _timeseries("LLM Token Usage by Agent", [
            {"expr": 'sum by (agent, token_type) (rate(cpg_llm_tokens_total[5m]))', "legendFormat": "{{agent}} {{token_type}}", "refId": "A"}
        ], {"x": 12, "y": 6, "w": 12, "h": 8}, prom_ds),
        _timeseries("Supervisor Routing Decisions", [
            {"expr": 'sum by (next_agent) (rate(cpg_supervisor_routings_total[5m]))', "legendFormat": "→ {{next_agent}}", "refId": "A"}
        ], {"x": 0, "y": 14, "w": 12, "h": 8}, prom_ds),
        _timeseries("API Request Rate & Errors", [
            {"expr": 'sum(rate(http_server_duration_count{service_name="cpg-supply-chain"}[5m]))', "legendFormat": "requests/s", "refId": "A"},
            {"expr": 'sum(rate(http_server_duration_count{service_name="cpg-supply-chain",http_response_status_code=~"5.."}[5m]))', "legendFormat": "errors/s", "refId": "B"},
        ], {"x": 12, "y": 14, "w": 12, "h": 8}, prom_ds),
        _logs_panel("Recent Agent Logs", '{service_name="cpg-supply-chain"} |= "Agent"', {"x": 0, "y": 22, "w": 24, "h": 8}, loki_ds),
    ]
    return _dashboard("CPG — Agent Orchestration", "cpg-agent-orchestration", panels)


# ── 2. Supply Chain Operations ────────────────────────────────────────────────

def dashboard_supply_chain_ops(prom_ds, loki_ds):
    panels = [
        _text("## Supply Chain Operations\nInventory status, demand forecast accuracy, and procurement activity.", {"x": 0, "y": 0, "w": 24, "h": 2}),
        _stat("Inventory Queries", 'sum(cpg_agent_invocations_total{agent="inventory"})', "short", {"x": 0, "y": 2, "w": 6, "h": 4}, prom_ds),
        _stat("Demand Forecasts Run", 'sum(cpg_agent_invocations_total{agent="demand_forecasting"})', "short", {"x": 6, "y": 2, "w": 6, "h": 4}, prom_ds),
        _stat("Procurement Recommendations", 'sum(cpg_agent_invocations_total{agent="procurement"})', "short", {"x": 12, "y": 2, "w": 6, "h": 4}, prom_ds),
        _stat("RAG Lookups", 'sum(cpg_agent_invocations_total{agent="rag"})', "short", {"x": 18, "y": 2, "w": 6, "h": 4}, prom_ds),
        _timeseries("Agent Activity — Supply Chain", [
            {"expr": 'sum by (agent) (rate(cpg_agent_invocations_total{agent=~"inventory|demand_forecasting|procurement"}[10m]))', "legendFormat": "{{agent}}", "refId": "A"}
        ], {"x": 0, "y": 6, "w": 24, "h": 8}, prom_ds),
        _logs_panel("Inventory Agent Responses", '{service_name="cpg-supply-chain"} |= "Inventory Agent"', {"x": 0, "y": 14, "w": 12, "h": 10}, loki_ds),
        _logs_panel("Procurement Agent Responses", '{service_name="cpg-supply-chain"} |= "Procurement Agent"', {"x": 12, "y": 14, "w": 12, "h": 10}, loki_ds),
    ]
    return _dashboard("CPG — Supply Chain Operations", "cpg-supply-chain-ops", panels)


# ── 3. Policy Governance ──────────────────────────────────────────────────────

def dashboard_policy_governance(prom_ds, loki_ds):
    panels = [
        _text("## Policy Governance\nAI procurement policy decisions — approval rates, human-review queue, and denials.", {"x": 0, "y": 0, "w": 24, "h": 2}),
        _stat("Auto-Approved", 'sum(cpg_policy_decisions_total{decision="auto_approve"})', "short", {"x": 0, "y": 2, "w": 6, "h": 4}, prom_ds),
        _stat("Human Review Required", 'sum(cpg_policy_decisions_total{decision="human_review"})', "short", {"x": 6, "y": 2, "w": 6, "h": 4}, prom_ds),
        _stat("Denied", 'sum(cpg_policy_decisions_total{decision="deny"})', "short", {"x": 12, "y": 2, "w": 6, "h": 4}, prom_ds),
        _stat("Policy Agent Invocations", 'sum(cpg_agent_invocations_total{agent="policy_approval"})', "short", {"x": 18, "y": 2, "w": 6, "h": 4}, prom_ds),
        _timeseries("Policy Decision Rate Over Time", [
            {"expr": 'sum by (decision) (rate(cpg_policy_decisions_total[10m]))', "legendFormat": "{{decision}}", "refId": "A"}
        ], {"x": 0, "y": 6, "w": 24, "h": 8}, prom_ds),
        _logs_panel("Policy Approval Decisions", '{service_name="cpg-supply-chain"} |= "Policy Approval"', {"x": 0, "y": 14, "w": 24, "h": 10}, loki_ds),
    ]
    return _dashboard("CPG — Policy Governance", "cpg-policy-governance", panels)


# ── 4. Executive Analytics ────────────────────────────────────────────────────

def dashboard_executive_analytics(prom_ds, loki_ds):
    panels = [
        _text("## Executive Analytics\nKPI trends and CFO narrative from the Executive Analytics agent.", {"x": 0, "y": 0, "w": 24, "h": 2}),
        _stat("Analytics Reports Generated", 'sum(cpg_agent_invocations_total{agent="executive_analytics"})', "short", {"x": 0, "y": 2, "w": 8, "h": 4}, prom_ds),
        _stat("Total Queries Handled", 'sum(cpg_supervisor_routings_total)', "short", {"x": 8, "y": 2, "w": 8, "h": 4}, prom_ds),
        _stat("Total Tokens Used (All Time)", 'sum(cpg_llm_tokens_total)', "short", {"x": 16, "y": 2, "w": 8, "h": 4}, prom_ds),
        _timeseries("Query Volume by Agent Type", [
            {"expr": 'sum by (agent) (increase(cpg_agent_invocations_total[1h]))', "legendFormat": "{{agent}}", "refId": "A"}
        ], {"x": 0, "y": 6, "w": 24, "h": 8}, prom_ds),
        _logs_panel("Executive Analytics Narratives", '{service_name="cpg-supply-chain"} |= "Executive Analytics"', {"x": 0, "y": 14, "w": 24, "h": 12}, loki_ds),
    ]
    return _dashboard("CPG — Executive Analytics", "cpg-executive-analytics", panels)


# ── 5. Infrastructure Health ──────────────────────────────────────────────────

def dashboard_infrastructure_health(prom_ds, loki_ds):
    panels = [
        _text("## Infrastructure Health\nFastAPI performance, error rates, and OTel pipeline health.", {"x": 0, "y": 0, "w": 24, "h": 2}),
        _stat("API Uptime Check", '1', "short", {"x": 0, "y": 2, "w": 6, "h": 4}, prom_ds),
        _stat("Request Rate (req/s)", 'sum(rate(http_server_duration_count{service_name="cpg-supply-chain"}[5m]))', "reqps", {"x": 6, "y": 2, "w": 6, "h": 4}, prom_ds),
        _stat("Error Rate (5xx)", 'sum(rate(http_server_duration_count{service_name="cpg-supply-chain",http_response_status_code=~"5.."}[5m]))', "reqps", {"x": 12, "y": 2, "w": 6, "h": 4}, prom_ds),
        _stat("Active Spans", 'sum(cpg_supervisor_routings_total)', "short", {"x": 18, "y": 2, "w": 6, "h": 4}, prom_ds),
        _timeseries("HTTP Request Latency (p50/p95)", [
            {"expr": 'histogram_quantile(0.50, sum by (le) (rate(http_server_duration_bucket{service_name="cpg-supply-chain"}[5m])))', "legendFormat": "p50", "refId": "A"},
            {"expr": 'histogram_quantile(0.95, sum by (le) (rate(http_server_duration_bucket{service_name="cpg-supply-chain"}[5m])))', "legendFormat": "p95", "refId": "B"},
        ], {"x": 0, "y": 6, "w": 12, "h": 8}, prom_ds),
        _timeseries("LLM Token Rate (tokens/min)", [
            {"expr": 'sum by (token_type) (rate(cpg_llm_tokens_total[5m])) * 60', "legendFormat": "{{token_type}}", "refId": "A"}
        ], {"x": 12, "y": 6, "w": 12, "h": 8}, prom_ds),
        _logs_panel("Application Error Logs", '{service_name="cpg-supply-chain"} |= "ERROR"', {"x": 0, "y": 14, "w": 24, "h": 8}, loki_ds),
    ]
    return _dashboard("CPG — Infrastructure Health", "cpg-infrastructure-health", panels)


# ── Push logic ────────────────────────────────────────────────────────────────

def get_datasource_uid(token: str, ds_type: str) -> str:
    """Return UID of the preferred datasource for each type.

    Grafana Cloud stacks have multiple datasources per type (ml-metrics, play-prom, etc.).
    We prefer the main stack datasource by matching the well-known name patterns first.
    """
    preferred_names = {
        "prometheus": ["grafanacloud-prom"],
        "loki":       ["grafanacloud-logs"],
        "tempo":      ["grafanacloud-traces"],
    }
    url = f"{GRAFANA_URL}/api/datasources"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as r:
        sources = json.loads(r.read())

    # Build lookup by uid and by name
    by_uid  = {s["uid"]:  s for s in sources}
    by_name = {s["name"]: s for s in sources}

    # Check preferred names first
    for name in preferred_names.get(ds_type, []):
        if name in by_uid:
            return by_uid[name]["uid"]
        if name in by_name:
            return by_name[name]["uid"]

    # Fall back to first matching type that is the default, then any
    matching = [s for s in sources if s["type"] == ds_type]
    defaults = [s for s in matching if s.get("isDefault")]
    return (defaults or matching or [{"uid": f"grafanacloud-{ds_type}"}])[0]["uid"]


def push_dashboard(token: str, payload: dict) -> str:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{GRAFANA_URL}/api/dashboards/db",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read())
    return f"{GRAFANA_URL}{result['url']}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True, help="Grafana service account token (Editor role)")
    args = parser.parse_args()
    token = args.token

    print("Discovering datasource UIDs...")
    prom_ds = get_datasource_uid(token, "prometheus")
    loki_ds = get_datasource_uid(token, "loki")
    tempo_ds = get_datasource_uid(token, "tempo")
    print(f"  Prometheus: {prom_ds}  Loki: {loki_ds}  Tempo: {tempo_ds}")

    dashboards = [
        ("Agent Orchestration",    dashboard_agent_orchestration(prom_ds, tempo_ds, loki_ds)),
        ("Supply Chain Operations", dashboard_supply_chain_ops(prom_ds, loki_ds)),
        ("Policy Governance",       dashboard_policy_governance(prom_ds, loki_ds)),
        ("Executive Analytics",     dashboard_executive_analytics(prom_ds, loki_ds)),
        ("Infrastructure Health",   dashboard_infrastructure_health(prom_ds, loki_ds)),
    ]

    print("\nPushing dashboards to Grafana Cloud...")
    urls = []
    for name, payload in dashboards:
        try:
            url = push_dashboard(token, payload)
            print(f"  [OK] {name}")
            print(f"       {url}")
            urls.append(url)
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"  [FAIL] {name}: HTTP {e.code} — {body}")

    print(f"\nDone. {len(urls)}/5 dashboards created.")
    if urls:
        print(f"\nOpen your Grafana: {GRAFANA_URL}/dashboards")


if __name__ == "__main__":
    main()
