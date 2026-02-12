import urllib.parse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from typing import List, Optional
from app.models.data import ScrapedArticle
import asyncio
from concurrent.futures import ThreadPoolExecutor

class ScraperService:
    SITES = [
        "gujaratsamachar.com",
        "aninews.in",
        "aajtak.in",
        "news18.com",
        "tv9gujarati.com",
        "sandesh.com",
    ]

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=6)

    async def scrape_topic(self, topic: str, limit_per_site: int = 3) -> List[ScrapedArticle]:
        """Async wrapper around sync scraping to avoid Windows event loop issues"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self._scrape_topic_sync, topic, limit_per_site)

    def _scrape_topic_sync(self, topic: str, limit_per_site: int) -> List[ScrapedArticle]:
        """Synchronous scraping using sync_playwright"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # Visible browser
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/121.0.0.0 Safari/537.36"
                )
            )

            results: List[ScrapedArticle] = []
            
            # Scrape each site sequentially in sync mode
            for site in self.SITES:
                articles = self._scrape_one_site(context, topic, site, limit_per_site)
                results.extend(articles)
                
            browser.close()
            return results

    def _scrape_one_site(self, context, topic: str, site: str, limit: int) -> List[ScrapedArticle]:
        page = context.new_page()
        articles = []

        try:
            query = f"{topic} site:{site}"
            print(f"🔍 Searching {site}...")
            
            # Use regular DuckDuckGo (not HTML version)
            page.goto("https://duckduckgo.com/", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)
            
            # Fill search with explicit wait for input
            try:
                page.wait_for_selector("input[name='q']", timeout=10000)
                page.fill("input[name='q']", query)
                page.wait_for_timeout(500)
                page.keyboard.press("Enter")
                page.wait_for_timeout(4000)  # Wait for results
            except Exception as e:
                print(f"⚠️ Search input failed for {site}: {e}")
                return []

            # Look for result links (regular DuckDuckGo uses different selectors)
            links = page.locator("article h2 a, [data-testid='result-title-a']").all()
            hrefs = []

            for link in links:
                href = link.get_attribute("href")
                if not href:
                    continue

                # Regular DuckDuckGo uses direct URLs (no redirect encoding)
                if href.startswith("http"):
                    hrefs.append(href)

                if len(hrefs) >= limit:
                    break

            if not hrefs:
                print(f"⚠️ No results found for {site}")
                return []

            for href in hrefs:
                article = self._scrape_article(context, href, site)
                if article:
                    articles.append(article)
                    print(f"✅ Scraped article from {site}")
                    
            return articles

        except Exception as e:
            print(f"❌ Error searching {site}: {e}")
            return []
        finally:
            page.close()

    def _scrape_article(self, context, url: str, site: str) -> Optional[ScrapedArticle]:
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1000)
            
            self._expand_article_if_needed(page, site)

            # Get Title
            title = ""
            if page.locator("h1").count() > 0:
                title = page.locator("h1").first.text_content() or ""
            elif page.locator("meta[property='og:title']").count() > 0:
                title = page.locator("meta[property='og:title']").get_attribute("content") or ""

            if not title.strip():
                return None

            # Get Body
            body_text = self._extract_body(page, url, site)
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
            page.close()

    def _expand_article_if_needed(self, page, site: str):
        try:
            if "sandesh.com" in site:
                btn = page.locator("#postId button, #postId button span").filter(has_text="View")
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(800)
            elif "aajtak.in" in site:
                btn = page.locator("div.read-more-content button")
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(800)
            elif "news18.com" in site:
                btn = page.locator("span[id^='readmore_story'], span[class*='readmore'], span:has-text('Read More')")
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(800)
        except Exception:
            pass

    def _extract_body(self, page, url: str, site: str) -> str:
        if url.lower().endswith(".html"):
            return page.evaluate("""
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
                el = page.query_selector(v)
                return el.inner_text() if el else ""
                
        return page.evaluate("document.body.innerText")
