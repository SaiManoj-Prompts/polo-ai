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
# Blocklists
IRRELEVANT_TITLE_WORDS = [
    "newsletter", "subscribe", "captcha", "sign up", "email",
    "bot protection", "verify", "login", "register",
    "riddle", "joke", "trivia", "puzzle", "brainteaser",
    "cloudflare", "access denied",
    "403 forbidden", "404 not found", "cookie policy",
]

IRRELEVANT_URL_PATTERNS = [
    "riddle", "joke", "trivia", "puzzle"
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


def _is_career_query(query_keywords: set) -> bool:
    """Check if the query is related to jobs, careers, or internships."""
    career_terms = {"internship", "internships", "job", "jobs", "hiring", "career", "position", "intern", "interns"}
    return bool(query_keywords & career_terms)


def _is_title_relevant(title: str, query_keywords: set) -> bool:
    """Check if a page title is relevant to the query and not junk."""
    title_lower = title.lower()

    # Reject if title matches any irrelevant pattern
    for word in IRRELEVANT_TITLE_WORDS:
        if word in title_lower:
            return False

    # Require at least 1 keyword overlap (or fuzzy match) with the query
    title_words = set(re.findall(r"[a-zA-Z0-9]+", title_lower))
    for qw in query_keywords:
        for tw in title_words:
            if qw == tw:
                return True
            # Prefix match for words >= 4 chars (e.g. agent vs agentic)
            if len(qw) >= 4 and len(tw) >= 4:
                if qw.startswith(tw) or tw.startswith(qw):
                    return True
    return False


    return False


def _is_snippet_relevant(snippet: str, query: str, query_keywords: set) -> bool:
    """Check if the extracted snippet is relevant to the query."""
    if not snippet:
        return False

    snippet_lower = snippet.lower()
    
    # 1. Count keyword overlap
    snippet_words = set(re.findall(r"[a-zA-Z0-9]+", snippet_lower))
    match_count = 0
    for qw in query_keywords:
        for tw in snippet_words:
            if qw == tw or (len(qw) >= 4 and len(tw) >= 4 and (qw.startswith(tw) or tw.startswith(qw))):
                match_count += 1
                break  # count each query keyword at most once
    
    comparison_keywords = {"compare", "best", "vs", "frameworks", "tools", "alternatives"}
    is_comparison = bool(query_keywords & comparison_keywords)
    
    # 2. Check keyword count threshold
    if is_comparison and match_count < 3:
        return False
    elif not is_comparison and match_count < 2:
        return False

    # 3. For comparison queries, require at least one named entity NOT in the query
    if is_comparison:
        # Find Capitalized words (e.g. AutoGPT)
        caps = re.findall(r'\b[A-Z][a-zA-Z0-9]*\b', snippet)
        # Find words at start of sentences
        starts = re.findall(r'(?:^|[.!?]\s+)([A-Z][a-zA-Z0-9]*)\b', snippet)
        
        # Proper nouns = caps minus sentence starters, excluding query keywords
        proper_nouns = {p for p in set(caps) - set(starts) if p.lower() not in query_keywords and len(p) > 2}
        
        # CamelCase / internal caps words, excluding query keywords
        camel_cases = {c for c in re.findall(r'\b[a-zA-Z]*[A-Z][a-z]+[A-Z][a-zA-Z]*\b', snippet) if c.lower() not in query_keywords}
        
        if not proper_nouns and not camel_cases:
            return False

    return True


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


def _visit_and_collect(page, url, query, query_keywords, findings, seen_urls):
    """Visit a URL, extract content, and append to findings if relevant.

    Returns True if a finding was added, False otherwise.
    """
    normalized = url.rstrip('/')
    if normalized in seen_urls:
        return False
        
    for pattern in IRRELEVANT_URL_PATTERNS:
        if pattern in normalized.lower():
            return False
            
    seen_urls.add(normalized)

    try:
        page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
        _block_forms_and_submissions(page)
        title = page.title() or "(No title)"
        if not _is_title_relevant(title, query_keywords):
            return False
        snippet = _extract_text_snippet(page)
        if not _is_snippet_relevant(snippet, query, query_keywords):
            return False
            
        findings.append({"title": title, "url": url, "snippet": snippet})
        return True
    except Exception:
        return False


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


# ── Fallback source helpers ──────────────────────────────────────────────

def _search_wikipedia(page, query, query_keywords, findings, seen_urls, max_to_add=2):
    """Search Wikipedia and add relevant article findings."""
    added = 0
    search_url = (
        "https://en.wikipedia.org/w/index.php?search="
        + urllib.parse.quote_plus(query)
    )

    try:
        page.goto(search_url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
    except Exception:
        return

    current_url = page.url

    # Case 1: Wikipedia redirected directly to an article
    if "/wiki/" in current_url and "index.php" not in current_url:
        normalized = current_url.rstrip('/')
        if normalized not in seen_urls:
            seen_urls.add(normalized)
            title = page.title() or "(No title)"
            if _is_title_relevant(title, query_keywords):
                snippet = _extract_text_snippet(page)
                if snippet:
                    findings.append({"title": title, "url": current_url, "snippet": snippet})
        return

    # Case 2: Wikipedia showed a search results page
    try:
        result_links = page.query_selector_all("div.mw-search-results-container a[href], div.mw-search-results a[href]")
        urls_to_visit = []
        for el in result_links:
            href = el.get_attribute("href") or ""
            # Skip special pages (Wikipedia:, Help:, Category:, etc.)
            page_name = href.split("/wiki/")[-1] if "/wiki/" in href else href
            if ":" in page_name and "Special:" not in page_name:
                continue
            if href.startswith("/wiki/") or href.startswith("/w/"):
                full_url = "https://en.wikipedia.org" + href
                if full_url not in urls_to_visit:
                    urls_to_visit.append(full_url)
            if len(urls_to_visit) >= 3:
                break

        for url in urls_to_visit:
            if added >= max_to_add:
                break
            if _visit_and_collect(page, url, query, query_keywords, findings, seen_urls):
                added += 1
    except Exception:
        pass


def _search_github(page, query, query_keywords, findings, seen_urls, max_to_add=2):
    """Search GitHub repositories and add relevant findings."""
    # GitHub navigation paths to skip
    github_nav = {
        "features", "enterprise", "pricing", "security", "topics",
        "trending", "collections", "events", "explore", "marketplace",
        "pulls", "issues", "codespaces", "settings", "notifications",
        "new", "organizations", "login", "join", "search", "about",
        "contact", "support", "customer-stories", "readme", "sponsors",
    }
    added = 0
    search_url = (
        "https://github.com/search?q="
        + urllib.parse.quote_plus(query)
        + "&type=repositories"
    )

    try:
        page.goto(search_url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)  # Brief wait for JS rendering
    except Exception:
        return

    try:
        all_links = page.query_selector_all("a[href]")
        repo_urls = []
        seen_repos = set()
        for el in all_links:
            href = el.get_attribute("href") or ""
            # Match /owner/repo pattern (exactly 2 path segments)
            stripped = href.strip("/")
            parts = stripped.split("/")
            if (
                href.startswith("/")
                and len(parts) == 2
                and all(p and not p.startswith(".") for p in parts)
                and parts[0].lower() not in github_nav
            ):
                full_url = "https://github.com/" + stripped
                if full_url not in seen_repos:
                    seen_repos.add(full_url)
                    repo_urls.append(full_url)
            if len(repo_urls) >= 3:
                break

        for url in repo_urls:
            if added >= max_to_add:
                break
            if _visit_and_collect(page, url, query, query_keywords, findings, seen_urls):
                added += 1
    except Exception:
        pass


def _search_indeed(page, query, findings, seen_urls, max_to_add=3):
    """Search Indeed for jobs/internships and add relevant findings."""
    added = 0
    search_url = (
        "https://www.indeed.com/jobs?q="
        + urllib.parse.quote_plus(query)
        + "&l=United+States"
    )

    try:
        page.goto(search_url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)  # Brief wait for JS rendering
    except Exception:
        return

    try:
        job_cards = page.query_selector_all("div.job_seen_beacon, td.resultContent")
        for card in job_cards:
            if added >= max_to_add:
                break
                
            title_el = card.query_selector("h2.jobTitle span[title], h2.jobTitle a")
            company_el = card.query_selector('span[data-testid="company-name"]')
            loc_el = card.query_selector('div[data-testid="text-location"]')
            snippet_els = card.query_selector_all("ul > li, div.jobMetaDataGroup")
            
            # Use Indeed link if we can find one, else just the search URL
            link_el = card.query_selector("h2.jobTitle a")
            href = link_el.get_attribute("href") if link_el else ""
            full_url = "https://www.indeed.com" + href if href.startswith("/") else (href if href else search_url)
            
            title = (title_el.inner_text() if title_el else "").strip()
            company = (company_el.inner_text() if company_el else "Unknown Company").strip()
            location = (loc_el.inner_text() if loc_el else "Unknown Location").strip()
            
            snippets = [el.inner_text().strip() for el in snippet_els if el.inner_text().strip()]
            snippet_text = " ".join(snippets)
            
            if title and snippet_text:
                normalized = full_url.rstrip('/')
                if normalized not in seen_urls:
                    seen_urls.add(normalized)
                    final_snippet = f"Company: {company} | Location: {location}\n{snippet_text}"
                    findings.append({"title": title, "url": full_url, "snippet": final_snippet})
                    added += 1
    except Exception:
        pass


def _search_usajobs(page, query, findings, seen_urls, max_to_add=3):
    """Search USAJobs.gov for federal jobs and add relevant findings."""
    added = 0
    search_url = (
        "https://www.usajobs.gov/Search/Results?k="
        + urllib.parse.quote_plus(query)
    )

    try:
        page.goto(search_url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
        try:
            # Wait for results to render since USAJobs is a single-page app
            page.wait_for_selector("div#search-results .page-section", timeout=5000)
        except Exception:
            pass
    except Exception:
        return

    try:
        job_cards = page.query_selector_all("div#search-results .page-section")
        for card in job_cards:
            if added >= max_to_add:
                break
                
            title_el = card.query_selector("a.no-underline")
            if not title_el:
                continue
                
            href = title_el.get_attribute("href")
            if not href or "/job/" not in href:
                continue
                
            agency_el = card.query_selector("strong")
            loc_el = card.query_selector("div.grid > div:nth-child(1) > div:nth-child(2)")
            snippet_el = card.query_selector("div.grid > div:nth-child(2)")
            
            full_url = "https://www.usajobs.gov" + href if href.startswith("/") else (href if href else search_url)
            
            title = (title_el.inner_text() if title_el else "").strip()
            agency = (agency_el.inner_text() if agency_el else "Unknown Agency").strip()
            location = (loc_el.inner_text() if loc_el else "Unknown Location").strip()
            snippet_text = (snippet_el.inner_text() if snippet_el else "").strip()
            if title and snippet_text:
                # RELEVANCE FILTER
                query_kws = _extract_query_keywords(query)
                ignore_kws = {"job", "jobs", "hiring", "career", "position", 
                              "government", "federal", "united", "states", "usa", "us"}
                target_kws = query_kws - ignore_kws
                
                if target_kws:
                    import re
                    combined_text = f"{title} {agency} {location} {snippet_text}".lower()
                    combined_words = set(re.findall(r"[a-z0-9]+", combined_text))
                    matched_kws = target_kws.intersection(combined_words)
                    
                    intern_terms = {"intern", "interns", "internship", "internships"}
                    is_intern_query = bool(target_kws.intersection(intern_terms))
                    if is_intern_query and combined_words.intersection(intern_terms):
                        matched_kws.add("internship") # ensure it counts as matched
                        
                    if not matched_kws:
                        continue  # No target keywords matched
                        
                    # Strict check: If user asked for intern/internship, the card MUST contain it
                    if is_intern_query and not combined_words.intersection(intern_terms):
                        continue
                        
                    generic_roles = {"analyst", "specialist", "manager", "engineer", "assistant", "technician", "officer", "clerk", "director"}
                    # Reject if it only matched a generic role word, but the user asked for a specific type
                    if all(kw in generic_roles for kw in matched_kws) and not all(kw in generic_roles for kw in target_kws):
                        continue
                        
                normalized = full_url.rstrip('/')
                if normalized not in seen_urls:
                    seen_urls.add(normalized)
                    final_snippet = f"Agency: {agency} | Location: {location}\n{snippet_text}"
                    findings.append({"title": title, "url": full_url, "snippet": final_snippet})
                    added += 1
    except Exception:
        pass


def _search_arxiv(page, query, query_keywords, findings, seen_urls, max_to_add=1):
    """Search arXiv papers and add relevant findings."""
    added = 0
    search_url = (
        "https://arxiv.org/search/?searchtype=all&query="
        + urllib.parse.quote_plus(query)
    )

    try:
        page.goto(search_url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
    except Exception:
        return

    try:
        # arXiv search results contain links to /abs/XXXX.XXXXX pages
        paper_links = page.query_selector_all("a[href*='/abs/']")
        abs_urls = []
        for el in paper_links:
            href = el.get_attribute("href") or ""
            if "/abs/" in href:
                full_url = href if href.startswith("http") else "https://arxiv.org" + href
                if full_url not in abs_urls:
                    abs_urls.append(full_url)
            if len(abs_urls) >= 2:
                break

        for url in abs_urls:
            if added >= max_to_add:
                break
            if _visit_and_collect(page, url, query, query_keywords, findings, seen_urls):
                added += 1
    except Exception:
        pass


# ── Main orchestrator ────────────────────────────────────────────────────

def search_and_collect(query: str, max_pages: int = MAX_PAGES, queries: list = None, category: str = None) -> list[dict]:
    """
    Search the web and collect findings using multiple sources.

    Strategy (waterfall):
        1. Mojeek  — primary search engine
        2. Wikipedia — if Mojeek returns < 2 relevant results
        3. GitHub   — if still < 2 relevant results
        4. arXiv    — if still < 2 relevant results

    Args:
        query: The user's research question.
        max_pages: Maximum number of pages to visit (default 5).
        queries: List of validated queries for bounded multi-query search.
        category: AI-derived category.

    Returns:
        A list of dicts, each with keys: 'title', 'url', 'snippet'.
    """
    max_pages = min(max_pages, MAX_PAGES)  # enforce hard cap
    findings = []
    seen_urls = set()
    
    if queries is None:
        queries = [query]
        
    is_career = False
    if category == "career":
        is_career = True
    else:
        combined_text = " ".join(queries).lower()
        is_career = _is_career_query(_extract_query_keywords(combined_text))

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

        # ── Stage 1.0: USAJobs (Career queries only) ─────────────
        if is_career:
            usajobs_page = None
            try:
                usajobs_page = context.new_page()
                for q in queries:
                    if len(findings) >= min(3, max_pages):
                        break
                    
                    simplified_q = " ".join(
                        [w for w in re.findall(r"[a-zA-Z0-9]+", q) if w.lower() not in STOP_WORDS]
                    )
                    if not simplified_q:
                        simplified_q = q
                    
                    _search_usajobs(
                        usajobs_page, simplified_q, findings, seen_urls,
                        max_to_add=min(3, max_pages) - len(findings),
                    )
            finally:
                if usajobs_page:
                    usajobs_page.close()

        # ── Stage 1.1: Mojeek ──────────────────────────────────────
        for q in queries:
            if len(findings) >= max_pages:
                break
                
            q_keywords = _extract_query_keywords(q)
            search_url = (
                "https://www.mojeek.com/search?q="
                + urllib.parse.quote_plus(q)
                + "&lb=en&fmt=10"
            )

            try:
                page.goto(search_url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
                raw_results = _extract_search_links(page)

                if raw_results:
                    # Filter URLs before parsing completely
                    for b in IRRELEVANT_URL_PATTERNS:
                        raw_results = [(u, t) for u, t in raw_results if b not in u.lower()]

                    # Pre-filter and rank by relevance
                    filtered = [
                        (url, text) for url, text in raw_results
                        if _is_title_relevant(text, q_keywords)
                    ]

                    def _relevance_score(item):
                        _, text = item
                        text_words = set(re.findall(r"[a-zA-Z0-9]+", text.lower()))
                        return len(text_words & q_keywords)

                    filtered.sort(key=_relevance_score, reverse=True)

                    for url, _link_text in filtered[:10]:
                        if len(findings) >= max_pages:
                            break
                        _visit_and_collect(page, url, q, q_keywords, findings, seen_urls)

            except Exception:
                pass  # Mojeek failed entirely — proceed to next query

        # ── Stage 1.5: Indeed (Career queries only) ──────────────
        if len(findings) < max_pages and is_career:
            for q in queries:
                if len(findings) >= max_pages:
                    break
                simplified_q = " ".join(
                    [w for w in re.findall(r"[a-zA-Z0-9]+", q) if w.lower() not in STOP_WORDS]
                )
                if not simplified_q:
                    simplified_q = q
                    
                _search_indeed(
                    page, simplified_q, findings, seen_urls,
                    max_to_add=max_pages - len(findings),
                )

        # ── Stage 2: Wikipedia (if needed) ───────────────────────
        if len(findings) < max_pages:
            for q in queries:
                if len(findings) >= max_pages:
                    break
                q_keywords = _extract_query_keywords(q)
                _search_wikipedia(
                    page, q, q_keywords, findings, seen_urls,
                    max_to_add=max_pages - len(findings),
                )

        # ── Stage 3: GitHub (if needed) ──────────────────────────
        if len(findings) < max_pages:
            for q in queries:
                if len(findings) >= max_pages:
                    break
                simplified_q = " ".join(
                    [w for w in re.findall(r"[a-zA-Z0-9]+", q) if w.lower() not in STOP_WORDS]
                )
                if not simplified_q:
                    simplified_q = q
                q_keywords = _extract_query_keywords(q)
                _search_github(
                    page, simplified_q, q_keywords, findings, seen_urls,
                    max_to_add=max_pages - len(findings),
                )

        # ── Stage 4: arXiv (if needed) ───────────────────────────
        if len(findings) < max_pages:
            for q in queries:
                if len(findings) >= max_pages:
                    break
                simplified_q = " ".join(
                    [w for w in re.findall(r"[a-zA-Z0-9]+", q) if w.lower() not in STOP_WORDS]
                )
                if not simplified_q:
                    simplified_q = q
                q_keywords = _extract_query_keywords(q)
                _search_arxiv(
                    page, simplified_q, q_keywords, findings, seen_urls,
                    max_to_add=max_pages - len(findings),
                )

        browser.close()

    # Only show "insufficient" if ALL four sources failed
    if len(findings) < 2:
        return [{
            "title": "Insufficient results",
            "url": "",
            "snippet": "Insufficient relevant sources found for this query."
        }]

    return findings
