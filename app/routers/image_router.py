from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from typing import List, Optional
from app.services.image_service import ImageService
import requests
import os

router = APIRouter(prefix="/image", tags=["image"])
service = ImageService()

class SearchRequest(BaseModel):
    query: str
    count: Optional[int] = 10

class GenerateRequest(BaseModel):
    prompt: str
    count: Optional[int] = 1

class AutoGenerateRequest(BaseModel):
    headline: str
    topic: str
    intro: Optional[str] = ""

@router.post("/search")
async def search_images(request: SearchRequest):
    try:
        return {"images": await service.get_images(request.query, request.count)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate")
async def generate_images(request: GenerateRequest):
    try:
        images = await service.generate_image(request.prompt, request.count)
        return {"images": images}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auto-generate")
async def auto_generate_image(request: AutoGenerateRequest):
    try:
        return await service.auto_generate_for_article(
            request.headline, request.topic, request.intro
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download")
async def download_image_proxy(url: str):
    """
    Proxy endpoint to download images from news sites.
    Bypasses hotlink protection and forces a browser download.
    """
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
        
    try:
        # Handle local static files differently (don't use requests for local files!)
        if url.startswith("/static"):
            # Normalize path (remove leading /)
            clean_path = url[1:] if url.startswith("/") else url
            full_path = clean_path # Should already be relative to project root
            
            # Fallback if app/ is not in the path
            if not os.path.exists(full_path) and not full_path.startswith("app/"):
                full_path = os.path.join("app", full_path)
            
            if os.path.exists(full_path):
                from fastapi.responses import FileResponse
                filename = full_path.split("/")[-1]
                
                # SMART MIME DETECTION (Fallback for files with wrong extensions)
                media_type = None
                try:
                    with open(full_path, "rb") as f:
                        header = f.read(16)
                        if b"ftypavif" in header: media_type = "image/avif"
                        elif b"RIFF" in header and b"WEBP" in header: media_type = "image/webp"
                        elif header.startswith(b"\x89PNG"): media_type = "image/png"
                        elif header.startswith(b"\xff\xd8"): media_type = "image/jpeg"
                except:
                    pass

                return FileResponse(
                    path=full_path,
                    filename=filename,
                    media_type=media_type # If None, FileResponse guesses from extension
                )
            else:
                print(f"[ERROR] Local download failed: file not found at {full_path}")
                raise HTTPException(status_code=404, detail="File not found")

        # Handle external URLs
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': url 
        }
        
        # Use streaming for better reliability
        response = requests.get(url, headers=headers, timeout=12, stream=True)
        response.raise_for_status()
        
        content_type = response.headers.get('Content-Type', 'image/jpeg')
        filename = url.split('/')[-1].split('?')[0] or "news_image.jpg"
        if not any(filename.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
             # Map content-type to common extension
             if "png" in content_type: filename += ".png"
             elif "webp" in content_type: filename += ".webp"
             else: filename += ".jpg"

        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            response.iter_content(chunk_size=8192),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        print(f"[ERROR] Proxy download failed for {url}: {e}")
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=url)
