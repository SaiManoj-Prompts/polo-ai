"""
browser_controller.py — Safe read-only browser research for Polo AI.

Uses Playwright (Chromium only) to:
1. Search DuckDuckGo for the user's query
2. Visit up to 5 result pages
3. Collect each page's title, URL, and a text snippet

Safety rules enforced:
- Headless only (no visible browser window)
- 30-second timeout per page
- No forms, logins, downloads, uploads, or payments
- No CAPTCHA bypassing or paywall circumvention
- No persistent cookies or cache
- Max 5 pages per research session
"""

import re
import urllib.parse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ── Safety constants ─────────────────────────────────────────────────────
MAX_PAGES = 5
PAGE_TIMEOUT_MS = 30_000  # 30 seconds
SNIPPET_LENGTH = 500      # max characters per page snippet

# URL patterns to skip (logins, auth, payments, etc.)
BLOCKED_URL_PATTERNS = [
    "login", "signin", "sign-in", "signup", "sign-up",
    "auth", "oauth", "account", "checkout", "payment",
    "pay.", "billing", "subscribe",
]

# File extensions to skip (downloads, media, etc.)
BLOCKED_EXTENSIONS = [
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".tar", ".gz", ".exe", ".dmg", ".msi",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
]


def _is_safe_url(url: str) -> bool:
    """Check if a URL is safe to visit (no logins, payments, downloads)."""
    url_lower = url.lower()

    # Block unsafe URL patterns
    for pattern in BLOCKED_URL_PATTERNS:
        if pattern in url_lower:
            return False

    # Block file downloads
    for ext in BLOCKED_EXTENSIONS:
        if url_lower.endswith(ext):
            return False

    return True


def _extract_text_snippet(page, max_length: int = SNIPPET_LENGTH) -> str:
    """Extract the first visible text from a page, cleaned up."""
    try:
        # Get text from the body, stripping extra whitespace
        raw_text = page.inner_text("body", timeout=5000)
        # Clean up: collapse whitespace and newlines
        cleaned = re.sub(r"\s+", " ", raw_text).strip()
        # Truncate to max length
        if len(cleaned) > max_length:
            return cleaned[:max_length] + "…"
        return cleaned
    except Exception:
        return "(Could not extract text from this page.)"


def _block_forms_and_submissions(page):
    """Inject JavaScript to disable all form submissions on a page."""
    try:
        page.evaluate("""
            document.querySelectorAll('form').forEach(form => {
                form.addEventListener('submit', e => e.preventDefault(), true);
            });
        """)
    except Exception:
        pass  # Page might not support JS injection; that's okay


def _extract_search_links(page) -> list[str]:
    """Extract search result URLs from a Mojeek HTML results page."""
    links = []
    try:
        # Mojeek results typically use <a> with class "ob" or "title" inside results list
        selectors = [
            "ul.results-standard li h2 a.title",
            "a.ob",
        ]

        for selector in selectors:
            elements = page.query_selector_all(selector)
            for el in elements:
                href = el.get_attribute("href")
                if href and href.startswith("http") and _is_safe_url(href):
                    # Avoid duplicate URLs
                    if href not in links:
                        links.append(href)
                if len(links) >= MAX_PAGES:
                    break
            if links:
                break

        # Fallback: grab any result-like links if specific selectors fail
        if not links:
            all_anchors = page.query_selector_all("a[href^='http']")
            for el in all_anchors:
                href = el.get_attribute("href")
                if (
                    href
                    and "mojeek.com" not in href
                    and _is_safe_url(href)
                ):
                    if href not in links:
                        links.append(href)
                    if len(links) >= MAX_PAGES:
                        break

    except Exception:
        pass

    return links[:MAX_PAGES]


def search_and_collect(query: str, max_pages: int = MAX_PAGES) -> list[dict]:
    """
    Search the web and collect findings.

    Args:
        query: The user's research question.
        max_pages: Maximum number of pages to visit (default 5).

    Returns:
        A list of dicts, each with keys: 'title', 'url', 'snippet'.
        Returns an empty list if search fails entirely.
    """
    max_pages = min(max_pages, MAX_PAGES)  # enforce hard cap
    findings = []

    with sync_playwright() as p:
        # Launch headless Chromium with safety flags
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-downloads",
                "--disable-popup-blocking",
                "--no-first-run",
                "--disable-extensions",
                "--disable-default-apps",
            ],
        )

        # Create a fresh context (no cookies, no cache, no stored data)
        context = browser.new_context(
            accept_downloads=False,
            java_script_enabled=True,
            ignore_https_errors=False,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        page = context.new_page()

        # ── Step 1: Search Mojeek ────────────────────────────────
        search_url = (
            "https://www.mojeek.com/search?q="
            + urllib.parse.quote_plus(query)
        )

        try:
            page.goto(search_url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
        except PlaywrightTimeout:
            browser.close()
            return [{"title": "Search timed out", "url": search_url,
                      "snippet": "Mojeek did not respond within 30 seconds."}]
        except Exception as e:
            browser.close()
            return [{"title": "Search failed", "url": search_url,
                      "snippet": f"Could not reach Mojeek: {str(e)[:200]}"}]

        # ── Step 2: Extract result links ─────────────────────────────
        result_urls = _extract_search_links(page)

        if not result_urls:
            browser.close()
            return [{"title": "No results found", "url": search_url,
                      "snippet": "Mojeek returned no usable results for this query."}]

        # ── Step 3: Visit each result page ───────────────────────────
        for url in result_urls[:max_pages]:
            try:
                page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")

                # Block forms on this page
                _block_forms_and_submissions(page)

                # Collect data
                title = page.title() or "(No title)"
                snippet = _extract_text_snippet(page)

                findings.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                })

            except PlaywrightTimeout:
                findings.append({
                    "title": "(Page timed out)",
                    "url": url,
                    "snippet": "This page took longer than 30 seconds to load and was skipped.",
                })
            except Exception:
                # Silently skip pages that fail to load
                continue

        browser.close()

    return findings
