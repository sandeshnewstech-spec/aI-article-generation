import asyncio
import sys
from app.services.scraper_service import ScraperService
from app.services.ai_service import AIService

async def verify():
    print("✅ Imports successful")
    
    scraper = ScraperService()
    print("✅ ScraperService initialized")
    
    ai = AIService()
    print("✅ AIService initialized")
    
    # We won't run full scrape/AI here to save time/cost, just ensuring classes load
    # and maybe check if playwright is installed by dry-running a browser launch?
    
    from playwright.async_api import async_playwright
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            await browser.close()
        print("✅ Playwright browser launch successful")
    except Exception as e:
        print(f"❌ Playwright error: {e}")
        print("Run 'playwright install' manually.")

if __name__ == "__main__":
    try:
        asyncio.run(verify())
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        sys.exit(1)
