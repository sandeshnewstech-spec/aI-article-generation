import torch
from sentence_transformers import SentenceTransformer

# Load model globally to share across calls
# max_seq_length = 2048 to fit "up to about 2,000 tokens"
device = "cuda" if torch.cuda.is_available() else "cpu"

print(f"Loading BAAI/bge-m3 model on {device}...")
model = SentenceTransformer("BAAI/bge-m3", device=device)
model.max_seq_length = 2048

def embed_texts(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    """
    Embeds a list of texts using BAAI/bge-m3.
    Dense 1024-dim, normalized embeddings, Cosine.
    Truncates at 2048 tokens based on model.max_seq_length.
    """
    if not texts:
        return []
        
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True
    )
    
    # sentence_transformers returns a numpy array, convert to list[list[float]]
    return embeddings.tolist()
