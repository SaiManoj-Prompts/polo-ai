import unittest
from unittest.mock import patch, MagicMock
import json
import planner

class TestPlanner(unittest.TestCase):

    def setUp(self):
        self.query = "Compare LangChain and CrewAI"

    @patch('planner.requests.post')
    def test_12_step_plan_truncates_to_8(self, mock_post):
        # 12 steps
        steps = [f"Analyze aspect {i} of LangChain" for i in range(1, 13)]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": json.dumps({
                "plan": steps,
                "queries": ["LangChain vs CrewAI"],
                "category": "technical research"
            })
        }
        mock_post.return_value = mock_response

        result = planner.generate_plan(self.query)

        self.assertEqual(result["source"], "Ollama")
        self.assertEqual(len(result["plan"]), 8)
        self.assertEqual(result["plan"], steps[:8])
        self.assertEqual(result["category"], "technical research")
        self.assertTrue(any("langchain vs crewai" == q.lower() for q in result["queries"]))

    @patch('planner.requests.post')
    def test_3_step_plan_unchanged(self, mock_post):
        steps = ["Analyze one", "Analyze two", "Analyze three"]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": json.dumps({
                "plan": steps,
                "queries": ["LangChain vs CrewAI"],
                "category": "technical research"
            })
        }
        mock_post.return_value = mock_response

        result = planner.generate_plan(self.query)

        self.assertEqual(result["source"], "Ollama")
        self.assertEqual(len(result["plan"]), 3)
        self.assertEqual(result["plan"], steps)

    @patch('planner.requests.post')
    def test_2_step_plan_uses_fallback(self, mock_post):
        steps = ["Analyze one", "Analyze two"]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": json.dumps({
                "plan": steps,
                "queries": ["LangChain vs CrewAI"],
                "category": "technical research"
            })
        }
        mock_post.return_value = mock_response

        result = planner.generate_plan(self.query)

        self.assertEqual(result["source"], "Fallback")
        self.assertEqual(len(result["plan"]), 4) # fallback plan has 4 steps

    @patch('planner.requests.post')
    def test_malformed_response_uses_fallback(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "this is not json"
        }
        mock_post.return_value = mock_response

        result = planner.generate_plan(self.query)

        self.assertEqual(result["source"], "Fallback")

    @patch('planner.requests.post')
    def test_invalid_early_steps_still_uses_ollama_if_enough_valid(self, mock_post):
        steps = [
            "   ",
            "Research robotics",
            "Research healthcare",
            "   ",
            "   ",
            "Investigate real estate",
            "   ",
            "Explore blockchain",
            "Analyze aspect 1 of LangChain",
            "Analyze aspect 2 of LangChain",
            "Analyze aspect 3 of LangChain"
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": json.dumps({
                "plan": steps,
                "queries": ["LangChain vs CrewAI"],
                "category": "technical research"
            })
        }
        mock_post.return_value = mock_response

        result = planner.generate_plan(self.query)

        self.assertEqual(result["source"], "Ollama")
        self.assertEqual(len(result["plan"]), 3)
        self.assertEqual(result["plan"], [
            "Analyze aspect 1 of LangChain",
            "Analyze aspect 2 of LangChain",
            "Analyze aspect 3 of LangChain"
        ])

    @patch('planner.requests.post')
    def test_query_validation_expansions(self, mock_post):
        task_query = "Compare LangChain, CrewAI, and AutoGen for building open-source AI agents"

        test_cases = [
            ("LangChain architecture", True),
            ("CrewAI capabilities", True),
            ("LangChain", False),
            ("LangChain blockchain architecture", False),
            ("LangChain vs CrewAI", True),
            ("LangChain use cases", True),
            ("LangChain use", False),
            ("LangChain cases", False)
        ]

        for cand_query, expected_accepted in test_cases:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "response": json.dumps({
                    "plan": ["Step 1", "Step 2", "Step 3"],
                    "queries": [cand_query],
                    "category": "technical research"
                })
            }
            mock_post.return_value = mock_response

            result = planner.generate_plan(task_query)

            if expected_accepted:
                self.assertIn(cand_query, result["queries"], f"Expected '{cand_query}' to be accepted")
            else:
                self.assertEqual(result["queries"], [task_query], f"Expected '{cand_query}' to be rejected")

if __name__ == '__main__':
    unittest.main()
