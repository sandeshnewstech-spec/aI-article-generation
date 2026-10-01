import os
import sys
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from app.services.embedding_service import embed_texts

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(WORKSPACE, ".env")
load_dotenv(dotenv_path=env_path)

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_ENV = os.getenv("QDRANT_ENV", "dev")
EPAPER_COLLECTION_BASE = os.getenv("EPAPER_COLLECTION_BASE", "epaper_items")

COLLECTION_NAME = f"{QDRANT_ENV}_{EPAPER_COLLECTION_BASE}"
VECTOR_DIM = 1024 # Same as BAAI/bge-m3

class EPaperRetrievalService:
    def __init__(self):
        if not QDRANT_URL or not QDRANT_API_KEY:
            raise ValueError("QDRANT_URL or QDRANT_API_KEY not found in .env")
        
        self.client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    def _get_embedding(self, text: str) -> list[float]:
        # Use shared sentence-transformers embedding service
        embeddings = embed_texts([text])
        return embeddings[0]

    def search_articles(self, query_text: str, category: Optional[str] = None, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar articles."""
        if not self.client.collection_exists(COLLECTION_NAME):
            return []

        vector = self._get_embedding(query_text)
        
        # Enforce doc_type="article"
        must_conditions = [
            FieldCondition(
                key="doc_type",
                match=MatchValue(value="article")
            )
        ]
        
        if category:
            must_conditions.append(
                FieldCondition(
                    key="category",
                    match=MatchValue(value=category)
                )
            )

        query_filter = Filter(must=must_conditions)

        results = self.client.search(
            collection_name=COLLECTION_NAME,
            query_vector=("full", vector),
            query_filter=query_filter,
            limit=top_k
        )
        return [hit.payload for hit in results]
        
    def search_headlines(self, query_text: str, category: Optional[str] = None, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search specifically against the headline vector for articles."""
        if not self.client.collection_exists(COLLECTION_NAME):
            return []

        vector = self._get_embedding(query_text)
        
        # Enforce doc_type="article"
        must_conditions = [
            FieldCondition(
                key="doc_type",
                match=MatchValue(value="article")
            )
        ]
        
        if category:
            must_conditions.append(
                FieldCondition(
                    key="category",
                    match=MatchValue(value=category)
                )
            )

        query_filter = Filter(must=must_conditions)

        results = self.client.search(
            collection_name=COLLECTION_NAME,
            query_vector=("headline", vector),
            query_filter=query_filter,
            limit=top_k
        )
        return [hit.payload for hit in results]

    def search_ads(self, query_text: str, ad_type: Optional[str] = None, top_k: int = 3) -> List[Dict[str, Any]]:
        """Search for similar ads."""
        if not self.client.collection_exists(COLLECTION_NAME):
            return []

        vector = self._get_embedding(query_text)
        
        # Enforce doc_type="ad"
        must_conditions = [
            FieldCondition(
                key="doc_type",
                match=MatchValue(value="ad")
            )
        ]
        
        if ad_type:
            must_conditions.append(
                FieldCondition(
                    key="ad_type",
                    match=MatchValue(value=ad_type)
                )
            )

        query_filter = Filter(must=must_conditions)

        results = self.client.search(
            collection_name=COLLECTION_NAME,
            query_vector=("full", vector),
            query_filter=query_filter,
            limit=top_k
        )
        return [hit.payload for hit in results]

epaper_retrieval_service = EPaperRetrievalService()
