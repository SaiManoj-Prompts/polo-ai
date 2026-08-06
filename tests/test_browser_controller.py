"""Deterministic tests for browser_controller.py — search orchestration,
evaluation budgeting, GitHub reservation, insufficient-results fallback,
and off-topic content filtering.

All tests mock Playwright and external network access so they run without
a real browser or live web connectivity."""

import unittest
from unittest.mock import patch, MagicMock

from browser_controller import (
    search_and_collect,
    _visit_and_collect,
    _extract_query_keywords,
    _is_safe_url,
    _is_career_query,
    MAX_PAGES,
    MAX_CANDIDATE_EVALUATIONS,
)


# ── Shared helpers ───────────────────────────────────────────────────────


def _make_playwright_cm():
    """Return a fully wired mock for the ``sync_playwright()`` context manager.

    The mock provides:
      - p.chromium.launch() → browser
      - browser.new_context() → context
      - context.new_page()   → page (MagicMock)
      - browser.close()      → no-op
    """
    mock_page = MagicMock(name="page")
    mock_page.url = "https://www.mojeek.com/search"

    mock_context = MagicMock(name="context")
    mock_context.new_page.return_value = mock_page

    mock_browser = MagicMock(name="browser")
    mock_browser.new_context.return_value = mock_context

    mock_pw = MagicMock(name="playwright")
    mock_pw.chromium.launch.return_value = mock_browser

    cm = MagicMock(name="sync_playwright_cm")
    cm.__enter__ = MagicMock(return_value=mock_pw)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _mojeek_links(n):
    """Return *n* distinct ``(url, link_text)`` tuples for mocked Mojeek."""
    return [(f"http://result{i}.com/page", f"Result {i}") for i in range(n)]


def _make_visit_side_effect(max_successes=float("inf")):
    """Build a ``_visit_and_collect`` replacement.

    The mock:
      - respects ``attempt_state`` budget (increments counter, obeys caps)
      - deduplicates via ``seen_urls``
      - appends a finding for the first *max_successes* unique URLs
      - returns ``False`` for subsequent calls (simulates irrelevant content)

    Findings include representative query keywords so they survive the
    post-collection relevance gate (which requires ≥2 keyword matches).
    """
    success_count = [0]

    def side_effect(page, url, query, query_keywords, findings, seen_urls,
                    attempt_state=None):
        normalized = url.rstrip("/")
        if normalized in seen_urls:
            return False
        if attempt_state:
            c = attempt_state["count"][0]
            gm = attempt_state.get("global_max", float("inf"))
            qm = attempt_state.get("max", float("inf"))
            if c >= gm or c >= qm:
                return False
            attempt_state["count"][0] += 1
        seen_urls.add(normalized)
        if success_count[0] < max_successes:
            findings.append({
                "title": f"AI Agent Frameworks Result {success_count[0]}",
                "url": url,
                "snippet": f"Comparing agent frameworks and their architecture {success_count[0]}.",
            })
            success_count[0] += 1
            return True
        return False

    return side_effect


# ── 1. search_and_collect: max_pages cap ─────────────────────────────────


class TestResultsCappedAtMaxPages(unittest.TestCase):

    def test_results_never_exceed_max_pages(self):
        """Final output length must be ≤ max_pages regardless of source volume."""
        max_pages = 3
        with patch("browser_controller.sync_playwright",
                   return_value=_make_playwright_cm()), \
             patch("browser_controller._extract_search_links",
                   return_value=_mojeek_links(15)), \
             patch("browser_controller._is_title_relevant", return_value=True), \
             patch("browser_controller._visit_and_collect",
                   side_effect=_make_visit_side_effect()), \
             patch("browser_controller._search_github"), \
             patch("browser_controller._search_wikipedia"), \
             patch("browser_controller._search_arxiv"):
            result = search_and_collect("AI agent frameworks", max_pages=max_pages)

        self.assertLessEqual(len(result), max_pages)
        # Verify they are real findings, not sentinel
        for f in result:
            self.assertTrue(f.get("url"))


# ── 2. search_and_collect: evaluation budget ─────────────────────────────


