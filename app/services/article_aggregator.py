from typing import List, Dict, AsyncGenerator
from collections import defaultdict
from app.services.scraper_service_sync import ScraperService
from app.services.ai_service import AIService
from app.models.data import ScrapedArticle, GenerationResult
import asyncio

class ArticleAggregator:
    def __init__(self):
        self.scraper = ScraperService()
        self.ai = AIService()

    async def process_topic_streaming(self, topic: str) -> AsyncGenerator[Dict, None]:
        """Stream results progressively as they're generated"""
        # 1. Scrape Articles
        print(f"[SCRAPE] Starting scrape for topic: {topic}")
        yield {"type": "status", "message": "Scraping articles..."}
        
        articles = await self.scraper.scrape_topic(topic)
        
        if not articles:
            print("[WARN] No articles found. Skipping AI generation.")
            yield {"type": "error", "message": "No articles found for this topic."}
            return
        
        print(f"[OK] Found {len(articles)} articles from {len(set(a.source for a in articles))} sources")
        yield {"type": "status", "message": f"Found {len(articles)} articles from {len(set(a.source for a in articles))} sources"}
        
        # 2. Generate three style variants (one at a time to respect rate limits)
        styles = [
            ("formal", "Formal Style"),
            ("conversational", "Conversational Style"),
            ("analytical", "Analytical Style")
        ]
        
        for style_key, style_name in styles:
            print(f"[AI] Generating {style_name}...")
            yield {"type": "status", "message": f"Generating {style_name}..."}
            
            try:
                prompt = self.ai.build_style_prompt(articles, topic, style_key)
                content = await self.ai.generate_content(prompt)
                yield {"type": "article", "style": style_key, "style_name": style_name, "content": content}
            except Exception as e:
                print(f"[WARN] Failed to generate {style_name}: {e}")
                yield {"type": "error", "style": style_key, "message": str(e)}
            
            # Wait between styles to respect rate limits (except after the last one)
            if style_key != "analytical":
                print("[INFO] Waiting 60s before next style...")
                yield {"type": "status", "message": "Waiting 60s before next style..."}
                await asyncio.sleep(60)
        
        # Final completion signal
        yield {"type": "complete", "topic": topic}

    async def process_topic(self, topic: str) -> GenerationResult:
        """Non-streaming version for backward compatibility"""
        import asyncio
        # 1. Scrape Articles
        print(f"[SCRAPE] Starting scrape for topic: {topic}")
        articles = await self.scraper.scrape_topic(topic)
        
        if not articles:
            print("[WARN] No articles found. Skipping AI generation.")
            return GenerationResult(
                topic=topic,
                formal_style="No articles found for this topic.",
                conversational_style="No articles found for this topic.",
                analytical_style="No articles found for this topic."
            )
        
        print(f"[OK] Found {len(articles)} articles from {len(set(a.source for a in articles))} sources")
        
        # 2. Generate three style variants (one at a time to respect rate limits)
        styles = {}
        style_keys = ["formal", "conversational", "analytical"]
        
        for i, style_key in enumerate(style_keys):
            print(f"[AI] Generating {style_key} style...")
            
            try:
                prompt = self.ai.build_style_prompt(articles, topic, style_key)
                content = await self.ai.generate_content(prompt)
                styles[style_key] = content
            except Exception as e:
                print(f"[WARN] Failed to generate {style_key} style: {e}")
                styles[style_key] = f"[Generation failed: {str(e)}]"
            
            # Wait between styles (except after the last one)
            if i < len(style_keys) - 1:
                print("[INFO] Waiting 60s before next style...")
                await asyncio.sleep(60)
            
        return GenerationResult(
            topic=topic,
            formal_style=styles.get("formal", "Generation failed"),
            conversational_style=styles.get("conversational", "Generation failed"),
            analytical_style=styles.get("analytical", "Generation failed")
        )
