import asyncio
import urllib.parse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from typing import List, Optional
from app.models.data import ScrapedArticle

class ScraperService:
    SITES = [
        "gujaratsamachar.com",
        "aninews.in",
        "aajtak.in",
        "news18.com",
        "tv9gujarati.com",
        "sandesh.com",
    ]

    async def scrape_topic(self, topic: str, limit_per_site: int = 3) -> List[ScrapedArticle]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/121.0.0.0 Safari/537.36"
                )
            )

            results: List[ScrapedArticle] = []
            
            # Create tasks for all sites to run in parallel
            tasks = [
                self.scrape_one_site(context, topic, site, limit_per_site)
                for site in self.SITES
            ]
            
            site_results = await asyncio.gather(*tasks)
            
            await browser.close()
            
            # Flatten results
            for articles in site_results:
                results.extend(articles)
                
            return results

    async def scrape_one_site(self, context, topic: str, site: str, limit: int) -> List[ScrapedArticle]:
        page = await context.new_page()
        articles = []

        try:
            query = f"{topic} site:{site}"
            # Using html version for speed/simplicity as in original
            await page.goto("https://duckduckgo.com/html/", wait_until="domcontentloaded", timeout=15000)
            await page.fill("input[name='q']", query)
            await page.press("input[name='q']", "Enter")
            await page.wait_for_timeout(1000) # Reduced wait time

            links = await page.locator("a.result__a").all()
            hrefs = []

            for link in links:
                href = await link.get_attribute("href")
                if not href:
                    continue

                if href.startswith("/l/?uddg="):
                    parsed = urllib.parse.urlparse(href)
                    qs = urllib.parse.parse_qs(parsed.query)
                    href = urllib.parse.unquote(qs.get("uddg", [""])[0])

                if href.startswith("http"):
                    hrefs.append(href)

                if len(hrefs) >= limit:
                    break

            for href in hrefs:
                article = await self.scrape_article(context, href, site)
                if article:
                    articles.append(article)
                    
            return articles

        except Exception as e:
            print(f"Error searching {site}: {e}")
            return []
        finally:
            await page.close()

    async def scrape_article(self, context, url: str, site: str) -> Optional[ScrapedArticle]:
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)
            
            await self.expand_article_if_needed(page, site)

            # Get Title
            title = ""
            if await page.locator("h1").count() > 0:
                title = await page.locator("h1").first.text_content() or ""
            elif await page.locator("meta[property='og:title']").count() > 0:
                title = await page.locator("meta[property='og:title']").get_attribute("content") or ""

            if not title.strip():
                return None

            # Get Body
            body_text = await self.extract_body(page, url, site)
            if not body_text or len(body_text) < 100:
                return None

            return ScrapedArticle(
                source=site,
                url=url,
                title=title.strip(),
                body=" ".join(body_text.split())
            )

        except Exception as e:
            return None
        finally:
            await page.close()

    async def expand_article_if_needed(self, page, site: str):
        try:
            if "sandesh.com" in site:
                btn = page.locator("#postId button, #postId button span").filter(has_text="View")
                if await btn.count() > 0:
                    await btn.first.click()
                    await page.wait_for_timeout(800)
            elif "aajtak.in" in site:
                btn = page.locator("div.read-more-content button")
                if await btn.count() > 0:
                    await btn.first.click()
                    await page.wait_for_timeout(800)
            elif "news18.com" in site:
                btn = page.locator("span[id^='readmore_story'], span[class*='readmore'], span:has-text('Read More')")
                if await btn.count() > 0:
                    await btn.first.click()
                    await page.wait_for_timeout(800)
        except Exception:
            pass

    async def extract_body(self, page, url: str, site: str) -> str:
        if url.lower().endswith(".html"):
            return await page.evaluate("""
                () => {
                    const selectors = [
                        'article', '.article-content', '.article-body', '.story-details',
                        '.content', '.content-area', '.detailBody', '.news-description',
                        '.article-inner-detail', '.story'
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.length > 100) {
                            return el.innerText;
                        }
                    }
                    return document.body.innerText || '';
                }
            """)
        
        selectors = {
            "sandesh.com": "div[class^='story article-']",
            "gujaratsamachar.com": "div.article-inner-detail.card-body",
            "tv9gujarati.com": "div.detailBody",
            "aninews.in": "article",
            "aajtak.in": "div.content-area",
            "news18.com": "article[id^='story-']"
        }
        
        for k, v in selectors.items():
            if k in site:
                el = await page.query_selector(v)
                return await el.inner_text() if el else ""
                
        return await page.evaluate("document.body.innerText")