class TestCandidateEvaluationBudget(unittest.TestCase):

    def test_visit_calls_bounded_by_max_candidate_evaluations(self):
        """_visit_and_collect must not be called more than
        MAX_CANDIDATE_EVALUATIONS times in the Mojeek loop."""
        with patch("browser_controller.sync_playwright",
                   return_value=_make_playwright_cm()), \
             patch("browser_controller._extract_search_links",
                   return_value=_mojeek_links(15)), \
             patch("browser_controller._is_title_relevant", return_value=True), \
             patch("browser_controller._visit_and_collect",
                   side_effect=_make_visit_side_effect(max_successes=0)) as mv, \
             patch("browser_controller._search_github"), \
             patch("browser_controller._search_wikipedia"), \
             patch("browser_controller._search_arxiv"):
            # max_pages=2 disables the reservation check (requires >= 3)
            # so the full budget is consumed in Mojeek
            search_and_collect("AI agent frameworks", max_pages=2)

        self.assertLessEqual(mv.call_count, MAX_CANDIDATE_EVALUATIONS)


# ── 3. search_and_collect: GitHub reservation ────────────────────────────


class TestGitHubReservation(unittest.TestCase):

    def test_github_entered_when_mojeek_insufficient(self):
        """When Mojeek yields fewer than max_pages findings, the GitHub
        fallback must be invoked."""
        with patch("browser_controller.sync_playwright",
                   return_value=_make_playwright_cm()), \
             patch("browser_controller._extract_search_links",
                   return_value=_mojeek_links(15)), \
             patch("browser_controller._is_title_relevant", return_value=True), \
             patch("browser_controller._visit_and_collect",
                   side_effect=_make_visit_side_effect(max_successes=2)), \
             patch("browser_controller._search_github") as mock_gh, \
             patch("browser_controller._search_wikipedia"), \
             patch("browser_controller._search_arxiv"):
            search_and_collect("AI agent frameworks", max_pages=5)

        self.assertTrue(mock_gh.called,
                        "GitHub fallback must be called when Mojeek < max_pages")

    def test_mojeek_stops_to_reserve_two_evaluations(self):
        """With max_pages >= 3 and findings < max_pages, the Mojeek loop must
        stop at MAX_CANDIDATE_EVALUATIONS − 2 to leave budget for GitHub."""
        with patch("browser_controller.sync_playwright",
                   return_value=_make_playwright_cm()), \
             patch("browser_controller._extract_search_links",
                   return_value=_mojeek_links(15)), \
             patch("browser_controller._is_title_relevant", return_value=True), \
             patch("browser_controller._visit_and_collect",
                   side_effect=_make_visit_side_effect(max_successes=2)) as mv, \
             patch("browser_controller._search_github"), \
             patch("browser_controller._search_wikipedia"), \
             patch("browser_controller._search_arxiv"):
            search_and_collect("AI agent frameworks", max_pages=5)

        self.assertEqual(mv.call_count, MAX_CANDIDATE_EVALUATIONS - 2)

    def test_github_not_entered_when_mojeek_fills_max_pages(self):
        """When Mojeek alone produces max_pages results, GitHub must not
        be called."""
        with patch("browser_controller.sync_playwright",
                   return_value=_make_playwright_cm()), \
             patch("browser_controller._extract_search_links",
                   return_value=_mojeek_links(15)), \
             patch("browser_controller._is_title_relevant", return_value=True), \
             patch("browser_controller._visit_and_collect",
                   side_effect=_make_visit_side_effect()), \
             patch("browser_controller._search_github") as mock_gh, \
             patch("browser_controller._search_wikipedia"), \
             patch("browser_controller._search_arxiv"):
            search_and_collect("AI agent frameworks", max_pages=3)

        self.assertFalse(mock_gh.called,
                         "GitHub must not be called when Mojeek fills max_pages")


# ── 4. search_and_collect: insufficient results ─────────────────────────


class TestInsufficientResults(unittest.TestCase):

    def test_sentinel_when_mojeek_returns_nothing(self):
        """When Mojeek has no results and all fallbacks fail, the
        insufficient-results sentinel must be returned."""
        with patch("browser_controller.sync_playwright",
                   return_value=_make_playwright_cm()), \
             patch("browser_controller._extract_search_links",
                   return_value=[]), \
             patch("browser_controller._search_github"), \
             patch("browser_controller._search_wikipedia"), \
             patch("browser_controller._search_arxiv"):
            result = search_and_collect("xyz completely nonsensical query")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Insufficient results")
        self.assertFalse(result[0].get("url"))

    def test_sentinel_when_all_visits_fail(self):
        """Even when Mojeek has links, if every visit fails the sentinel
        must still be returned."""
        with patch("browser_controller.sync_playwright",
                   return_value=_make_playwright_cm()), \
             patch("browser_controller._extract_search_links",
                   return_value=_mojeek_links(10)), \
             patch("browser_controller._is_title_relevant", return_value=True), \
             patch("browser_controller._visit_and_collect",
                   side_effect=_make_visit_side_effect(max_successes=0)), \
             patch("browser_controller._search_github"), \
             patch("browser_controller._search_wikipedia"), \
             patch("browser_controller._search_arxiv"):
            result = search_and_collect("test query", max_pages=5)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Insufficient results")


