import urllib.parse
import re
from typing import List, Dict, Any
import copy

STOP_WORDS = {
    "the", "is", "a", "an", "of", "in", "for", "and", "to", "with",
    "on", "at", "by", "from", "or", "as", "it", "be", "are", "was",
    "were", "been", "has", "have", "had", "do", "does", "did", "but",
    "not", "so", "if", "its", "my", "that", "this", "what", "which",
    "who", "how", "when", "where", "why", "can", "will", "should",
    "would", "could", "most", "more", "very", "just", "about",
}

def get_canonical_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)

    hostname = (parsed.hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    path = parsed.path
    if path.endswith("/") and len(path) > 1:
        path = path[:-1]
    elif not path:
        path = "/"

    query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    preserved = []
    for k, v in query_params:
        k_lower = k.lower()
        if k_lower.startswith("utm_") or k_lower in ("gclid", "fbclid"):
            continue
        preserved.append((k, v))

    preserved.sort(key=lambda x: (x[0], x[1]))
    query_str = urllib.parse.urlencode(preserved)

    canonical = hostname + path
    if query_str:
        canonical += "?" + query_str
    return canonical

def get_source_type(url: str, title: str = "", query: str = "") -> str:
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    path = parsed.path.lower()

    # 1. Government
    if hostname == "usajobs.gov" or hostname.endswith(".usajobs.gov") or hostname.endswith(".gov"):
        return "Government"

    # 2. GitHub
    if hostname == "github.com" or hostname.endswith(".github.com"):
        return "GitHub"

    # 3. Research paper
    if hostname == "arxiv.org" or hostname.endswith(".arxiv.org"):
        return "Research paper"

    # 4. Official documentation
    is_docs = False
    if hostname == "readthedocs.io" or hostname.endswith(".readthedocs.io"):
        is_docs = True
    elif hostname.startswith("docs."):
        is_docs = True
    elif path.startswith("/docs") or path.startswith("/documentation"):
        is_docs = True
    else:
        # Title based rule
        if title and query:
            query_tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if t not in STOP_WORDS and len(t) >= 3]
            title_tokens = re.findall(r"[a-z0-9]+", title.lower())
            if query_tokens and title_tokens:
                if "docs" in title_tokens or "documentation" in title_tokens:
                    # Check for overlap
                    if any(qt in title_tokens for qt in query_tokens):
                        is_docs = True

    if is_docs:
        return "Official documentation"

    # 5. Job listing
    known_job_hosts = {"indeed.com", "glassdoor.com", "linkedin.com", "greenhouse.io", "lever.co", "myworkdayjobs.com"}
    is_job = False
    for job_host in known_job_hosts:
        if hostname == job_host or hostname.endswith(f".{job_host}"):
            if job_host == "linkedin.com":
                if path.startswith("/jobs/") or path == "/jobs":
                    is_job = True
            else:
                is_job = True
            break

    if is_job:
        return "Job listing"

    # 6. News/article
    known_news_hosts = {"techcrunch.com", "wired.com", "theverge.com", "nytimes.com"}
    is_news = False
    for news_host in known_news_hosts:
        if hostname == news_host or hostname.endswith(f".{news_host}"):
            is_news = True
            break
    if not is_news:
        if path.startswith("/news/") or path.startswith("/article/") or path.startswith("/blog/"):
            is_news = True

    if is_news:
        return "News/article"

    # 7. Other
    return "Other"

def get_quality_score(source_type: str, url: str) -> int:
    base_scores = {
        "Government": 12,
        "Official documentation": 11,
        "Research paper": 10,
        "GitHub": 9,
        "Job listing": 8,
        "News/article": 5,
        "Other": 1
    }

    score = base_scores.get(source_type, 1)

    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    # Exact first-party root bonus
    exact_roots = {"usajobs.gov", "github.com", "arxiv.org", "indeed.com", "readthedocs.io"}
    if hostname in exact_roots:
        score += 2

    return score

def postprocess_findings(findings: List[Dict[str, Any]], max_pages: int, query: str = "") -> List[Dict[str, Any]]:
    if not findings:
        return []

    seen_canonical_urls = set()
    seen_content = set()

    candidates = []

    for f in findings:
        title = f.get("title", "")
        url = f.get("url", "")
        snippet = f.get("snippet", "")

        canonical_url = get_canonical_url(url)

        parsed = urllib.parse.urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if hostname.startswith("www."):
            hostname = hostname[4:]

        norm_title = re.sub(r"[^a-z0-9]", "", title.lower())
        norm_snippet = re.sub(r"[^a-z0-9]", "", snippet.lower())

        if canonical_url in seen_canonical_urls:
            continue

        if norm_title and norm_snippet:
            content_sig = (hostname, norm_title, norm_snippet)
            if content_sig in seen_content:
                continue
            seen_content.add(content_sig)

        seen_canonical_urls.add(canonical_url)

        source_type = get_source_type(url, title, query)
        score = get_quality_score(source_type, url)

        copied_f = copy.deepcopy(f)
        copied_f["source_type"] = source_type
        copied_f["quality_score"] = score

        candidates.append({
            "finding": copied_f,
            "source_type": source_type,
            "score": score,
            "canonical_url": canonical_url,
            "norm_title": norm_title
        })

    # Sort candidates initially: score DESC, canonical_url ASC, norm_title ASC
    candidates.sort(key=lambda x: (-x["score"], x["canonical_url"], x["norm_title"]))

    # Group by source type
    groups = {}
    for c in candidates:
        stype = c["source_type"]
        if stype not in groups:
            groups[stype] = []
        groups[stype].append(c)

    # Define group order: max score DESC, best candidate canonical ASC, source_type ASC
    ordered_groups = []
    for stype, items in groups.items():
        ordered_groups.append({
            "source_type": stype,
            "max_score": items[0]["score"],
            "best_canonical": items[0]["canonical_url"],
            "items": items
        })

    ordered_groups.sort(key=lambda g: (-g["max_score"], g["best_canonical"], g["source_type"]))

    final_list = []

    while len(final_list) < max_pages and any(g["items"] for g in ordered_groups):
        for g in ordered_groups:
            if len(final_list) >= max_pages:
                break
            if g["items"]:
                final_list.append(g["items"].pop(0)["finding"])

    return final_list
