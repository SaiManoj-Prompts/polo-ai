# Polo AI — Think. Browse. Execute.

Polo AI is a local-first research assistant. It accepts natural-language tasks, creates a research plan via an optional local Ollama model (with a built-in non-Ollama fallback), performs safe public-web research, filters results for relevance, saves task history locally, and generates a downloadable Markdown report with source links.

## Why Polo AI?

Polo AI is designed as a transparent local-first research workflow:
it shows the research plan, validates search queries, preserves source
links, and reports insufficient evidence honestly instead of presenting
unsupported conclusions.

## Main Features

* **Streamlit Dashboard:** Clean UI with visible progress stages and a task checklist.
* **Local AI Planner with Fallback:** Uses Ollama locally to generate plans and search queries, seamlessly falling back to a default plan if Ollama is unavailable.
* **AI-Guided Search Strategies:** Uses validated keyword extraction and categorization.
* **Safe Public Browser Research:** Uses Playwright for headless, read-only data retrieval across sources like Mojeek, Wikipedia, GitHub, and arXiv.
* **Relevance Filtering:** Enforces keyword thresholds, filters noise, and ensures findings match the query.
* **USAJobs & Indeed Career-Query Support:** Specialized scraping and formatting logic for career/internship searches.
* **SQLite Task History:** Saves past research tasks and findings locally in `polo_ai.db`.
* **Structured Reports:** Generates structured Markdown and JSON reports with source links.
* **Report Download:** Download final reports directly from the UI.
* **Honest Insufficient-Results Handling:** Gracefully alerts the user if not enough relevant data is found.

## How it Works

**User Task** -> **Planner** -> **Validated Queries** -> **Public-Source Search** -> **Relevance Checks** -> **Findings** -> **SQLite History** -> **Report**

## Technology Stack

Python, Streamlit, Playwright, SQLite, Ollama, and Requests.

## Local Setup Instructions (Windows)

1. Clone the repository:
   ```cmd
   git clone https://github.com/SaiManoj-Prompts/polo-ai.git
   cd polo-ai
   ```

2. Create and activate a virtual environment:
   ```cmd
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. Install dependencies:
   ```cmd
   pip install -r requirements.txt
   ```

4. Install the Playwright browser (specifically Chromium):
   ```cmd
   python -m playwright install chromium
   ```

5. *(Optional)* Install and run Ollama with the configured model (`llama3.2`):
   ```cmd
   ollama run llama3.2
   ```
   *Note: Ollama is optional. If not running, Polo AI will automatically use its built-in fallback plan.*

6. Start the application:
   ```cmd
   streamlit run app.py
   ```

## Example Tasks

* "Government internships"
* "Compare open-source AI agent frameworks"
* "What is the capital of France?"

## Safety and Limitations

* Polo AI interacts strictly with public pages.
* It does **not** log in to services, submit forms, apply for jobs, bypass CAPTCHAs, or use paid APIs.
* It does not guarantee complete or perfectly current search results.
* It prioritizes accuracy and safety, showing an honest "insufficient-results" message when applicable rather than hallucinating answers.

## Project Structure

* `app.py` (Main Streamlit interface and application flow)
* `planner.py` (Ollama integration, prompt generation, and fallback logic)
* `browser_controller.py` (Playwright web scraper, safe-browsing rules, and search sources)
* `report_generator.py` (Markdown and JSON output formatting)
* `db_manager.py` (SQLite database initialization and history handling)
* `requirements.txt` (Python dependencies)

## Screenshots

*Screenshots will be added later.*
* **Dashboard View:** The main Streamlit dashboard showing the task input area and progress checklist.
* **Report View:** The completed research report view with download buttons and task history.
