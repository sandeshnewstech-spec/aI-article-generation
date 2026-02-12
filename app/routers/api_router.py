from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.services.article_aggregator import ArticleAggregator
from app.models.data import GenerationResult
import json
import asyncio

router = APIRouter()
aggregator = ArticleAggregator()

class GenerateRequest(BaseModel):
    topic: str

@router.post("/generate", response_model=GenerationResult)
async def generate_articles(request: GenerateRequest):
    """Legacy endpoint - returns all results at once"""
    try:
        if not request.topic:
            raise HTTPException(status_code=400, detail="Topic is required")
            
        result = await aggregator.process_topic(request.topic)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/generate-stream")
async def generate_articles_stream(topic: str):
    """SSE endpoint - streams results progressively"""
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")
    
    async def event_generator():
        try:
            async for event in aggregator.process_topic_streaming(topic):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
