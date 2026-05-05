import urllib.parse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from typing import List, Optional
from app.models.data import ScrapedArticle
import asyncio
import random
import time
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
        # Reduced to 1 to save RAM on the server (Prevents OOM errors)
        self.executor = ThreadPoolExecutor(max_workers=1)

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
        chrome_options = Options()
        # Auto-detect Linux (Server) vs Windows
        import os
        is_linux = os.name != 'nt'
        
        if is_linux:
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
        
        chrome_options.add_argument("--mute-audio")
        chrome_options.add_argument("--window-size=1280,800")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        try:
            for site in sites:
                try:
                    print(f"[SCRAPE] Starting work on: {site}")
                    articles = self._scrape_one_site(
                        driver, topic, site, limit_per_site
                    )
                    yield {"site": site, "articles": articles}
                    print(f"[SCRAPE] Completed work on: {site} (Found {len(articles)})")
                except Exception as e:
                    print(f"[WARN] Failed site {site}: {e}")
                    yield {"site": site, "articles": [], "error": str(e)}
        finally:
            driver.quit()
            print("[SCRAPE] All news sources processed.")

    def _scrape_one_site(
        self, driver, topic: str, site: str, limit: int
    ) -> List[ScrapedArticle]:
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
                driver.get(search_url)
                time.sleep(random.uniform(3, 5))
                ddg_ok = True
            except Exception as ddg_err:
                print(f"[WARN] DDG network error for {site}: {type(ddg_err).__name__}. Skipping to Google...")

            if ddg_ok:
                page_source = driver.page_source
                if "Robot Check" in page_source or "Security Check" in page_source:
                    print(f"[WARN] DuckDuckGo blocked us for {site}. Trying Google fallback...")
                    ddg_ok = False
                else:
                    if limit > 6:
                        for _ in range(2): 
                            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)
                            time.sleep(1.5)
                            try:
                                more_btn = driver.find_element(By.CSS_SELECTOR, "button#more-results, button.more-results")
                                if more_btn.is_displayed():
                                    more_btn.click()
                                    time.sleep(2)
                            except: pass

            def extract_hrefs(d_obj):
                res = []
                s_list = [
                    "article h2 a", "[data-testid='result-title-a']", "a.result__a", "a.result-link", 
                    "h3 a", ".g a", "#search a", ".yuRUbf a", "a h3", ".content a"
                ]
                for s in s_list:
                    try:
                        found = d_obj.find_elements(By.CSS_SELECTOR, s)
                        for el in found:
                            h = el.get_attribute("href")
                            if h and h.startswith("http") and (site in h or site.replace("www.","") in h):
                                if any(x in h.lower() for x in ["/category/", "/section/", "/topic/"]) and h.lower().count('/') < 5:
                                    continue
                                if any(h.lower().endswith(x) for x in [".com", ".com/", ".in", ".in/"]):
                                    continue
                                if "duckduckgo" not in h and "google" not in h:
                                    if h not in res: res.append(h)
                            if len(res) >= limit: return res
                    except: continue

                js_links = d_obj.execute_script("""
                    return Array.from(document.querySelectorAll('a'))
                        .filter(a => a.href && a.href.startsWith('http'))
                        .map(a => a.href)
                """)
                for h in js_links:
                    if site in h and "google" not in h and "duckduckgo" not in h:
                        if h not in res: res.append(h)
                    if len(res) >= limit: break
                return res

            hrefs = extract_hrefs(driver) if ddg_ok else []

            if not hrefs:
                print(f"[INFO] DDG had no results for {site}, trying Google fallback...")
                try:
                    google_url = f"https://www.google.com/search?q={encoded_query}&num=20"
                    driver.get(google_url)
                    time.sleep(random.uniform(4, 6))
                    hrefs = extract_hrefs(driver)
                except Exception as g_err:
                    print(f"[WARN] Google fallback also failed for {site}: {g_err}")

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
                    driver.get(direct_url)
                    time.sleep(3)
                    hrefs = extract_hrefs(driver)

            if not hrefs:
                driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(2)
                hrefs = extract_hrefs(driver)

            if not hrefs:
                try:
                    all_links = driver.find_elements(By.TAG_NAME, "a")
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
                article = self._scrape_article(driver, href, site)
                if article:
                    articles.append(article)
                    print(f"[OK] Scraped: {article.title[:50]}...")
                else:
                    print(f"[SKIP] Failed to extract content from {href}")

            return articles

        except Exception as e:
            print(f"[ERROR] Error searching {site}: {e}")
            return []

    def _scrape_article(self, driver, url: str, site: str) -> Optional[ScrapedArticle]:
        try:
            driver.get(url)
            time.sleep(1)

            self._expand_article_if_needed(driver, site)

            # Get Title
            title = ""
            try:
                h1 = driver.find_element(By.TAG_NAME, "h1")
                title = h1.text or ""
            except NoSuchElementException:
                try:
                    og_title = driver.find_element(By.CSS_SELECTOR, "meta[property='og:title']")
                    title = og_title.get_attribute("content") or ""
                except NoSuchElementException:
                    pass

            if not title.strip():
                return None

            # Get Body
            body_text = self._extract_body(driver, url, site)
            if not body_text or len(body_text) < 80:
                return None

            # Get Main Article Image
            image_url = self._extract_image(driver, site)

            return ScrapedArticle(
                source=site,
                url=url,
                title=title.strip(),
                body=" ".join(body_text.split()),
                image_url=image_url,
            )
        except Exception:
            return None

    def _expand_article_if_needed(self, driver, site: str):
        try:
            if "sandesh.com" in site:
                try:
                    btns = driver.find_elements(By.CSS_SELECTOR, "#postId button, #postId button span")
                    for btn in btns:
                        if "View" in btn.text:
                            btn.click()
                            time.sleep(0.8)
                            break
                except: pass
            elif "aajtak.in" in site:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, "div.read-more-content button")
                    btn.click()
                    time.sleep(0.8)
                except: pass
            elif "news18.com" in site:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, "span[id^='readmore_story'], span[class*='readmore'], span:has-text('Read More')")
                    btn.click()
                    time.sleep(0.8)
                except: pass
            elif "divyabhaskar.co.in" in site:
                try:
                    # Divya Bhaskar sometimes has a 'Read More' but it's rare on web
                    # We try to find any button that might expand content
                    btns = driver.find_elements(By.CSS_SELECTOR, "button, a.read-more")
                    for btn in btns:
                        if "વધારે વાંચો" in btn.text or "Read More" in btn.text:
                            btn.click()
                            time.sleep(0.8)
                            break
                except: pass
        except Exception:
            pass

    def _extract_body(self, driver, url: str, site: str) -> str:
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
            "zee24kalak.in": ".story-right-section",
            "divyabhaskar.co.in": "div.art-con, div.story-details, article, div[class*='article-body']"
        }

        for k, v in selectors.items():
            if k in site:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, v)
                    txt = el.text
                    if len(txt) > 80: return txt
                except: continue

        body = driver.execute_script("""
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
        """) or ""

        if not body or "Copyright ©" in body[:100] and len(body) < 200:
            p_tags = driver.find_elements(By.TAG_NAME, "p")
            body = " ".join([p.text for p in p_tags if len(p.text) > 40 and "Copyright" not in p.text and "DNPA" not in p.text])

        return body

    def _extract_image(self, driver, site: str) -> Optional[str]:
        try:
            try:
                driver.execute_script("""
                    const buttons = Array.from(document.querySelectorAll('button, a')).filter(el => /accept|agree|close|dismiss|ok/i.test(el.innerText));
                    if(buttons.length > 0) buttons[0].click();
                """)
                time.sleep(0.5)
            except: pass

            time.sleep(1)
            
            src = driver.execute_script("""
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
            """)
            if src: return src

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
                        src = driver.execute_script(f"const img = document.querySelector('{sel}'); return img ? (img.src || img.getAttribute('data-src')) : null;")
                        if src and src.startswith("http"): return src

            src = driver.execute_script("""
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
            """)
            if src: return src

            src = driver.execute_script("""
                const imgs = Array.from(document.querySelectorAll('img'));
                for (const img of imgs) {
                    const rect = img.getBoundingClientRect();
                    const s = img.src || img.getAttribute('data-src') || '';
                    if (rect.top < window.innerHeight * 0.4 && rect.width > 200 && s.startsWith('http')) {
                        return s;
                    }
                }
                return null;
            """)
            return src

        except Exception:
            return None
