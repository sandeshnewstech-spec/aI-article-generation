import urllib.parse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from typing import List, Optional
from app.models.data import ScrapedArticle
import asyncio
import random
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
        "vtvgujarati.com",
        "zee24kalak.in",
        "iamgujarat.com",
        "gujarati.abplive.com"
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

    async def scrape_topic_stream(
        self,
        topic: str,
        limit_per_site: int = 3,
        allowed_sites: Optional[List[str]] = None,
    ):
        """Streaming async wrapper that returns results as they are found via a thread-safe queue."""
        import queue
        q = queue.Queue()
        sites = allowed_sites if allowed_sites else self.SITES
        
        def runner():
            try:
                for chunk in self._scrape_sites_generator(topic, limit_per_site, sites):
                    q.put(chunk)
            except Exception as e:
                print(f"[ERROR] Stream burner failed: {e}")
            finally:
                q.put(None) # Sentinel

        loop = asyncio.get_event_loop()
        loop.run_in_executor(self.executor, runner)

        while True:
            # Get next result from queue (must use executor to avoid blocking main loop)
            result = await loop.run_in_executor(None, q.get)
            if result is None:
                break
            yield result

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
            # Use headless=False on Windows to bypass search engine blocks MUCH more reliably
            browser = p.chromium.launch(
                headless=False, 
                args=['--mute-audio', '--window-position=0,0']
            ) 
            context = browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            )

            for site in sites:
                try:
                    print(f"[SCRAPE] Starting work on: {site}")
                    articles = self._scrape_one_site(
                        context, topic, site, limit_per_site
                    )
                    yield {"site": site, "articles": articles}
                    print(f"[SCRAPE] Completed work on: {site} (Found {len(articles)})")
                except Exception as e:
                    print(f"[WARN] Failed site {site}: {e}")
                    yield {"site": site, "articles": [], "error": str(e)}

            browser.close()
            print("[SCRAPE] All news sources processed.")

    def _scrape_one_site(
        self, context, topic: str, site: str, limit: int
    ) -> List[ScrapedArticle]:
        page = context.new_page()
        articles = []

        try:
            # BROADEN QUERY: Remove dates or 'Today's' for better result volume
            clean_topic = topic.replace("Today's ", "").replace("Today ", "")
            query = f"{clean_topic} site:{site}"
            encoded_query = urllib.parse.quote(query)
            
            # --- ATTEMPT 1: DuckDuckGo ---
            search_url = f"https://duckduckgo.com/?q={encoded_query}&ia=news"
            print(f"[SCRAPE] Searching {site} via DDG: {search_url}")
            
            ddg_ok = False
            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(random.randint(3000, 5000))
                ddg_ok = True
            except Exception as ddg_err:
                print(f"[WARN] DDG network error for {site}: {type(ddg_err).__name__}. Skipping to Google...")

            if ddg_ok:
                # Detect DDG bot block
                if "Robot Check" in page.content() or "Security Check" in page.content():
                    print(f"[WARN] DuckDuckGo blocked us for {site}. Trying Google fallback...")
                    ddg_ok = False
                else:
                    # SCROLL TO LOAD MORE IF NEEDED (For higher limits)
                    if limit > 6:
                        for _ in range(2): 
                            page.keyboard.press("End")
                            page.wait_for_timeout(1500)
                            more_btn = page.locator("button#more-results, button.more-results").first
                            if more_btn.count() > 0 and more_btn.is_visible():
                                try: more_btn.click(timeout=3000); page.wait_for_timeout(2000)
                                except: pass

            # --- ATTEMPT 2: Google Fallback if DDG failed or found no links ---
            def extract_hrefs(page_obj):
                res = []
                # Target 'a' tags specifically to ensure we get hrefs
                s_list = [
                    "article h2 a", "[data-testid='result-title-a']", "a.result__a", "a.result-link", 
                    "h3 a", ".g a", "#search a", ".yuRUbf a", "a h3", ".content a"
                ]
                for s in s_list:
                    try:
                        found = page_obj.locator(s).all()
                        for el in found:
                            h = el.get_attribute("href")
                            if h and h.startswith("http") and (site in h or site.replace("www.","") in h):
                                if any(x in h.lower() for x in ["/category/", "/section/", "/topic/"]) and h.lower().count('/') < 5:
                                    continue # Skip likely section pages
                                if any(h.lower().endswith(x) for x in [".com", ".com/", ".in", ".in/"]):
                                    continue # Skip homepage
                                if "duckduckgo" not in h and "google" not in h:
                                    if h not in res: res.append(h)
                            if len(res) >= limit: return res
                    except: continue

                # JS Collector (More reliable for Google)
                js_links = page_obj.evaluate("""
                    () => Array.from(document.querySelectorAll('a'))
                        .filter(a => a.href && a.href.startsWith('http'))
                        .map(a => a.href)
                """)
                for h in js_links:
                    if site in h and "google" not in h and "duckduckgo" not in h:
                        if h not in res: res.append(h)
                    if len(res) >= limit: break
                return res

            hrefs = extract_hrefs(page) if ddg_ok else []

            if not hrefs:
                print(f"[INFO] DDG had no results for {site}, trying Google fallback...")
                try:
                    google_url = f"https://www.google.com/search?q={encoded_query}&num=20"
                    page.goto(google_url, wait_until="domcontentloaded", timeout=25000)
                    page.wait_for_timeout(random.randint(4000, 6000))
                    hrefs = extract_hrefs(page)
                except Exception as g_err:
                    print(f"[WARN] Google fallback also failed for {site}: {g_err}")

            # --- ATTEMPT 3: Direct Site Fallback (Specific for Categories) ---
            if not hrefs and any(c in topic.lower() for c in ["international", "business", "sports", "gujarat", "national"]):
                cat_map = {
                    "international": "/international-news",
                    "business": "/business",
                    "sports": "/sports",
                    "gujarat": "/gujarat",
                    "national": "/national-news"
                }
                suffix = ""
                for k, v in cat_map.items():
                    if k in topic.lower(): suffix = v; break
                
                if suffix:
                    direct_url = f"https://{site}{suffix}"
                    print(f"[INFO] No search results, trying direct visit: {direct_url}")
                    page.goto(direct_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(3000)
                    hrefs = extract_hrefs(page)

            # If no links, try scrolling a bit and waiting (ajax results)
            if not hrefs:
                page.mouse.wheel(0, 500)
                page.wait_for_timeout(2000)
                hrefs = extract_hrefs(page)

            if not hrefs:
                # Last resort: Any link that looks like it belongs to the site
                try:
                    all_links = page.locator("a").all()
                    for link in all_links:
                        href = link.get_attribute("href")
                        if href and site in href and len(href) > len(search_url) + 10:
                            if href not in hrefs: hrefs.append(href)
                        if len(hrefs) >= limit: break
                except: pass

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
            if not body_text or len(body_text) < 80:
                return None

            # Get Main Article Image (og:image → twitter:image → first large img)
            image_url = self._extract_image(page, site)

            return ScrapedArticle(
                source=site,
                url=url,
                title=title.strip(),
                body=" ".join(body_text.split()),
                image_url=image_url,
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
            "vtvgujarati.com": ".post-content, #postId",
            "abplive.com": ".article-story, .story-full-width",
            "iamgujarat.com": ".article-payload",
            "zee24kalak.in": ".story-right-section"
        }

        for k, v in selectors.items():
            if k in site:
                el = page.query_selector(v)
                if el:
                    txt = el.inner_text()
                    if len(txt) > 80: return txt

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

    def _extract_image(self, page, site: str) -> Optional[str]:
        """Extract the main article image URL with ultra-resilient, multi-stage fallback."""
        try:
            # Dismiss typical cookie barriers
            try:
                page.evaluate("""() => { 
                    const buttons = Array.from(document.querySelectorAll('button, a')).filter(el => /accept|agree|close|dismiss|ok/i.test(el.innerText));
                    if(buttons.length > 0) buttons[0].click();
                }""")
                page.wait_for_timeout(500)
            except: pass

            # Wait for any image to load (lazy loading)
            page.wait_for_timeout(1000)
            
            # 1. Meta-scanners (Highest reliability across standardized News sites)
            src = page.evaluate("""
                () => {
                    const selectors = [
                        'meta[property="og:image"]', 
                        'meta[name="twitter:image"]',
                        'meta[property="twitter:image"]',
                        'meta[name="thumbnail"]',
                        'link[rel="image_src"]'
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        const val = el ? (el.content || el.href) : null;
                        if (val && val.startsWith('http')) return val;
                    }
                    return null;
                }
            """)
            if src:
                print(f"[IMAGE-SCRAPE] Meta/Tag image found: {src[:60]}...")
                return src

            # 2. Channel-Specific High-Resolution Selectors
            # Targeted at the most common Indian news channels
            site_patterns = {
                "sandesh.com":         [".article-image img", ".post-thumb img", ".story-main-image img"],
                "tv9gujarati.com":     [".detailBody img", ".news-detail-img img", "figure.news-detail-img img"],
                "vtvgujarati.com":     [".post-thumbnail img", ".post-content img", ".post-img img"],
                "gujaratsamachar.com": [".post-thumbnail img", ".card-body img", ".article-inner-detail img"],
                "abplive.com":         [".article-img img", ".story-content img"],
                "indianexpress.com":   [".story-image img", ".article-header img", "article figure img"],
                "indiatoday.in":       [".main-story-image img", ".story-details img"],
                "indiatimes.com":      [".main-img img", ".article-image img", ".story-image img", ".content-img img"],
                "ndtv.com":            [".ins_storyfull_withimg img", ".sp-cn img", ".fullstory img"],
                "news18.com":          [".article-header-image img", ".jsx-story img", ".cover-img img"],
                "jagran.com":          [".article-full-image img", ".story-img img"],
                "republicbharat.com":  [".main-content img", ".article-img img"],
                "iamgujarat.com":      [".article-payload img", ".main-image img"],
                "zee24kalak.in":       [".story-right-section img", ".post-thumbnail img"]
            }
            
            for channel, selectors in site_patterns.items():
                if channel in site:
                    for sel in selectors:
                        src = page.evaluate(f"() => {{ const img = document.querySelector('{sel}'); return img ? (img.src || img.getAttribute('data-src')) : null; }}")
                        if src and src.startswith("http"):
                            print(f"[IMAGE-SCRAPE] Channel-specific success for {channel}")
                            return src

            # 3. Geometric Content Scan (Aggressive fallback)
            # Find the largest image in the main content area
            src = page.evaluate("""
                () => {
                    const containers = ['article', 'main', '.article-content', '.story-details', '.detailBody', '.post-content', '.content-area', '.story-payload'];
                    let bestImg = null;
                    let maxArea = 0;

                    for (const sel of containers) {
                        const container = document.querySelector(sel);
                        if (!container) continue;
                        
                        const imgs = Array.from(container.querySelectorAll('img'));
                        for (const img of imgs) {
                            const src = img.src || img.getAttribute('data-src') || '';
                            if (!src.startsWith('http')) continue;
                            if (!src.includes('.jpg') && !src.includes('.jpeg') && !src.includes('.png') && !src.includes('.webp')) continue;

                            const area = (img.naturalWidth || img.width || 0) * (img.naturalHeight || img.height || 0);
                            if (area > maxArea) {
                                maxArea = area;
                                bestImg = src;
                            }
                        }
                    }
                    return bestImg;
                }
            """)
            if src:
                print(f"[IMAGE-SCRAPE] Geometric scan found content image")
                return src

            # 4. Final Fail-Safe: Top Image
            # If nothing else works, pick the first image in the top 40% of the page
            src = page.evaluate("""
                () => {
                    const imgs = Array.from(document.querySelectorAll('img'));
                    for (const img of imgs) {
                        const rect = img.getBoundingClientRect();
                        const s = img.src || img.getAttribute('data-src') || '';
                        if (rect.top < window.innerHeight * 0.4 && rect.width > 200 && s.startsWith('http')) {
                            return s;
                        }
                    }
                    return null;
                }
            """)
            if src:
                print(f"[IMAGE-SCRAPE] Top-page fail-safe image found")
                return src

        except Exception as e:
            print(f"[IMAGE-SCRAPE] Universal error: {e}")

        return None
