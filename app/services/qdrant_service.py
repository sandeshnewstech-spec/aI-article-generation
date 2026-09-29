import os
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from fastembed import TextEmbedding

# Store qdrant data locally inside the app directory
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qdrant_data")
COLLECTION_NAME = "advt_exemplars"

class QdrantService:
    def __init__(self):
        # Initializes a local file-based Qdrant database (no docker needed)
        self.client = QdrantClient(path=DB_PATH)
        # Using a fast, lightweight local embedding model
        self.embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        self._ensure_collection()
        
    def _ensure_collection(self):
        if not self.client.collection_exists(COLLECTION_NAME):
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )
            # Create index to filter by advertisement type (e.g., 'legal notice')
            self.client.create_payload_index(COLLECTION_NAME, "advt_type", field_schema="keyword")
            
    def _get_embedding(self, text: str) -> list[float]:
        # fastembed returns an iterator of numpy arrays
        embeddings = list(self.embedding_model.embed([text]))
        return embeddings[0].tolist()
        
    def add_exemplar(self, original_text: str, parsed_json: str, advt_type: str):
        """Adds a verified ad to Qdrant"""
        vector = self._get_embedding(original_text)
        point_id = str(uuid.uuid4())
        
        payload = {
            "original_text": original_text,
            "parsed_json": parsed_json,
            "advt_type": advt_type.lower() if advt_type else "unknown"
        }
        
        self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(id=point_id, vector=vector, payload=payload)
            ]
        )
        return point_id

    def get_exemplars(self, text: str, advt_type: str = None, top_k: int = 3) -> list[dict]:
        """Finds most similar past ads for few-shot prompting"""
        if not self.client.collection_exists(COLLECTION_NAME):
            return []
            
        vector = self._get_embedding(text)
        
        # Filter by advt_type if provided
        query_filter = None
        if advt_type:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="advt_type",
                        match=MatchValue(value=advt_type.lower())
                    )
                ]
            )
            
        results = self.client.search(
            collection_name=COLLECTION_NAME,
            query_vector=vector,
            query_filter=query_filter,
            limit=top_k
        )
        
        return [hit.payload for hit in results]

# Singleton instance
qdrant_service = QdrantService()
