"""
Image Service
- get_images: Fetches images from DuckDuckGo (with improved headers)
- generate_image: Generates AI image using Google Gemini Imagen (paid)
- auto_generate_for_article: FREE image generation via Pollinations.ai (no API key)
"""

import urllib.parse
import asyncio
import httpx
import re
import os
import uuid
from typing import List, Optional
from app.core.config import settings


class ImageService:
    """Service for fetching and generating images for news articles"""

    # Pollinations.ai — 100% FREE, no API key, no signup
    POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"

    DUCKDUCKGO_SEARCH_URL = "https://duckduckgo.com/"
    DUCKDUCKGO_IMAGE_URL  = "https://duckduckgo.com/i.js"

    # Rich browser-like headers to avoid DDG 403
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://duckduckgo.com/",
        "Origin": "https://duckduckgo.com",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    # ─────────────────────────────────────────────────────────────────
    # FREE: Auto-Generate image using Pollinations.ai (no API key)
    # ─────────────────────────────────────────────────────────────────

    async def auto_generate_for_article(
        self, headline: str, topic: str, intro: str = ""
    ) -> dict:
        """
        FREE image generation using Pollinations.ai.

        Steps:
        1. Use Gemini text to translate Gujarati content -> English image prompt
        2. Build a Pollinations.ai URL (100% free, no key needed)
        3. Return the image URL — frontend <img src="..."> directly

        Returns: {success, image_url, prompt_used} or {success: False, error}
        """
        try:
            # Step 1: Build English prompt using Gemini text
            english_prompt = await asyncio.get_event_loop().run_in_executor(
                None,
                self._build_image_prompt_sync,
                headline, topic, intro
            )
            print(f"[IMAGE-FREE] Prompt: {english_prompt[:100]}")

            # Step 2: Build Pollinations URL (returns image directly)
            encoded = urllib.parse.quote(english_prompt, safe="")
            image_url = (
                f"{self.POLLINATIONS_BASE}/{encoded}"
                f"?width=1280&height=720&model=flux&nologo=true&enhance=true"
            )

            # Step 3: Verify the URL is reachable (quick HEAD check)
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    r = await client.head(image_url)
                    if r.status_code >= 400:
                        raise ValueError(f"Pollinations returned {r.status_code}")
            except Exception:
                # If HEAD fails, still return URL — browser will try
                pass

            return {
                "success": True,
                "image_url": image_url,
                "prompt_used": english_prompt,
            }

        except Exception as e:
            print(f"[IMAGE-FREE ERROR] {e}")
            return {"success": False, "error": str(e)}

    def _build_image_prompt_sync(self, headline: str, topic: str, intro: str) -> str:
        """
        Use Gemini text to translate Gujarati article info into
        a descriptive English image generation prompt.
        """
        from google import genai

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        system_prompt = f"""You are an expert at creating image generation prompts for news photos.

Given this news article information (may be in Gujarati):
TOPIC: {topic}
HEADLINE: {headline}
INTRO: {intro[:300] if intro else ''}

Create a SHORT, VIVID, DESCRIPTIVE image generation prompt in English (max 80 words) that:
1. Visually captures the core subject of this news story
2. Suitable for a professional newspaper front page photo
3. Describes the scene, people, setting, lighting, and mood clearly
4. NO text, headlines, watermarks, or overlays in the image
5. Photorealistic news photography style

Output ONLY the prompt text. No explanation, no quotes, just the raw prompt."""

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=system_prompt,
        )

        prompt = response.text.strip().strip('"').strip("'").strip()
        prompt += ", photorealistic, professional news photography, high resolution, natural daylight"
        return prompt

    # ─────────────────────────────────────────────────────────────────
    # SEARCH: Images via DuckDuckGo (improved anti-403 headers)
    # ─────────────────────────────────────────────────────────────────

    async def get_images(self, query: str, max_results: int = 10) -> List[dict]:
        """
        Search for images relevant to the query using DuckDuckGo.
        Falls back to Pollinations search results if DDG fails.
        """
        try:
            token = await self._get_ddg_token(query)
            if not token:
                print(f"[IMAGE] DDG token failed, using Pollinations fallback")
                return self._pollinations_search_fallback(query, max_results)

            images = await self._fetch_ddg_images(query, token, max_results)
            print(f"[IMAGE] Found {len(images)} images for '{query}'")

            if not images:
                return self._pollinations_search_fallback(query, max_results)

            return images

        except Exception as e:
            print(f"[IMAGE ERROR] get_images failed: {e}")
            return self._pollinations_search_fallback(query, max_results)

    def _pollinations_search_fallback(self, query: str, count: int) -> List[dict]:
        """
        Fallback: Generate variation images via Pollinations when DDG fails.
        Returns image dicts in the same format as DDG results.
        """
        results = []
        prompts = [
            f"news photo about {query}, professional journalism",
            f"documentary photo of {query}, editorial style",
            f"{query}, photorealistic news coverage",
        ]
        for i, p in enumerate(prompts[:count]):
            encoded = urllib.parse.quote(p, safe="")
            url = f"{self.POLLINATIONS_BASE}/{encoded}?width=800&height=500&model=flux&nologo=true&seed={i+1}"
            results.append({
                "title": f"{query} - Image {i+1}",
                "image_url": url,
                "thumbnail_url": url,
                "source_url": url,
                "width": 800,
                "height": 500,
                "source": "Pollinations.ai (Free)",
            })
        return results

    async def _get_ddg_token(self, query: str) -> Optional[str]:
        """Get DuckDuckGo vqd token required for image search"""
        try:
            async with httpx.AsyncClient(
                headers=self.HEADERS, timeout=12.0, follow_redirects=True
            ) as client:
                # GET first to get cookies
                await client.get(self.DUCKDUCKGO_SEARCH_URL)
                # Then POST search
                resp = await client.get(
                    self.DUCKDUCKGO_SEARCH_URL,
                    params={"q": query, "ia": "images"},
                )
                text = resp.text
                match = re.search(r'vqd=(["\'])([^"\']+)\1', text)
                if match:
                    return match.group(2)
                match = re.search(r"vqd=([\d-]+)", text)
                if match:
                    return match.group(1)
                # Try header
                vqd_header = resp.headers.get("X-DuckDuckGo-Locale")
                return None
        except Exception as e:
            print(f"[IMAGE-DDG] Token fetch error: {e}")
            return None

    async def _fetch_ddg_images(self, query: str, token: str, max_results: int) -> List[dict]:
        """Fetch image results from DuckDuckGo using vqd token"""
        params = {
            "l": "us-en",
            "o": "json",
            "q": query,
            "vqd": token,
            "f": ",,,",
            "p": "1",
        }
        async with httpx.AsyncClient(
            headers=self.HEADERS, timeout=15.0, follow_redirects=True
        ) as client:
            resp = await client.get(self.DUCKDUCKGO_IMAGE_URL, params=params)
            if resp.status_code != 200:
                print(f"[IMAGE] DDG returned status {resp.status_code}")
                return []

            data = resp.json()
            results = data.get("results", [])
            images = []
            for item in results[:max_results]:
                images.append({
                    "title": item.get("title", ""),
                    "image_url": item.get("image", ""),
                    "thumbnail_url": item.get("thumbnail", ""),
                    "source_url": item.get("url", ""),
                    "width": item.get("width", 0),
                    "height": item.get("height", 0),
                    "source": item.get("source", ""),
                })
            return images

    # ─────────────────────────────────────────────────────────────────
    # GENERATE: Image via Hugging Face Inference API (Free/Limited)
    # ─────────────────────────────────────────────────────────────────

    async def generate_image(self, prompt: str, count: int = 1) -> List[dict]:
        """
        Generate image(s) using Hugging Face (FLUX) or Pollinations.ai (FREE).
        """
        results = []
        
        # 1. Hugging Face - Best if API Key is set
        # NEW 2026 Router URL: https://router.huggingface.co/hf-inference/models/
        if settings.HUGGINGFACE_API_KEY:
            model_id = "stabilityai/stable-diffusion-xl-base-1.0"
            api_url = f"https://router.huggingface.co/hf-inference/models/{model_id}"
            headers = {
                "Authorization": f"Bearer {settings.HUGGINGFACE_API_KEY}",
                "Content-Type": "application/json"
            }
            
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    for i in range(min(count, 4)):
                        print(f"[IMAGE-HF] Generating {i+1} via HF '{model_id}'...")
                        payload = {
                            "inputs": prompt, 
                            "parameters": {"seed": i + 100},
                            "options": {"wait_for_model": True}
                        }
                        
                        resp = await client.post(api_url, headers=headers, json=payload)
                        if resp.status_code == 200:
                            import base64
                            b64 = base64.b64encode(resp.content).decode("utf-8")
                            results.append({
                                "base64_image": b64,
                                "mime_type": "image/png", # Match user snippet preference
                                "prompt": prompt,
                            })
                        elif resp.status_code == 403:
                            print(f"[IMAGE-HF] ERROR 403: Insufficient permissions. Please enable 'Inference Providers' in your HF account settings.")
                            break
                        elif resp.status_code in [503, 410, 404]:
                            print(f"[IMAGE-HF] Status {resp.status_code}, skipping to Pollinations.")
                            break 
                        else:
                            print(f"[IMAGE-HF] Status {resp.status_code}: {resp.text[:50]}")
                            break
            except Exception as e:
                print(f"[IMAGE-HF ERROR] {e}")

        # 2. POLLINATIONS Fallback (100% Free, NO key needed)
        # If we didn't get enough images from HF, or HF is not configured
        if len(results) < count:
            remaining = count - len(results)
            print(f"[IMAGE-FREE] Generating {remaining} images via Pollinations (Unlimited Free Tier)")
            
            # Clean and shorten prompt for Pollinations reliability
            clean_prompt = prompt[:200] # Long prompts often fail on cloud workers
            encoded = urllib.parse.quote(clean_prompt, safe="")

            for i in range(remaining):
                seed = i + 1000 
                # Try a more stable model (turbo) if flux is failing
                url = (
                    f"https://pollinations.ai/p/{encoded}"
                    f"?width=1024&height=768&model=turbo&nologo=true&seed={seed}"
                )
                
                results.append({
                    "image_url": url,
                    "prompt": prompt,
                    "source": "Pollinations.ai (Free)",
                })
        
        return results

    # ─────────────────────────────────────────────────────────────────
    # PERSISTENCE: Save external images to local disk
    # ─────────────────────────────────────────────────────────────────

    async def persist_scraped_image(self, url: str) -> Optional[str]:
        """
        Download an external image and save it locally in app/static/scraped_images/.
        Returns the local URL path (e.g. /static/scraped_images/abc.jpg)
        """
        if not url or not url.startswith("http"):
            return url

        try:
            # Create local dir if not exists
            base_dir = "app/static/scraped_images"
            if not os.path.exists(base_dir):
                os.makedirs(base_dir, exist_ok=True)

            async with httpx.AsyncClient(headers=self.HEADERS, timeout=12.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return url # return original if download fails

                # Get extension from content-type (Modern news sites use AVIF/HEIC)
                ext = ".jpg"
                ctype = resp.headers.get("Content-Type", "").lower()
                if "png" in ctype: ext = ".png"
                elif "webp" in ctype: ext = ".webp"
                elif "avif" in ctype: ext = ".avif"
                elif "heic" in ctype: ext = ".heic"
                elif "heif" in ctype: ext = ".heif"
                elif "gif" in ctype: ext = ".gif"
                elif "svg" in ctype: ext = ".svg"

                # Generate unique filename
                filename = f"{uuid.uuid4().hex}{ext}"
                filepath = os.path.join(base_dir, filename)

                with open(filepath, "wb") as f:
                    f.write(resp.content)

                print(f"[IMAGE-STORE] Saved locally: {filename}")
                return f"/static/scraped_images/{filename}"

        except Exception as e:
            print(f"[IMAGE-STORE ERROR] Failed to persist {url}: {e}")
            return url # Fallback to original

