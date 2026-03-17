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
        "divyabhaskar.co.in",
    ]

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=6)

    async def scrape_topic(
        self,
        topic: str,
        limit_per_site: int = 3,
        allowed_sites: Optional[List[str]] = None,
    ) -> List[ScrapedArticle]:
        """Async wrapper around sync scraping to avoid Windows event loop issues"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor, self._scrape_topic_sync, topic, limit_per_site, allowed_sites
        )

    def _scrape_topic_sync(
        self, topic: str, limit_per_site: int, allowed_sites: Optional[List[str]] = None
    ) -> List[ScrapedArticle]:
        """Synchronous scraping using the generator to build a full list"""
        results = []
        sites = allowed_sites if allowed_sites else self.SITES
        for chunk in self._scrape_sites_generator(topic, limit_per_site, sites):
            results.extend(chunk["articles"])
        return results

    def _scrape_sites_generator(
        self, topic: str, limit_per_site: int, sites: List[str]
    ):
        """Generator that yields results site by site for real-time progress"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # Visible browser
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/121.0.0.0 Safari/537.36"
                )
            )

            for site in sites:
                try:
                    articles = self._scrape_one_site(
                        context, topic, site, limit_per_site
                    )
                    yield {"site": site, "articles": articles}
                except Exception as e:
                    print(f"[WARN] Failed site {site}: {e}")
                    yield {"site": site, "articles": [], "error": str(e)}

            browser.close()

    def _scrape_one_site(
        self, context, topic: str, site: str, limit: int
    ) -> List[ScrapedArticle]:
        page = context.new_page()
        articles = []

        try:
            # Use direct search URL to save time and reduce bot detection on homepage
            query = f"{topic} site:{site}"
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://duckduckgo.com/?q={encoded_query}"
            
            print(f"[SCRAPE] Searching {site} via {search_url}")
            
            # Use domcontentloaded for speed, then wait briefly for results
            page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000) # Give scripts time to load results

            # Robust selectors for DDG results
            result_selectors = [
                "article h2 a",
                "[data-testid='result-title-a']",
                ".result__a",
                "a.result-link"
            ]
            
            hrefs = []
            for selector in result_selectors:
                links = page.locator(selector).all()
                if links:
                    for link in links:
                        href = link.get_attribute("href")
                        if href and href.startswith("http") and site in href:
                            if href not in hrefs:
                                hrefs.append(href)
                        if len(hrefs) >= limit: break
                if hrefs: break

            if not hrefs:
                print(f"[INFO] No results found for {site} in this pass.")
                return []

            print(f"[INFO] Found {len(hrefs)} candidate links for {site}")

            for href in hrefs:
                article = self._scrape_article(context, href, site)
                if article:
                    articles.append(article)
                    print(f"[OK] Scraped: {article.title[:50]}...")
                else:
                    print(f"[SKIP] Failed to extract content from {href}")

            return articles

        except Exception as e:
            print(f"[ERROR] Error searching {site}: {e}")
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
                title = (
                    page.locator("meta[property='og:title']").get_attribute("content")
                    or ""
                )

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
                body=" ".join(body_text.split()),
            )

        except Exception as e:
            return None
        finally:
            page.close()

    def _expand_article_if_needed(self, page, site: str):
        try:
            if "sandesh.com" in site:
                btn = page.locator("#postId button, #postId button span").filter(
                    has_text="View"
                )
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(800)
            elif "aajtak.in" in site:
                btn = page.locator("div.read-more-content button")
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(800)
            elif "news18.com" in site:
                btn = page.locator(
                    "span[id^='readmore_story'], span[class*='readmore'], span:has-text('Read More')"
                )
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(800)
        except Exception:
            pass

    def _extract_body(self, page, url: str, site: str) -> str:
        # 1. Try site-specific selectors first
        selectors = {
            "sandesh.com": "div[class^='story article-']",
            "gujaratsamachar.com": "div.article-inner-detail.card-body",
            "tv9gujarati.com": "div.detailBody",
            "aninews.in": "article",
            "aajtak.in": "div.content-area",
            "news18.com": "article[id^='story-'], div.article-content",
            "indianexpress.com": "div.story-details, div.full-details",
            "hindustantimes.com": "div.storyDetail, div.detail",
            "thehindu.com": "div.article-block, div.content-body",
            "indiatoday.in": "div.description-section, div.story-right"
        }

        for k, v in selectors.items():
            if k in site:
                el = page.query_selector(v)
                if el:
                    txt = el.inner_text()
                    if len(txt) > 150: return txt

        # 2. Try common selectors for any site
        body = page.evaluate(
            """
            () => {
                const selectors = [
                    'article', '.article-content', '.article-body', '.story-details',
                    '.content', '.content-area', '.detailBody', '.news-description',
                    '.article-inner-detail', '.story', '#article-body', '.story_content',
                    '[itemprop="articleBody"]', '.post-content', '.entry-content',
                    '.story-full-width', '.article-payload', '.storyDetail'
                ];
                for (const sel of selectors) {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        if (el && el.innerText.length > 200) {
                             return el.innerText;
                        }
                    }
                }
                return '';
            }
        """
        ) or ""

        if not body:
            print(f"[WARN] No body extracted via selectors for {url}. Falling back to P tags.")
            p_tags = page.locator("p").all()
            body = " ".join([p.text_content() for p in p_tags if len(p.text_content() or "") > 40])

        return body