# ── 5. _visit_and_collect: content filtering ─────────────────────────────


class TestVisitAndCollectFiltering(unittest.TestCase):
    """Test off-topic and on-topic filtering via mocked page I/O.
    Only page.goto, page.title, and snippet extraction are mocked;
    all classification logic runs for real."""

    @patch("browser_controller._block_forms_and_submissions")
    @patch("browser_controller._extract_text_snippet")
    def test_blockchain_content_rejected(self, mock_snippet, _mock_block):
        """A finding with blockchain/crypto/NFT terms must be rejected
        when the query is about generic AI agent frameworks."""
        mock_page = MagicMock()
        mock_page.title.return_value = "BlockchainAgent - DeFi AI Framework"
        mock_snippet.return_value = (
            "A blockchain-based AI agent framework for cryptocurrency "
            "trading and NFT marketplace automation that leverages "
            "smart contracts for decentralised governance."
        )

        findings = []
        seen_urls = set()
        query = "Compare open-source AI agent frameworks"
        keywords = _extract_query_keywords(query)

        result = _visit_and_collect(
            mock_page, "https://blockchain-agent.com/",
            query, keywords, findings, seen_urls,
        )

        self.assertFalse(result)
        self.assertEqual(len(findings), 0)

    @patch("browser_controller._block_forms_and_submissions")
    @patch("browser_controller._extract_text_snippet")
    def test_legitimate_finding_accepted(self, mock_snippet, _mock_block):
        """On-topic content with sufficient keyword overlap must be accepted."""
        mock_page = MagicMock()
        mock_page.title.return_value = (
            "AutoGPT vs BabyAGI: Comparing AI Agent Frameworks"
        )
        mock_snippet.return_value = (
            "AutoGPT and BabyAGI are two leading open-source AI agent "
            "frameworks. This comparison evaluates their architecture, "
            "extensibility, and performance across various benchmarks."
        )

        findings = []
        seen_urls = set()
        query = "Compare open-source AI agent frameworks"
        keywords = _extract_query_keywords(query)

        result = _visit_and_collect(
            mock_page, "https://example.com/ai-frameworks",
            query, keywords, findings, seen_urls,
        )

        self.assertTrue(result)
        self.assertEqual(len(findings), 1)


# ── 6. Pure helper functions ─────────────────────────────────────────────


class TestSafeUrl(unittest.TestCase):

    def test_normal_url_is_safe(self):
        self.assertTrue(_is_safe_url("https://example.com/article"))

    def test_login_url_blocked(self):
        self.assertFalse(_is_safe_url("https://example.com/login"))

    def test_pdf_download_blocked(self):
        self.assertFalse(_is_safe_url("https://example.com/paper.pdf"))

    def test_payment_url_blocked(self):
        self.assertFalse(_is_safe_url("https://pay.example.com/checkout"))


class TestCareerQueryDetection(unittest.TestCase):

    def test_internship_detected(self):
        kw = _extract_query_keywords("data science internships")
        self.assertTrue(_is_career_query(kw))

    def test_generic_research_not_career(self):
        kw = _extract_query_keywords("AI agent frameworks comparison")
        self.assertFalse(_is_career_query(kw))


# ── 7. Wikipedia redirect path filtering ─────────────────────────────────


