import json
import requests
from typing import List

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3"

def generate_plan(query: str) -> List[str]:
    """
    Generates a 3 to 6 step research plan using local Ollama.
    Returns a fallback plan if Ollama is unavailable or fails.
    """
    fallback_plan = [
        "Define query terms and core keywords",
        "Search web sources and extract raw text",
        "Filter out irrelevant navigation noise",
        "Synthesize the findings into a report"
    ]

    prompt = f"""You are an expert research planner. 
The user wants to research the following query: "{query}"

Create a step-by-step research plan containing between 3 and 6 steps. 
Respond ONLY with a valid JSON array of strings. Do not include any markdown formatting, code blocks, or conversational text.

Example output format:
["Step 1 description", "Step 2 description", "Step 3 description"]
"""

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        response_text = data.get("response", "")
        
        # Parse the JSON response
        plan = json.loads(response_text)
        
        if isinstance(plan, list) and all(isinstance(step, str) for step in plan) and len(plan) > 0:
            return plan
        else:
            # If the response isn't a list of strings, fall back
            return fallback_plan

    except (requests.exceptions.RequestException, json.JSONDecodeError, ValueError):
        # Catch connection errors, timeouts, or invalid JSON parsing
        return fallback_plan
