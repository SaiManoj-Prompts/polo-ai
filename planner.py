import re
import requests
import time
from typing import List

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2"

def generate_plan(query: str) -> List[str]:
    """
    Generates a 3 to 6 step research plan using local Ollama.
    Returns a fallback plan if Ollama is unavailable or fails.
    """
    start_time = time.time()
    fallback_plan = [
        "Define query terms and core keywords",
        "Search web sources and extract raw text",
        "Filter out irrelevant navigation noise",
        "Synthesize the findings into a report"
    ]

    prompt = f"""You are an expert research planner.
The user wants to research the following query: "{query}"

List 3 to 6 research steps as a plain numbered list. One step per line.
Format each line exactly as:
1. Step description
2. Step description

Do not add any introduction, explanation, or JSON - just the numbered list."""

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        response_text = data.get("response", "").strip()
        print(f"[DEBUG] Raw response from Ollama:\n{response_text}")
        
        # Parse numbered lines: match lines starting with a digit followed by a period
        matches = re.findall(r'^\s*\d+\.\s+(.+)', response_text, re.MULTILINE)
        
        # Strip whitespace from each extracted step
        steps = [step.strip() for step in matches if step.strip()]
        print(f"[DEBUG] Parsed {len(steps)} steps from response: {steps}")

        if 3 <= len(steps) <= 8:
            elapsed = round(time.time() - start_time, 2)
            print(f"[DEBUG] Successfully generated plan via Ollama model ({MODEL_NAME}) in {elapsed}s")
            return steps
        else:
            elapsed = round(time.time() - start_time, 2)
            print(f"[DEBUG] Parsed {len(steps)} steps (expected 3-8) after {elapsed}s. Using fallback plan.")
            return fallback_plan

    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        print(f"[DEBUG] Ollama request failed after {elapsed}s: {type(e).__name__} - {e}")
        print("[DEBUG] Using fallback plan.")
        return fallback_plan
