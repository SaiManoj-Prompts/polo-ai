import re
import requests
import time
import json
from typing import Dict, Any

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2"

STOPWORDS = {"the", "and", "how", "what", "is", "a", "an", "of", "in", "for", "to", "with", "on", "at", "by", "from", "or", "as", "it", "be", "are", "was", "were", "been", "has", "have", "had", "do", "does", "did", "but", "not", "so", "if", "its", "my", "that", "this", "which", "who", "when", "where", "why", "can", "will", "should", "would", "could", "most", "more", "very", "just", "about"}
EXPANSION_TERMS = {"jobs", "internships", "careers", "frameworks", "libraries", "documentation", "official", "requirements", "funding", "research", "companies", "applications", "salary", "hiring"}
NON_ANCHOR_TERMS = {
    "open", "source", "best", "latest", "top", "guide", "comparison",
    "compare", "overview", "introduction", "information", "news"
}
BAD_PHRASES = ["ignore previous", "system prompt", "instructions", "jailbreak", "execute", "run command", "delete", "password", "token", "api key", "curl", "powershell", "python code"]
BAD_CHARS = ["{", "}", "[", "]", "```", "\n", "\r", "http", "www.", ".com", ".org"]

def clean_text(item) -> str:
    if not item:
        return ""
    if isinstance(item, str):
        text = item.strip()
    elif isinstance(item, dict):
        parts = []
        for k, v in item.items():
            if not v:
                parts.append(str(k).strip())
            else:
                if str(k).lower() in ['query', 'step', 'description', 'text', 'action']:
                    parts.append(str(v).strip())
                else:
                    parts.append(f"{str(k).strip()}: {str(v).strip()}")
        text = " ".join(parts)
    elif isinstance(item, list):
        text = " ".join(clean_text(i) for i in item)
    else:
        text = str(item).strip()

    text = re.sub(r'^(?i:step\s*\d+[\.\:\)]*\s*|\d+[\.\:\)]\s*)', '', text)
    return text.strip()

def _normalize_query(text: str) -> str:
    return " ".join(re.findall(r'[a-z0-9]+', text.lower()))

def _validate_query(candidate: str, original_task: str) -> bool:
    if len(candidate) > 80:
        return False

    c_lower = candidate.lower()

    for bp in BAD_PHRASES:
        if bp in c_lower:
            return False

    for bc in BAD_CHARS:
        if bc in c_lower:
            return False

    if re.search(r'[^\w\s]{3,}', candidate):
        return False

    cand_tokens = [w for w in re.findall(r'[a-z0-9]+', c_lower) if w not in STOPWORDS]
    if not cand_tokens:
        return False

    if sum(len(w) for w in cand_tokens) < 2:
        return False

    orig_tokens = [w for w in re.findall(r'[a-z0-9]+', original_task.lower()) if w not in STOPWORDS]

    cand_anchor_tokens = [w for w in cand_tokens if w not in NON_ANCHOR_TERMS]
    orig_anchor_tokens = [w for w in orig_tokens if w not in NON_ANCHOR_TERMS]

    shared = set(cand_anchor_tokens).intersection(set(orig_anchor_tokens))
    if len(shared) >= 2:
        return True

    if len(shared) == 1:
        shared_token = list(shared)[0]
        if any(w in EXPANSION_TERMS and w != shared_token for w in cand_tokens):
            return True

    return False

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

        cleaned_steps = [clean_text(s) for s in steps]
        steps = [s for s in cleaned_steps if s]

        # Validate queries
        raw_queries = parsed.get("queries", [])
        if not isinstance(raw_queries, list):
            raise ValueError("queries must be a list")

        orig_norm = _normalize_query(query)
        ollama_queries = []
        for q in raw_queries:
            if len(ollama_queries) >= 2:
                break

            q_str = clean_text(q).strip('"\'')
            if _validate_query(q_str, query):
                q_norm = _normalize_query(q_str)
                if q_norm == orig_norm:
                    continue
                if not any(q_norm == _normalize_query(existing) for existing in ollama_queries):
                    ollama_queries.append(q_str)

        validated_queries = ollama_queries + [query]

        # Validate category
        category = str(parsed.get("category", "")).strip().lower()
        if category not in ["career", "technical research", "general research", "unknown"]:
            category = "unknown"

        elapsed = round(time.time() - start_time, 2)
        print(f"[DEBUG] Successfully generated plan via Ollama model ({MODEL_NAME}) in {elapsed}s")

        source_label = "Ollama"
        if not ollama_queries:
            source_label = "Ollama (no valid query expansions)"

        return {
            "plan": steps,
            "queries": validated_queries,
            "category": category,
            "source": source_label
        }

    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        print(f"[DEBUG] Ollama request failed after {elapsed}s: {type(e).__name__} - {e}")
        print("[DEBUG] Using fallback plan.")
        return fallback_response
