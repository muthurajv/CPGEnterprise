"""FastAPI application — CPG Supply Chain Multi-Agent API."""
import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, Field

from src.observability.otel_setup import setup_telemetry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_telemetry()
    logger.info("CPG Supply Chain AI started")
    yield
    logger.info("CPG Supply Chain AI shutting down")


app = FastAPI(
    title="CPG Supply Chain AI",
    description="Multi-agent LangGraph system for CPG supply chain operations",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FastAPIInstrumentor.instrument_app(app)


class AskRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sku: str | None = Field(default=None, description="Primary SKU in scope, e.g. SKU-015")
    region: str | None = Field(default=None, description="EMEA | AMER | APAC")
    risk_tier: str = Field(default="medium", description="low | medium | high | critical")


class AskResponse(BaseModel):
    session_id: str
    query: str
    answer: str
    agents_invoked: list[str]
    trace_id: str


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    from langchain_core.messages import HumanMessage
    from src.agents.supervisor import build_graph

    span = get_current_span()
    trace_id = format(span.get_span_context().trace_id, "032x") if span.is_recording() else "none"

    initial_state = {
        "messages": [HumanMessage(content=request.query)],
        "query": request.query,
        "session_id": request.session_id,
        "active_agent": "",
        "agent_outputs": {},
        "risk_tier": request.risk_tier,
        "region": request.region,
        "sku": request.sku,
        "next_agent": "",
    }

    try:
        graph = build_graph()
        final_state = await graph.ainvoke(initial_state, config={"recursion_limit": 20})
    except Exception as exc:
        logger.error("Graph execution error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    agents_invoked = list(final_state.get("agent_outputs", {}).keys())
    outputs = final_state.get("agent_outputs", {})
    answer = outputs.get(agents_invoked[-1], "No response generated") if agents_invoked else "No agents invoked"

    logger.info(
        "Query answered | session=%s agents=%s trace=%s",
        request.session_id, agents_invoked, trace_id,
    )

    return AskResponse(
        session_id=request.session_id,
        query=request.query,
        answer=str(answer),
        agents_invoked=agents_invoked,
        trace_id=trace_id,
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "cpg-supply-chain", "version": "1.0.0"}


@app.get("/agents")
async def list_agents() -> dict:
    return {
        "agents": [
            {"name": "inventory", "description": "Real-time stock levels via SAP mock"},
            {"name": "demand_forecasting", "description": "90-day demand forecast over 18-month history"},
            {"name": "procurement", "description": "Vendor selection and order recommendations"},
            {"name": "policy_approval", "description": "Deterministic policy rule evaluation"},
            {"name": "rag", "description": "Hybrid search over policy documents and SOPs"},
            {"name": "executive_analytics", "description": "KPI computation with CFO narrative"},
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.main:app",
        host=os.environ.get("APP_HOST", "0.0.0.0"),
        port=int(os.environ.get("APP_PORT", 8000)),
        reload=False,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )
