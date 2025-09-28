"""
RFP RAG Module

Integrates LightRAG for indexing and querying RFP content.
Uses Ollama models for local, zero-cost RAG.
"""

import asyncio
import os
from typing import Dict, Optional
from lightrag import LightRAG, QueryParam
from lightrag.llm.ollama import ollama_model_complete, ollama_embed
from lightrag.utils import EmbeddingFunc
from lightrag.kg.shared_storage import initialize_pipeline_status
from dotenv import load_dotenv

load_dotenv()


class RFPRAG:
    """
    LightRAG wrapper for RFP processing.
    Handles initialization, indexing, and querying.
    """

    def __init__(self, working_dir: str = "./rfp_rag_data"):
        """
        Initialize RFP RAG instance.

        Args:
            working_dir: Directory for storing RAG data
        """
        self.working_dir = working_dir
        self.rag: Optional[LightRAG] = None

    async def initialize(self):
        """
        Initialize the LightRAG instance with Ollama models.
        """
        if not os.path.exists(self.working_dir):
            os.makedirs(self.working_dir)

        # Configure Ollama models (from demo)
        llm_model_name = os.getenv("LLM_MODEL", "qwen2.5-coder:7b")
        embedding_model = os.getenv("EMBEDDING_MODEL", "bge-m3:latest")

        self.rag = LightRAG(
            working_dir=self.working_dir,
            llm_model_func=ollama_model_complete,
            llm_model_name=llm_model_name,
            summary_max_tokens=8192,
            llm_model_kwargs={
                "host": os.getenv("LLM_BINDING_HOST", "http://localhost:11434"),
                "options": {"num_ctx": 8192},
                "timeout": int(os.getenv("TIMEOUT", "600")),  # Increased from 300 to 600
            },
            embedding_func=EmbeddingFunc(
                embedding_dim=int(os.getenv("EMBEDDING_DIM", "1024")),
                max_token_size=int(os.getenv("MAX_EMBED_TOKENS", "8192")),
                func=lambda texts: ollama_embed(
                    texts,
                    embed_model=embedding_model,
                    host=os.getenv("EMBEDDING_BINDING_HOST", "http://localhost:11434"),
                ),
            ),
        )

        await self.rag.initialize_storages()
        await initialize_pipeline_status()

    async def index_rfp(self, rfp_text: str, file_path: str = None):
        """
        Index RFP text into the knowledge graph using LightRAG's native document processing.

        Args:
            rfp_text: Full RFP text to index
            file_path: Optional file path for the document
        """
        if not self.rag:
            await self.initialize()

        # Use LightRAG's native document processing pipeline
        track_id = await self.rag.apipeline_enqueue_documents(
            input=rfp_text,
            file_paths=[file_path] if file_path else None
        )
        print(f"Enqueued RFP document for processing with track_id: {track_id}")
        return track_id

    async def query_rfp(self, query: str, mode: str = "hybrid") -> str:
        """
        Query the RFP knowledge base.

        Args:
            query: Question about the RFP
            mode: Query mode (naive, local, global, hybrid, mix)

        Returns:
            Response from RAG
        """
        if not self.rag:
            await self.initialize()

        param = QueryParam(mode=mode, stream=False)
        response = await self.rag.aquery(query, param=param)
        return str(response)

    async def close(self):
        """
        Clean up RAG resources.
        """
        if self.rag:
            await self.rag.finalize_storages()

    async def get_processed_documents(self, track_id: str = None):
        """
        Retrieve processed documents from LightRAG storage.

        Args:
            track_id: Optional track_id to filter documents

        Returns:
            Dict of document_id -> document_content
        """
        if not self.rag:
            await self.initialize()

        documents = {}

        if track_id:
            # Get documents by track_id
            doc_statuses = await self.rag.aget_docs_by_track_id(track_id)
            doc_ids = list(doc_statuses.keys())
        else:
            # Get all documents
            all_docs = await self.rag.full_docs.get_all()
            doc_ids = list(all_docs.keys())

        # Retrieve full content for each document
        for doc_id in doc_ids:
            try:
                doc_data = await self.rag.full_docs.get_by_id(doc_id)
                if doc_data and 'content' in doc_data:
                    documents[doc_id] = doc_data['content']
            except Exception as e:
                print(f"Error retrieving document {doc_id}: {e}")

        return documents


# Global instance for reuse
_rfp_rag_instance: Optional[RFPRAG] = None


async def get_rfp_rag() -> RFPRAG:
    """
    Get or create the global RFP RAG instance.
    """
    global _rfp_rag_instance
    if not _rfp_rag_instance:
        _rfp_rag_instance = RFPRAG()
        await _rfp_rag_instance.initialize()
    return _rfp_rag_instance


# Example usage
async def main():
    rag = await get_rfp_rag()
    sample_text = "This is a sample RFP with requirements for Section A deadlines."
    track_id = await rag.index_rfp(sample_text, "sample_rfp.txt")

    response = await rag.query_rfp("What are the deadlines in Section A?")
    print(response)

    # Retrieve and print processed documents
    documents = await rag.get_processed_documents(track_id)
    print("Processed documents:", documents)

    await rag.close()


if __name__ == "__main__":
    asyncio.run(main())