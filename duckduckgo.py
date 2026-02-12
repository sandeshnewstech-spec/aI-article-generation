import asyncio
import json
import urllib.parse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


SITES = [
    "gujaratsamachar.com",
    "aninews.in",
    "aajtak.in",
    "news18.com",
    "tv9gujarati.com",
    "sandesh.com",
]


# ==============================
# MAIN CONTROLLER
# ==============================
async def scrape_topic_articles(topic: str, debug=False):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            )
        )

        results = []
        opened_urls = []

        for site in SITES:
            print(f"\n🔍 Searching site: {site}")
            article, urls = await scrape_one_site(context, topic, site)
            opened_urls.extend(urls)

            if article:
                results.append(article)
                print(f"✅ Added article from {site}")
            else:
                print(f"❌ No valid article from {site}")

        await browser.close()

        if debug:
            return {
                "articles": results,
                "debug_opened_urls": opened_urls,
            }
        else:
            return results


# ==============================
# SEARCH ONE SITE
# ==============================
async def scrape_one_site(context, topic: str, site: str, limit: int = 3):
    page = await context.new_page()
    opened_urls = []

    try:
        query = f"{topic} site:{site}"
        await page.goto("https://duckduckgo.com/html/", wait_until="domcontentloaded")
        await page.fill("input[name='q']", query)
        await page.press("input[name='q']", "Enter")
        await page.wait_for_timeout(2000)

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
            opened_urls.append(href)
            article = await scrape_article(context, href, site)
            if article:
                return article, opened_urls

        return None, opened_urls

    finally:
        await page.close()


# ==============================
# CLICK "READ MORE / VIEW MORE"
# ==============================
async def expand_article_if_needed(page, site: str):
    try:
        if "sandesh.com" in site:
            btn = page.locator(
                "#postId button, #postId button span"
            ).filter(has_text="View")
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(800)

        elif "aajtak.in" in site:
            btn = page.locator(
                "div.read-more-content button"
            )
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(800)

        elif "news18.com" in site:
            btn = page.locator(
                "span[id^='readmore_story'], "
                "span[class*='readmore'], "
                "span:has-text('Read More')"
            )
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(800)

    except Exception:
        pass


# ==============================
# SITE-AWARE ARTICLE SCRAPER
# ==============================
async def scrape_article(context, url: str, site: str):
    page = await context.new_page()

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1200)

        # expand full article if button exists
        await expand_article_if_needed(page, site)

        # ---------- TITLE ----------
        title = ""
        if await page.locator("h1").count() > 0:
            title = await page.locator("h1").first.text_content() or ""
        elif await page.locator("meta[property='og:title']").count() > 0:
            title = await page.locator(
                "meta[property='og:title']"
            ).get_attribute("content") or ""

        if not title.strip():
            return None

        body_text = ""

        # =========================================================
        # URL ends with .html
        # =========================================================
        if url.lower().endswith(".html"):
            body_text = await page.evaluate("""
                () => {
                    const selectors = [
                        'article',
                        '.article-content',
                        '.article-body',
                        '.story-details',
                        '.content',
                        '.content-area',
                        '.detailBody',
                        '.news-description',
                        '.article-inner-detail',
                        '.story'
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

        else:
            if "sandesh.com" in site:
                el = await page.query_selector("div[class^='story article-']")
                if not el:
                    return None
                body_text = await el.inner_text()

            elif "gujaratsamachar.com" in site:
                el = await page.query_selector("div.article-inner-detail.card-body")
                if not el:
                    return None
                body_text = await el.inner_text()

            elif "tv9gujarati.com" in site:
                el = await page.query_selector("div.detailBody")
                if not el:
                    return None
                body_text = await el.inner_text()

            elif "aninews.in" in site:
                el = await page.query_selector("article")
                if not el:
                    return None
                body_text = await el.inner_text()

            elif "aajtak.in" in site:
                el = await page.query_selector("div.content-area")
                if not el:
                    return None
                body_text = await el.inner_text()

            elif "news18.com" in site:
                el = await page.query_selector("article[id^='story-']")
                if not el:
                    return None
                body_text = await el.inner_text()

        body = " ".join(body_text.split())

        if len(body) < 100:
            return None

        return {
            "url": url,
            "title": title.strip(),
            "body": body,
        }

    except PlaywrightTimeout:
        return None
    except Exception:
        return None
    finally:
        await page.close()


# ==============================
# ENTRY POINT
# ==============================
if __name__ == "__main__":
    data = asyncio.run(
        scrape_topic_articles("india national cricket team")
    )

    print("\n📄 FINAL OUTPUT:")
    print(json.dumps(data, indent=2, ensure_ascii=False))
