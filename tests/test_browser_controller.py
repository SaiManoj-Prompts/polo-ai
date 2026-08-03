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
                "title": f"Result {success_count[0]}",
                "url": url,
                "snippet": f"Content about the research topic {success_count[0]}.",
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


if __name__ == "__main__":
    unittest.main()
