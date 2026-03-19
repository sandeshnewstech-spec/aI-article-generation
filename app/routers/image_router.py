"""
Image Router
Endpoints:
  POST /api/image/search         - Search relevant images for a query
  POST /api/image/generate       - Generate AI image using Gemini Imagen
  POST /api/image/auto-generate  - Auto-generate from article content (Gujarati -> English prompt -> Imagen)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from app.services.image_service import ImageService

router = APIRouter(prefix="/image", tags=["image"])

image_service = ImageService()


# ─────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────

class ImageSearchRequest(BaseModel):
    query: str = Field(description="Search query / news topic")
    max_results: int = Field(default=10, ge=1, le=30, description="Max number of images")


class ImageResult(BaseModel):
    title: str
    image_url: str
    thumbnail_url: str
    source_url: str
    width: int
    height: int
    source: str


class ImageSearchResponse(BaseModel):
    query: str
    total: int
    images: List[ImageResult]


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(description="Prompt for AI image generation")
    count: int = Field(default=1, ge=1, le=4, description="Number of images (max 4)")


class GeneratedImage(BaseModel):
    base64_image: Optional[str] = None
    image_url: Optional[str] = None
    mime_type: str = "image/jpeg"
    prompt: str


class ImageGenerateResponse(BaseModel):
    prompt: str
    count: int
    images: List[GeneratedImage]


class AutoGenerateRequest(BaseModel):
    """Auto generate image from Gujarati article content"""
    headline: str = Field(description="Article headline (Gujarati OK)")
    topic: str = Field(description="Article topic (Gujarati OK)")
    intro: Optional[str] = Field(default="", description="Article intro paragraph (optional)")


class AutoGenerateResponse(BaseModel):
    success: bool
    image_url: Optional[str] = None      # Pollinations.ai URL (FREE)
    base64_image: Optional[str] = None  # Gemini Imagen base64 (PAID, legacy)
    mime_type: Optional[str] = None
    prompt_used: Optional[str] = None
    error: Optional[str] = None


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@router.post("/search", response_model=ImageSearchResponse)
async def search_images(request: ImageSearchRequest):
    """Search for relevant images using DuckDuckGo Image Search."""
    try:
        print(f"[IMAGE] Searching images for: '{request.query}'")
        results = await image_service.get_images(request.query, request.max_results)
        return ImageSearchResponse(
            query=request.query,
            total=len(results),
            images=[ImageResult(**img) for img in results],
        )
    except Exception as e:
        print(f"[ERROR] Image search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Image search failed: {str(e)}")


@router.post("/generate", response_model=ImageGenerateResponse)
async def generate_image(request: ImageGenerateRequest):
    """Generate an AI image using Google Gemini Imagen API."""
    try:
        if not request.prompt.strip():
            raise HTTPException(status_code=400, detail="Prompt cannot be empty")
        print(f"[IMAGE] Generating {request.count} image(s) for: '{request.prompt[:60]}'")
        results = await image_service.generate_image(request.prompt, request.count)
        return ImageGenerateResponse(
            prompt=request.prompt,
            count=len(results),
            images=[GeneratedImage(**img) for img in results],
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Image generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")


@router.post("/auto-generate", response_model=AutoGenerateResponse)
async def auto_generate_image(request: AutoGenerateRequest):
    """
    Automatically generate a relevant news image from Gujarati article content.

    Flow:
      1. Gemini text reads Gujarati headline/topic/intro
      2. Creates a descriptive English prompt
      3. Gemini Imagen generates the image
      4. Returns base64 PNG

    NOTE: Requires Gemini Imagen API access (paid tier).
    """
    try:
        print(f"[IMAGE-AUTO] Auto-generating for: '{request.headline[:60]}'")
        result = await image_service.auto_generate_for_article(
            headline=request.headline,
            topic=request.topic,
            intro=request.intro or "",
        )
        return AutoGenerateResponse(**result)
    except Exception as e:
        print(f"[ERROR] Auto image generation failed: {e}")
        return AutoGenerateResponse(success=False, error=str(e))
