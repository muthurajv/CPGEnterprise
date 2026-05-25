"""CPG-specific OpenTelemetry span and metric helpers."""
from contextlib import contextmanager
from typing import Any, Generator

from opentelemetry import metrics, trace
from opentelemetry.trace import Span, Status, StatusCode

_tracer = trace.get_tracer("cpg.supply_chain")
_meter = metrics.get_meter("cpg.supply_chain")

# Metrics
agent_invocations = _meter.create_counter(
    "cpg_agent_invocations_total",
    description="Total number of specialist agent invocations",
)
agent_latency = _meter.create_histogram(
    "cpg_agent_latency_ms",
    description="Agent execution latency in milliseconds",
    unit="ms",
)
supervisor_routings = _meter.create_counter(
    "cpg_supervisor_routings_total",
    description="Total supervisor routing decisions",
)
policy_decisions = _meter.create_counter(
    "cpg_policy_decisions_total",
    description="Policy approval decisions by outcome",
)
token_usage = _meter.create_counter(
    "cpg_llm_tokens_total",
    description="LLM token usage",
)


def set_cpg_span_attributes(
    span: Span,
    domain: str,
    workflow_type: str,
    risk_tier: str = "medium",
    agent_name: str = "",
    **extra: Any,
) -> None:
    span.set_attribute("industry", "cpg")
    span.set_attribute("business.domain", domain)
    span.set_attribute("workflow.type", workflow_type)
    span.set_attribute("gen_ai.model", "azure_openai_gpt4o")
    span.set_attribute("governance.risk_tier", risk_tier)
    if agent_name:
        span.set_attribute("cpg.agent.name", agent_name)
    for k, v in extra.items():
        span.set_attribute(k, str(v))


@contextmanager
def agent_span(agent_name: str, domain: str, risk_tier: str = "medium") -> Generator[Span, None, None]:
    """Context manager that wraps an agent execution in a named OTel span."""
    with _tracer.start_as_current_span(f"agent.{agent_name}") as span:
        set_cpg_span_attributes(
            span,
            domain=domain,
            workflow_type="specialist_agent",
            risk_tier=risk_tier,
            agent_name=agent_name,
        )
        agent_invocations.add(1, {"agent": agent_name, "domain": domain})
        try:
            yield span
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


@contextmanager
def supervisor_span(next_agent: str, session_id: str = "") -> Generator[Span, None, None]:
    with _tracer.start_as_current_span("supervisor.route") as span:
        span.set_attribute("supervisor.next_agent", next_agent)
        span.set_attribute("session.id", session_id)
        span.set_attribute("industry", "cpg")
        span.set_attribute("workflow.type", "supervisor_routing")
        supervisor_routings.add(1, {"next_agent": next_agent})
        yield span


def record_policy_decision(decision: str, sku: str, order_value: float) -> None:
    policy_decisions.add(1, {"decision": decision, "sku": sku})
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("policy.decision", decision)
        span.set_attribute("policy.sku", sku)
        span.set_attribute("policy.order_value_usd", order_value)


def record_token_usage(prompt_tokens: int, completion_tokens: int, agent: str) -> None:
    token_usage.add(prompt_tokens, {"token_type": "prompt", "agent": agent})
    token_usage.add(completion_tokens, {"token_type": "completion", "agent": agent})
