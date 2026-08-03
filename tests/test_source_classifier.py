"""Deterministic tests for source_classifier.py — URL classification,
quality scoring, canonical dedup, and postprocess capping."""

import unittest

from source_classifier import (
    get_source_type,
    get_canonical_url,
    get_quality_score,
    postprocess_findings,
)


# ── URL → source-type classification ────────────────────────────────────


class TestGetSourceType(unittest.TestCase):
    """Representative URLs must map to the correct source category."""

    # GitHub
    def test_github_repo(self):
        self.assertEqual(
            get_source_type("https://github.com/langchain-ai/langchain"),
            "GitHub",
        )

    def test_github_subdomain(self):
        self.assertEqual(
            get_source_type("https://pages.github.com/project"),
            "GitHub",
        )

    # Research paper
    def test_arxiv_paper(self):
        self.assertEqual(
            get_source_type("https://arxiv.org/abs/2301.12345"),
            "Research paper",
        )

    # Government
    def test_usajobs(self):
        self.assertEqual(
            get_source_type("https://www.usajobs.gov/job/12345"),
            "Government",
        )

    def test_generic_gov_domain(self):
        self.assertEqual(
            get_source_type("https://www.nasa.gov/missions"),
            "Government",
        )

    # Official documentation
    def test_readthedocs(self):
        self.assertEqual(
            get_source_type("https://project.readthedocs.io/en/latest/"),
            "Official documentation",
        )

    def test_docs_subdomain(self):
        self.assertEqual(
            get_source_type("https://docs.python.org/3/library/"),
            "Official documentation",
        )

    def test_docs_path_segment(self):
        self.assertEqual(
            get_source_type("https://example.com/docs/api-reference"),
            "Official documentation",
        )

    def test_nested_documentation_path(self):
        """Verifies commit 3e7d405 — /documentation/ nested path segment."""
        self.assertEqual(
            get_source_type("https://example.com/documentation/api"),
            "Official documentation",
        )

    # Job listings
    def test_indeed(self):
        self.assertEqual(
            get_source_type("https://www.indeed.com/viewjob?jk=abc"),
            "Job listing",
        )

    def test_glassdoor(self):
        self.assertEqual(
            get_source_type("https://www.glassdoor.com/job/listing"),
            "Job listing",
        )

    def test_linkedin_jobs_path(self):
        self.assertEqual(
            get_source_type("https://www.linkedin.com/jobs/view/12345"),
            "Job listing",
        )

    def test_linkedin_profile_is_not_job(self):
        """LinkedIn profiles without /jobs/ must not classify as Job listing."""
        result = get_source_type("https://www.linkedin.com/in/profile")
        self.assertNotEqual(result, "Job listing")

    # News / article
    def test_techcrunch(self):
        self.assertEqual(
            get_source_type("https://techcrunch.com/2024/01/article"),
            "News/article",
        )

    def test_blog_path(self):
        self.assertEqual(
            get_source_type("https://example.com/blog/post-title"),
            "News/article",
        )

    def test_news_path(self):
        self.assertEqual(
            get_source_type("https://example.com/news/latest"),
            "News/article",
        )

    # Other
    def test_generic_url(self):
        self.assertEqual(
            get_source_type("https://randomsite.com/page"),
            "Other",
        )

    def test_wikipedia_falls_to_other(self):
        """Wikipedia has no explicit category; should fall through to Other."""
        self.assertEqual(
            get_source_type("https://en.wikipedia.org/wiki/Python"),
            "Other",
        )


# ── Canonical URL deduplication ──────────────────────────────────────────


class TestGetCanonicalUrl(unittest.TestCase):

    def test_strips_www_prefix(self):
        self.assertEqual(
            get_canonical_url("https://www.example.com/page"),
            get_canonical_url("https://example.com/page"),
        )

    def test_strips_trailing_slash(self):
        self.assertEqual(
            get_canonical_url("https://example.com/page/"),
            get_canonical_url("https://example.com/page"),
        )

    def test_removes_utm_tracking_params(self):
        self.assertEqual(
            get_canonical_url("https://example.com/page?utm_source=x&id=1"),
            get_canonical_url("https://example.com/page?id=1"),
        )

    def test_preserves_meaningful_params(self):
        canonical = get_canonical_url("https://example.com/search?q=test&page=2")
        self.assertIn("q=test", canonical)
        self.assertIn("page=2", canonical)


# ── Quality scoring hierarchy ────────────────────────────────────────────


class TestGetQualityScore(unittest.TestCase):

    def test_government_outranks_other(self):
        gov = get_quality_score("Government", "https://www.usajobs.gov/job/1")
        other = get_quality_score("Other", "https://random.com")
        self.assertGreater(gov, other)

    def test_first_party_root_bonus(self):
        with_bonus = get_quality_score("GitHub", "https://github.com/user/repo")
        without = get_quality_score("GitHub", "https://some-mirror.com/repo")
        self.assertGreater(with_bonus, without)

    def test_full_score_hierarchy(self):
        """Gov >= Docs >= Research >= GitHub >= Job > News > Other."""
        gov = get_quality_score("Government", "https://usajobs.gov/x")
        docs = get_quality_score("Official documentation", "https://readthedocs.io/x")
        research = get_quality_score("Research paper", "https://arxiv.org/x")
        github = get_quality_score("GitHub", "https://github.com/x")
        job = get_quality_score("Job listing", "https://indeed.com/x")
        news = get_quality_score("News/article", "https://techcrunch.com/x")
        other = get_quality_score("Other", "https://x.com/x")

        self.assertGreaterEqual(gov, docs)
        self.assertGreaterEqual(docs, research)
        self.assertGreaterEqual(research, github)
        self.assertGreaterEqual(github, job)
        self.assertGreater(job, news)
        self.assertGreater(news, other)


# ── postprocess_findings ─────────────────────────────────────────────────


class TestPostprocessFindings(unittest.TestCase):
    """Deduplication, scoring, and max_pages enforcement."""

    @staticmethod
    def _finding(idx, url=None):
        return {
            "title": f"Finding {idx}",
            "url": url or f"https://example{idx}.com/page",
            "snippet": f"Detailed content for finding number {idx}.",
        }

    def test_caps_at_max_pages(self):
        findings = [self._finding(i) for i in range(10)]
        result = postprocess_findings(findings, max_pages=3, query="test")
        self.assertLessEqual(len(result), 3)

    def test_empty_input_returns_empty(self):
        self.assertEqual(postprocess_findings([], max_pages=5, query="test"), [])

    def test_deduplicates_canonical_urls(self):
        findings = [
            self._finding(1, url="https://www.example.com/page/"),
            self._finding(2, url="https://example.com/page"),
        ]
        result = postprocess_findings(findings, max_pages=5, query="test")
        self.assertEqual(len(result), 1)

    def test_annotates_source_type(self):
        findings = [self._finding(1, url="https://github.com/user/repo")]
        result = postprocess_findings(findings, max_pages=5, query="test")
        self.assertEqual(result[0]["source_type"], "GitHub")


if __name__ == "__main__":
    unittest.main()
