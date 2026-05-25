"""ChromaDB vector store setup with hybrid retrieval for the RAG agent."""
import os
from pathlib import Path
from typing import Optional

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain_openai import AzureOpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

_POLICY_DOCS_DIR = Path(__file__).parent.parent / "data" / "policy_docs"
_CHROMA_PERSIST_DIR = Path(__file__).parent.parent.parent / ".chroma_db"
_COLLECTION_NAME = "cpg_policy_docs"

_vectorstore: Optional[Chroma] = None


def _build_embeddings() -> AzureOpenAIEmbeddings:
    return AzureOpenAIEmbeddings(
        azure_deployment=os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
    )


def _ingest_documents(embeddings: AzureOpenAIEmbeddings) -> Chroma:
    loader = DirectoryLoader(
        str(_POLICY_DOCS_DIR),
        glob="*.txt",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=100)
    chunks = splitter.split_documents(docs)
    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=_COLLECTION_NAME,
        persist_directory=str(_CHROMA_PERSIST_DIR),
    )


def get_vectorstore() -> Chroma:
    global _vectorstore
    if _vectorstore is not None:
        return _vectorstore
    embeddings = _build_embeddings()
    if _CHROMA_PERSIST_DIR.exists():
        _vectorstore = Chroma(
            collection_name=_COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=str(_CHROMA_PERSIST_DIR),
        )
    else:
        _vectorstore = _ingest_documents(embeddings)
    return _vectorstore


def get_retriever(k: int = 5):
    """Return a hybrid retriever (mmr approximates diversity-aware retrieval)."""
    vs = get_vectorstore()
    return vs.as_retriever(
        search_type="mmr",
        search_kwargs={"k": k, "fetch_k": k * 3},
    )


def reingest() -> None:
    """Force re-ingestion of all policy docs (use after updating documents)."""
    global _vectorstore
    import shutil
    if _CHROMA_PERSIST_DIR.exists():
        shutil.rmtree(_CHROMA_PERSIST_DIR)
    _vectorstore = None
    embeddings = _build_embeddings()
    _vectorstore = _ingest_documents(embeddings)