class TestWikipediaRedirectFiltering(unittest.TestCase):
    """The Wikipedia redirect path (Case 1) must run the same relevance
    checks as Case 2 — specifically _is_snippet_relevant() and the
    off-topic domain check — so off-topic redirects are rejected."""

    @patch("browser_controller._block_forms_and_submissions")
    @patch("browser_controller._extract_text_snippet")
    def test_wikipedia_redirect_rejects_off_topic_article(self, mock_snippet, _mock_block):
        """When Wikipedia redirects to an off-topic article like 'AI art',
        the snippet-relevance check should reject it even though the title
        contains the keyword 'ai'."""
        from browser_controller import _search_wikipedia

        mock_page = MagicMock()
        # Simulate Wikipedia redirecting to /wiki/AI_art
        mock_page.url = "https://en.wikipedia.org/wiki/AI_art"
        mock_page.title.return_value = "AI art - Wikipedia"
        mock_snippet.return_value = (
            "There are many approaches used by artists to develop AI visual art. "
            "Some artists create these works using deep learning algorithms and "
            "generative adversarial networks to produce unique paintings."
        )

        findings = []
        seen_urls = set()
        query = "Compare LangChain, CrewAI, and AutoGen for building open-source AI agents"
        query_keywords = _extract_query_keywords(query)

        _search_wikipedia(
            mock_page, query, query_keywords, findings, seen_urls,
            max_to_add=2, attempt_state=None
        )

        self.assertEqual(len(findings), 0,
                         "Off-topic Wikipedia redirect 'AI art' must be rejected")


# ── 8. Title relevance threshold for broad queries ───────────────────────


class TestTitleRelevanceThreshold(unittest.TestCase):
    """For queries with ≥3 keywords, _is_title_relevant() must require
    ≥2 keyword matches, preventing a single common word from
    greenlighting unrelated pages."""

    def test_single_keyword_match_rejected_for_broad_query(self):
        """'AI art - Wikipedia' matches only 'ai' — must be rejected
        for a broad multi-keyword query."""
        from browser_controller import _is_title_relevant
        keywords = _extract_query_keywords(
            "Compare LangChain, CrewAI, and AutoGen for building open-source AI agents"
        )
        self.assertGreaterEqual(len(keywords), 3, "Sanity: query should have ≥3 keywords")
        self.assertFalse(
            _is_title_relevant("AI art - Wikipedia", keywords),
            "Title matching only 1 keyword should be rejected for broad queries"
        )

    def test_multi_keyword_match_accepted_for_broad_query(self):
        """'LangChain vs CrewAI AI Agent Frameworks' matches multiple
        keywords — must be accepted."""
        from browser_controller import _is_title_relevant
        keywords = _extract_query_keywords(
            "Compare LangChain, CrewAI, and AutoGen for building open-source AI agents"
        )
        self.assertTrue(
            _is_title_relevant("LangChain vs CrewAI AI Agent Frameworks", keywords),
            "Title matching ≥2 keywords should be accepted"
        )

    def test_narrow_query_still_allows_single_match(self):
        """For a narrow query (<3 keywords), 1 match should still suffice."""
        from browser_controller import _is_title_relevant
        keywords = _extract_query_keywords("LangChain guide")
        self.assertLess(len(keywords), 3, "Sanity: narrow query should have <3 keywords")
        self.assertTrue(
            _is_title_relevant("LangChain Documentation", keywords),
            "Narrow queries should accept single-keyword title matches"
        )


# ── 9. Post-collection relevance gate ────────────────────────────────────


class TestPostCollectionRelevanceGate(unittest.TestCase):
    """When all collected findings are off-topic (< 2 keyword matches),
    search_and_collect must return the insufficient results sentinel."""

    def test_single_offtopic_finding_returns_insufficient(self):
        """A single off-topic finding (only 1 keyword match in
        title+snippet) should be filtered to produce the
        insufficient-results sentinel."""
        with patch("browser_controller.sync_playwright",
                   return_value=_make_playwright_cm()), \
             patch("browser_controller._extract_search_links",
                   return_value=[]), \
             patch("browser_controller._search_github"), \
             patch("browser_controller._search_wikipedia") as mock_wiki, \
             patch("browser_controller._search_arxiv"), \
             patch("browser_controller.postprocess_findings") as mock_pp:

            # Simulate postprocess returning the off-topic AI art finding
            mock_pp.return_value = [{
                "title": "AI art - Wikipedia",
                "url": "https://en.wikipedia.org/wiki/AI_art",
                "snippet": "There are many approaches used by artists to develop AI visual art.",
                "source_type": "Other",
                "quality_score": 1
            }]

            result = search_and_collect(
                "Compare LangChain, CrewAI, and AutoGen for building open-source AI agents",
                max_pages=5
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Insufficient results",
                         "Off-topic finding must be filtered; sentinel returned")
        self.assertFalse(result[0].get("url"))


if __name__ == "__main__":
    unittest.main()
