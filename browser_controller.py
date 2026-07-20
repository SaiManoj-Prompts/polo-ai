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

# Title keywords that indicate a page is irrelevant to research
IRRELEVANT_TITLE_WORDS = [
    "newsletter", "subscribe", "captcha", "sign up", "email",
    "bot protection", "verification", "cloudflare", "access denied",
    "403 forbidden", "404 not found", "cookie policy",
]

# Common stop words to ignore when extracting query keywords
STOP_WORDS = {
    "the", "is", "a", "an", "of", "in", "for", "and", "to", "with",
    "on", "at", "by", "from", "or", "as", "it", "be", "are", "was",
    "were", "been", "has", "have", "had", "do", "does", "did", "but",
    "not", "so", "if", "its", "my", "that", "this", "what", "which",
    "who", "how", "when", "where", "why", "can", "will", "should",
    "would", "could", "most", "more", "very", "just", "about",
}


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


def _extract_query_keywords(query: str) -> set:
    """Extract meaningful keywords from the user's query, ignoring stop words."""
    words = re.findall(r"[a-zA-Z0-9]+", query.lower())
    return {w for w in words if w not in STOP_WORDS and len(w) > 1}


def _is_title_relevant(title: str, query_keywords: set) -> bool:
    """Check if a page title is relevant to the query and not junk."""
    title_lower = title.lower()

    # Reject if title matches any irrelevant pattern
    for word in IRRELEVANT_TITLE_WORDS:
        if word in title_lower:
            return False

    # Require at least 1 keyword overlap with the query
    title_words = set(re.findall(r"[a-zA-Z0-9]+", title_lower))
    overlap = title_words & query_keywords
    return len(overlap) >= 1


def _is_noisy_text(text: str) -> bool:
    """Check if the text contains common navigation/cookie banner noise."""
    lower_text = text.lower()
    noise_phrases = [
        "skip to content", "select theme", "ctrl k", "dark light auto",
        "select language", "cookie", "accept all", "manage preferences",
        "sign in", "log in", "subscribe", "about us", "privacy policy",
        "all rights reserved", "terms of use", "terms of service",
        "javascript is disabled", "please enable javascript",
        "categories", "archives"
    ]
    for phrase in noise_phrases:
        if phrase in lower_text:
            return True
    return False


def _extract_text_snippet(page, max_length: int = SNIPPET_LENGTH) -> str:
    """Extract clean body paragraphs from a page, stripping navigation noise."""
    try:
        paragraphs = page.locator("p").all_inner_texts()
        valid_paragraphs = []
        
        for p in paragraphs:
            cleaned = re.sub(r"\s+", " ", p).strip()
            # Require at least 60 characters for a substantive paragraph
            if len(cleaned) < 60:
                continue
            if _is_noisy_text(cleaned):
                continue
            valid_paragraphs.append(cleaned)
            
        if not valid_paragraphs:
            return ""
            
        # The longest paragraph is almost always the main article content,
        # avoiding concatenated lists of links or headers.
        best_paragraph = max(valid_paragraphs, key=len)
        raw_text = best_paragraph
            
        # Truncate to max length
        if len(raw_text) > max_length:
            return raw_text[:max_length] + "…"
        return raw_text
    except Exception:
        return ""


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


def _extract_search_links(page) -> list[tuple[str, str]]:
    """Extract search result URLs and their link text from a Mojeek results page.

    Returns:
        A list of (url, link_text) tuples.
    """
    links = []
    seen = set()
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
                link_text = (el.inner_text() or "").strip()
                if href and href.startswith("http") and _is_safe_url(href):
                    normalized = href.rstrip('/')
                    if normalized not in seen:
                        seen.add(normalized)
                        links.append((href, link_text))
                if len(links) >= 15:
                    break
            if links:
                break

        # Fallback: grab any result-like links if specific selectors fail
        if not links:
            all_anchors = page.query_selector_all("a[href^='http']")
            for el in all_anchors:
                href = el.get_attribute("href")
                link_text = (el.inner_text() or "").strip()
                if (
                    href
                    and "mojeek.com" not in href
                    and _is_safe_url(href)
                ):
                    normalized = href.rstrip('/')
                    if normalized not in seen:
                        seen.add(normalized)
                        links.append((href, link_text))
                    if len(links) >= 15:
                        break

    except Exception:
        pass

    return links[:15]


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
            + "&lb=en&fmt=10"
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

        # ── Step 2: Extract result links and rank by relevance ────────
        raw_results = _extract_search_links(page)

        if not raw_results:
            browser.close()
            return [{"title": "No results found", "url": search_url,
                      "snippet": "Mojeek returned no usable results for this query."}]

        # Extract keywords from the query for relevance scoring
        query_keywords = _extract_query_keywords(query)

        # Pre-filter: remove results whose link text is clearly irrelevant
        filtered_results = [
            (url, text) for url, text in raw_results
            if _is_title_relevant(text, query_keywords)
        ]

        # Rank remaining results by keyword overlap (descending)
        def _relevance_score(item):
            _, text = item
            text_words = set(re.findall(r"[a-zA-Z0-9]+", text.lower()))
            return len(text_words & query_keywords)

        filtered_results.sort(key=_relevance_score, reverse=True)

        # Take the top 10 candidates to visit
        candidates = filtered_results[:10]

        # ── Step 3: Visit each result page ───────────────────────────
        for url, _link_text in candidates:
            if len(findings) >= max_pages:
                break

            try:
                page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")

                # Block forms on this page
                _block_forms_and_submissions(page)

                # Collect data
                title = page.title() or "(No title)"

                # Double-check the actual page title for relevance
                if not _is_title_relevant(title, query_keywords):
                    continue

                snippet = _extract_text_snippet(page)

                # Skip if no useful content found
                if not snippet:
                    continue

                findings.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                })

            except PlaywrightTimeout:
                continue  # Skip timed-out pages silently
            except Exception:
                # Silently skip pages that fail to load
                continue

        browser.close()

    # If fewer than 2 relevant results, return an insufficient-sources message
    if len(findings) < 2:
        return [{
            "title": "Insufficient results",
            "url": "",
            "snippet": "Insufficient relevant sources found for this query."
        }]

    return findings
