"""Integration test for the core research workflow."""

import unittest
from unittest.mock import patch, MagicMock
import tempfile
import os
import json
import requests

import planner
import db_manager
import browser_controller
from report_generator import generate_report

class TestWorkflowIntegration(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._original_db = db_manager.DB_FILE
        db_manager.DB_FILE = self.db_path
        db_manager.init_db()

    def tearDown(self):
        db_manager.DB_FILE = self._original_db
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    @patch("planner.requests.post")
    @patch("browser_controller.search_and_collect")
    def test_successful_research_workflow(self, mock_search, mock_post):
        """Proves a request can be planned, receive findings, save to DB, and produce a report."""
        # 1. Mock Ollama response (External Dependency)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": '{"plan": ["Step 1", "Step 2", "Step 3"], "queries": ["Compare open-source AI frameworks"], "category": "technical research"}'
        }
        mock_post.return_value = mock_response

        # 2. Mock browser collection (External Dependency)
        mock_search.return_value = [
            {"title": "Great Discovery", "url": "https://example.com", "snippet": "We found something amazing."}
        ]

        task_query = "Compare AI agent frameworks"

        # --- EXECUTING THE WORKFLOW (replicating app.py sequence) ---
        # A. Plan
        ai_plan = planner.generate_plan(task_query)
        
        # B. Collect
        findings = browser_controller.search_and_collect(
            task_query, 
            queries=ai_plan.get("queries"), 
            category=ai_plan.get("category")
        )
        
        # C. Save
        db_manager.save_task(
            query=task_query,
            status="Completed",
            findings=findings,
            queries=ai_plan.get("queries")
        )

        # D. Report
        md_report, json_report = generate_report(task_query, findings)

        # --- ASSERTIONS ---
        # Verify planner logic parsed the JSON and validated it correctly
        self.assertEqual(ai_plan["category"], "technical research")
        self.assertIn("Compare open-source AI frameworks", ai_plan["queries"])

        # Verify collection was called with correct parameters from the planner
        mock_search.assert_called_once_with(
            task_query, 
            queries=ai_plan.get("queries"), 
            category=ai_plan.get("category")
        )
        
        # Verify state was correctly persisted to the DB
        saved_tasks = db_manager.get_all_tasks()
        self.assertEqual(len(saved_tasks), 1)
        self.assertEqual(saved_tasks[0]["query"], task_query)
        self.assertEqual(len(saved_tasks[0]["findings"]), 1)
        self.assertEqual(saved_tasks[0]["findings"][0]["title"], "Great Discovery")

        # Verify report generation incorporated the findings
        self.assertIn("Great Discovery", md_report)
        self.assertIn("We found something amazing", md_report)
        
        report_data = json.loads(json_report)
        self.assertEqual(report_data["completion_status"], "Complete - Sources compiled.")
        self.assertEqual(len(report_data["key_findings"]), 1)

    @patch("planner.requests.post")
    @patch("browser_controller.search_and_collect")
    def test_failure_handling(self, mock_search, mock_post):
        """Asserts external-service failure and empty-findings are handled safely."""
        # 1. Mock Ollama failure
        mock_post.side_effect = requests.exceptions.ConnectionError("Ollama is down")

        # 2. Mock browser collection returning insufficient results sentinel
        mock_search.return_value = [
            {"title": "Insufficient results", "url": "", "snippet": ""}
        ]

        task_query = "impossible task"

        # --- EXECUTING THE WORKFLOW (replicating app.py sequence) ---
        # A. Plan
        ai_plan = planner.generate_plan(task_query)
        
        # B. Collect
        findings = browser_controller.search_and_collect(
            task_query, 
            queries=ai_plan.get("queries"),
            category=ai_plan.get("category")
        )

        # C. Save
        db_manager.save_task(
            query=task_query,
            status="Completed",
            findings=findings,
            queries=ai_plan.get("queries")
        )

        # D. Report
        md_report, json_report = generate_report(task_query, findings)

        # --- ASSERTIONS ---
        # Verify planner degraded safely to the fallback plan
        self.assertEqual(ai_plan["source"], "Fallback")

        # Verify state was persisted despite failures
        saved_tasks = db_manager.get_all_tasks()
        self.assertEqual(len(saved_tasks), 1)
        self.assertEqual(saved_tasks[0]["findings"][0]["title"], "Insufficient results")

        # Verify report safely handles the failure without crashing or inventing data
        self.assertIn("Incomplete - insufficient sources found.", md_report)

        report_data = json.loads(json_report)
        self.assertEqual(report_data["completion_status"], "Incomplete - insufficient sources found.")
        self.assertEqual(len(report_data["key_findings"]), 0)

    @patch("planner.requests.post")
    @patch("browser_controller.search_and_collect")
    def test_offtopic_source_produces_incomplete_status(self, mock_search, mock_post):
        """An off-topic source (like 'AI art - Wikipedia') with a real URL
        must NOT produce 'Complete - Sources compiled.' — it should trigger
        the 'Incomplete' pathway."""
        # 1. Mock Ollama returning a valid plan
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": '{"plan": ["Step 1", "Step 2", "Step 3"], "queries": ["LangChain vs CrewAI vs AutoGen"], "category": "technical research"}'
        }
        mock_post.return_value = mock_response

        # 2. Mock browser returning the insufficient sentinel (after post-collection gate)
        mock_search.return_value = [
            {"title": "Insufficient results", "url": "", "snippet": "Insufficient relevant sources found for this query."}
        ]

        task_query = "Compare LangChain, CrewAI, and AutoGen for building open-source AI agents"

        # --- EXECUTING THE WORKFLOW ---
        ai_plan = planner.generate_plan(task_query)
        findings = browser_controller.search_and_collect(
            task_query,
            queries=ai_plan.get("queries"),
            category=ai_plan.get("category")
        )

        db_manager.save_task(
            query=task_query,
            status="Completed",
            findings=findings,
            queries=ai_plan.get("queries")
        )

        md_report, json_report = generate_report(task_query, findings)

        # --- ASSERTIONS ---
        self.assertIn("Incomplete - insufficient sources found.", md_report)

        report_data = json.loads(json_report)
        self.assertEqual(report_data["completion_status"], "Incomplete - insufficient sources found.")
        self.assertEqual(len(report_data["key_findings"]), 0)


if __name__ == "__main__":
    unittest.main()
