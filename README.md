# CPG Enterprise Supply Chain AI

A proof-of-concept multi-agent AI system for supply-chain operations, built with **LangGraph** and **Azure OpenAI**. A single supervisor coordinates six specialist agents inside one LangGraph state machine. All telemetry flows directly to **Grafana Cloud** via OpenTelemetry.

---

## Architecture

```
User Request
    |
    v
POST /ask  (FastAPI)
    |
    v
Supervisor Agent  (LangGraph StateGraph)
    |-- routes to -->
    |   inventory              Real-time stock levels (SAP mock)
    |   demand_forecasting     90-day forecast over 18-month history
    |   procurement            Vendor selection, order qty, urgency
    |   policy_approval        Deterministic rule engine (no LLM)
    |   rag                    Hybrid ChromaDB search over policy docs
    |   executive_analytics    KPI computation + CFO narrative
    |
    v
OTel HTTP exporter
    |
    v
Grafana Cloud OTLP Gateway
    |-- Tempo    (traces)
    |-- Loki     (logs)
    |-- Mimir    (metrics)
```

---

## Capabilities

| Agent | What it does |
|---|---|
| **Inventory** | Real-time stock levels, reorder-point alerts, stockout risk via SAP mock |
| **Demand Forecasting** | LLM reasoning over 18-month weekly shipment history; 90-day forecast + confidence score |
| **Procurement** | Vendor selection from catalog, optimal order quantity, urgency score 1-10 |
| **Policy Approval** | Deterministic: auto-approve ≤$10k, Procurement Manager ≤$50k, VP/Finance ≤$250k, C-Suite above |
| **RAG** | Hybrid MMR search over procurement policy, approval thresholds, and inventory SOP docs |
| **Executive Analytics** | KPI scorecard (fill rate, MAPE, inventory turnover) + CFO-ready narrative |

---

## Quick Start

### 1. Install dependencies

```powershell
pip install -r requirements.txt
```

### 2. Configure credentials

```powershell
copy .env.example .env
# Edit .env — fill in Azure OpenAI and Grafana Cloud values
```

The two Grafana Cloud values you need:

| Variable | Where to find it |
|---|---|
| `GRAFANA_CLOUD_OTLP_ENDPOINT` | Grafana Cloud stack > Connections > OpenTelemetry |
| `GRAFANA_CLOUD_AUTH` | base64 of `<StackID>:<API_Key>` — generate with: |

```powershell
[Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("1234567:glc_your_api_key"))
```

### 3. Run

```powershell
python run.py
```

API available at `http://127.0.0.1:8001`

---

## Usage Examples

```bash
# Stock level check
curl -X POST http://127.0.0.1:8001/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the stock level for SKU-015?","sku":"SKU-015"}'

# Compound supply chain query (triggers multiple agents)
curl -X POST http://127.0.0.1:8001/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"We have a potential stockout on SKU-015 in EMEA — what should we do?","sku":"SKU-015","region":"EMEA","risk_tier":"high"}'

# Policy lookup
curl -X POST http://127.0.0.1:8001/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the approval threshold for orders above $50,000?"}'

# Executive dashboard
curl -X POST http://127.0.0.1:8001/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Give me the executive KPI summary for EMEA","region":"EMEA"}'

# Health check
curl http://127.0.0.1:8001/health
```

---

## Project Structure

```
CPGEnterprise/
├── src/
│   ├── agents/
│   │   ├── state.py                     SupplyChainState TypedDict
│   │   ├── supervisor.py                LangGraph StateGraph + routing
│   │   ├── inventory_agent.py
│   │   ├── demand_forecasting_agent.py
│   │   ├── procurement_agent.py
│   │   ├── policy_approval_agent.py     Deterministic, no LLM
│   │   ├── rag_agent.py
│   │   └── executive_analytics_agent.py
│   ├── tools/
│   │   ├── sap_mock.py                  Simulated SAP inventory API
│   │   ├── vector_store.py              ChromaDB + hybrid retriever
│   │   └── kpi_calculator.py            Fill rate, MAPE, turnover
│   ├── observability/
│   │   ├── otel_setup.py                OTel → Grafana Cloud HTTP
│   │   └── instrumentation.py           CPG span attributes, counters
│   ├── data/
│   │   ├── inventory.json               50 SKUs
│   │   ├── shipment_history.json        4,680 weekly records (18 months)
│   │   ├── vendor_catalog.json          10 vendors
│   │   └── policy_docs/                 3 policy/SOP documents for RAG
│   └── api/
│       └── main.py                      FastAPI app
├── k8s/                                 AKS deployment manifests
├── tests/                               28 unit tests (no LLM calls)
├── run.py                               Local dev entry point
└── .env.example                         Credential template
```

---

## Observability

Every agent invocation is instrumented with CPG-specific OTel span attributes:

```python
span.set_attribute("industry", "cpg")
span.set_attribute("business.domain", "supply_chain")
span.set_attribute("workflow.type", "specialist_agent")
span.set_attribute("governance.risk_tier", "high")
span.set_attribute("gen_ai.model", "azure_openai_gpt4o")
```

Custom metrics tracked in Grafana Cloud:
- `cpg_agent_invocations_total` — per-agent invocation count
- `cpg_agent_latency_ms` — agent execution latency histogram
- `cpg_supervisor_routings_total` — supervisor routing decisions
- `cpg_policy_decisions_total` — policy outcomes (auto_approve / human_review / deny)
- `cpg_llm_tokens_total` — LLM token usage by agent

**Recommended Grafana Cloud dashboards** (create in UI using the metrics/traces above):
1. Agent Orchestration — supervisor routing heatmap, per-agent latency, token usage
2. Supply Chain Ops — inventory levels, forecast vs actual, procurement queue
3. Policy Governance — approval rates, human-review queue, deny reasons
4. Executive Analytics — fill rate, MAPE, stockout count trends
5. Infrastructure Health — API p95 latency, error rates

---

## Tests

```powershell
python -m pytest tests/ -v
# 28 passed in ~14s (no LLM or network calls)
```

---

## Deployment (AKS)

```powershell
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
# Create secrets first:
kubectl create secret generic cpg-supply-chain-secrets \
  --from-literal=AZURE_OPENAI_KEY=<key> \
  --from-literal=AZURE_OPENAI_ENDPOINT=<endpoint> \
  -n cpg-observability
kubectl create secret generic grafana-cloud-secrets \
  --from-literal=GRAFANA_CLOUD_OTLP_ENDPOINT=<url> \
  --from-literal=GRAFANA_CLOUD_AUTH=<base64> \
  -n cpg-observability
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```
