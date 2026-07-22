import re
import requests
import time
import json
from typing import Dict, Any

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2"

def generate_plan(query: str) -> Dict[str, Any]:
    """
    Generates a 3 to 6 step research plan, 1 to 3 search queries, and a category using local Ollama.
    Returns a fallback plan if Ollama is unavailable or fails.
    """
    start_time = time.time()
    fallback_plan = [
        "Define query terms and core keywords",
        "Search web sources and extract raw text",
        "Filter out irrelevant navigation noise",
        "Synthesize the findings into a report"
    ]
    
    fallback_response = {
        "plan": fallback_plan,
        "queries": [query],
        "category": "unknown",
        "source": "Fallback"
    }

    prompt = f"""You are an expert research planner.
The user wants to research the following query: "{query}"

Output a strict JSON object with exactly these keys:
- "plan": A list of 3 to 6 research steps (strings).
- "queries": A list of 1 to 3 focused search queries to search the web for this task.
- "category": A string, must be exactly one of: "career", "technical research", "general research", or "unknown".

Do not include any explanation or markdown code blocks, just the raw JSON object."""

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        response_text = data.get("response", "").strip()
        print(f"[DEBUG] Raw response from Ollama:\n{response_text}")
        
        parsed = json.loads(response_text)
        
        # Validate plan
        steps = parsed.get("plan", [])
        if not isinstance(steps, list) or not (3 <= len(steps) <= 8):
            raise ValueError(f"Invalid plan steps: {steps}")
        steps = [str(s).strip() for s in steps if str(s).strip()]
        
        # Validate queries
        raw_queries = parsed.get("queries", [])
        if not isinstance(raw_queries, list):
            raise ValueError("queries must be a list")
            
        validated_queries = [query]
        invalid_phrases = ["near me", "around me", "local to me", "in my area"]
        
        for q in raw_queries:
            if len(validated_queries) >= 3:
                break
                
            q_str = str(q).strip().strip('"\'')
            if not q_str or len(q_str) > 60:
                continue
                
            q_lower = q_str.lower()
            if any(phrase in q_lower for phrase in invalid_phrases):
                continue
                
            if not any(v.lower() == q_lower for v in validated_queries):
                validated_queries.append(q_str)
        
        # Validate category
        category = str(parsed.get("category", "")).strip().lower()
        if category not in ["career", "technical research", "general research", "unknown"]:
            category = "unknown"
            
        elapsed = round(time.time() - start_time, 2)
        print(f"[DEBUG] Successfully generated plan via Ollama model ({MODEL_NAME}) in {elapsed}s")
        
        return {
            "plan": steps,
            "queries": validated_queries,
            "category": category,
            "source": "Ollama"
        }

    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        print(f"[DEBUG] Ollama request failed after {elapsed}s: {type(e).__name__} - {e}")
        print("[DEBUG] Using fallback plan.")
        return fallback_response
