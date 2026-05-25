"""RAG specialist: hybrid search over CPG policy documents, SOPs, and contracts."""
import os

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from src.agents.state import SupplyChainState
from src.observability.instrumentation import agent_span, record_token_usage
from src.tools.vector_store import get_retriever

_SYSTEM_PROMPT = """You are the CPG policy and knowledge specialist.
You answer questions about company procurement policies, SOPs, approval thresholds, and contracts using retrieved document excerpts.

Instructions:
1. Answer based only on the retrieved context — do not hallucinate policies.
2. Cite the source document for each key point (e.g. "per procurement_policy.txt section 2.1").
3. If the context doesn't contain the answer, say so clearly.
4. Be precise about thresholds, limits, and procedures."""


def _build_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        temperature=0,
    )


def rag_node(state: SupplyChainState) -> dict:
    with agent_span("rag", domain="governance", risk_tier=state.get("risk_tier", "medium")) as span:
        query = state["query"]
        retriever = get_retriever(k=5)
        docs = retriever.invoke(query)

        span.set_attribute("rag.retrieval_k", len(docs))
        span.set_attribute("rag.search_type", "mmr")
        span.set_attribute("rag.query_length", len(query))

        context_parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "unknown").split("\\")[-1].split("/")[-1]
            context_parts.append(f"[{i}] Source: {source}\n{doc.page_content}")
        context = "\n\n---\n\n".join(context_parts)

        llm = _build_llm()
        response = llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=f"Question: {query}\n\nRetrieved context:\n{context}"),
        ])

        result = response.content
        span.set_attribute("rag.response_length", len(result))
        usage = getattr(response, "usage_metadata", None) or {}
        record_token_usage(usage.get("input_tokens", 0), usage.get("output_tokens", 0), "rag")

    return {
        "agent_outputs": {**state.get("agent_outputs", {}), "rag": result},
        "messages": [AIMessage(content=f"[RAG Knowledge Agent]\n{result}")],
        "active_agent": "rag",
    }
