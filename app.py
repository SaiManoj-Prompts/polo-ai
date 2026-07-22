import time
import streamlit as st
from browser_controller import search_and_collect
import db_manager
from report_generator import generate_report
import planner

# ── Page config ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Polo AI",
    page_icon="🐎",
    layout="wide",
)

# Ensure DB is initialized
db_manager.init_db()

# ── Session state defaults ──────────────────────────────────────────────
if "task" not in st.session_state:
    st.session_state.task = ""
if "step_index" not in st.session_state:
    st.session_state.step_index = -1  # -1 = not started
if "running" not in st.session_state:
    st.session_state.running = False
if "findings" not in st.session_state:
    st.session_state.findings = []
if "ai_plan" not in st.session_state:
    st.session_state.ai_plan = None

# The six demo research steps
STEPS = [
    ("🧠", "Understanding your request"),
    ("📝", "Creating a research plan"),
    ("🔍", "Searching public sources"),
    ("📖", "Reading webpages"),
    ("🗂️", "Organizing findings"),
    ("📊", "Preparing report"),
]

# ── Title & tagline ─────────────────────────────────────────────────────
st.title("🐎 Polo AI")
st.markdown("#### *Think. Browse. Execute.*")
st.divider()

# ── Task input ───────────────────────────────────────────────────────────
user_input = st.text_area(
    "What would you like Polo AI to research?",
    height=120,
    placeholder="e.g. Compare the latest electric-vehicle battery technologies…",
)

# ── Buttons: Execute & Reset side by side ────────────────────────────────
btn_col1, btn_col2 = st.columns([3, 1])

with btn_col1:
    execute_clicked = st.button("🚀 Execute Task", use_container_width=True)

with btn_col2:
    reset_clicked = st.button("🔄 Reset", use_container_width=True)

# ── Handle Reset ─────────────────────────────────────────────────────────
if reset_clicked:
    st.session_state.task = ""
    st.session_state.step_index = -1
    st.session_state.running = False
    st.session_state.findings = []
    st.session_state.ai_plan = None
    st.rerun()

# ── Handle Execute ───────────────────────────────────────────────────────
if execute_clicked:
    if user_input.strip():
        st.session_state.task = user_input.strip()
        st.session_state.running = True
        st.session_state.step_index = 0
    else:
        st.session_state.task = ""
        st.session_state.step_index = -1
        st.session_state.running = False
        st.session_state.ai_plan = None

st.divider()

# ── Current Task ─────────────────────────────────────────────────────────
st.subheader("📌 Current Task")

if execute_clicked and not user_input.strip():
    st.warning("Please enter a task above to get started.")
elif st.session_state.task:
    st.success(st.session_state.task)
    
    if st.session_state.get("ai_plan"):
        ai_data = st.session_state.ai_plan
        if isinstance(ai_data, list):
            plan_steps = ai_data
            queries = []
        else:
            plan_steps = ai_data.get("plan", [])
            category = ai_data.get("category", "unknown")
            queries = ai_data.get("queries", [])
            source = ai_data.get("source", "Unknown")

        with st.expander("🧠 AI Research Plan", expanded=True):
            for i, step in enumerate(plan_steps, 1):
                st.markdown(f"{i}. {step}")
                
        if queries:
            with st.expander("🔍 Search strategy used", expanded=True):
                st.markdown(f"**Category:** `{category}`")
                source_color = "green" if source == "Ollama" else "orange"
                st.markdown(f"**Source:** :{source_color}[{source}]")
                st.markdown("**Queries:**")
                for q in queries:
                    st.markdown(f"- {q}")
else:
    st.info("Enter a research task above and click **Execute Task** to begin.")

st.divider()

# ── Progress animation ──────────────────────────────────────────────────
# This runs once right after the user clicks Execute with valid text.
# It uses st.empty() containers so each step updates in place.

if st.session_state.running:
    if not st.session_state.get("ai_plan"):
        with st.spinner("🧠 AI is formulating a research plan..."):
            st.session_state.ai_plan = planner.generate_plan(st.session_state.task)
            st.rerun()

    progress_bar = st.progress(0, text="Starting research…")
    step_container = st.empty()

    for i, (emoji, label) in enumerate(STEPS):
        # Build the step list with current status
        lines = []
        for j, (e, lbl) in enumerate(STEPS):
            if j < i:
                lines.append(f"✅  ~~{lbl}~~ — done")
            elif j == i:
                lines.append(f"⏳  **{e} {lbl}…**")
            else:
                lines.append(f"⬜  {lbl}")

        step_container.markdown("\n\n".join(lines))
        progress_bar.progress(
            int((i / len(STEPS)) * 100),
            text=f"{emoji} {label}…",
        )

        # Steps 3 & 4 (index 2 & 3) do real browsing;
        # all other steps use demo sleep.
        if i == 2:  # "Searching public sources"
            ai_data = st.session_state.get("ai_plan", {})
            if isinstance(ai_data, dict) and ai_data.get("queries"):
                st.session_state.findings = search_and_collect(
                    st.session_state.task,
                    queries=ai_data["queries"],
                    category=ai_data.get("category")
                )
            else:
                st.session_state.findings = search_and_collect(
                    st.session_state.task
                )
        elif i == 3:  # "Reading webpages" — already done above
            time.sleep(0.5)  # brief pause for visual flow
        else:
            time.sleep(1.5)

        st.session_state.step_index = i

    # Final state: all done
    final_lines = [f"✅  ~~{lbl}~~ — done" for (_, lbl) in STEPS]
    step_container.markdown("\n\n".join(final_lines))
    progress_bar.progress(100, text="✅ Research complete!")

    # Save to database
    db_manager.save_task(
        query=st.session_state.task,
        status="Completed",
        findings=st.session_state.findings
    )

    st.session_state.running = False
    st.session_state.step_index = len(STEPS) - 1

    st.balloons()

st.divider()

# ── Placeholder sections ────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("📋 Task Progress")
    if st.session_state.step_index >= 0 and not st.session_state.running:
        # Show final completed checklist
        for emoji, label in STEPS:
            if STEPS.index((emoji, label)) <= st.session_state.step_index:
                st.markdown(f"✅  {label}")
            else:
                st.markdown(f"⬜  {label}")
    else:
        st.info("Nothing here yet.")

with col2:
    st.subheader("📄 Research Findings")
    if st.session_state.findings:
        for idx, finding in enumerate(st.session_state.findings, 1):
            if not finding.get('url') or finding.get('title') == 'Insufficient results':
                st.warning("⚠️ No relevant sources found for this query. Try rephrasing your request or ask about a different topic.")
            else:
                st.markdown(f"**{idx}. {finding['title']}**")
                st.markdown(f"🔗 [{finding['url']}]({finding['url']})")
                st.caption(finding["snippet"])
                if idx < len(st.session_state.findings):
                    st.markdown("---")
    else:
        st.info("Nothing here yet.")

with col3:
    st.subheader("📚 Task History")
    history = db_manager.get_all_tasks()
    if history:
        for task in history:
            query_preview = task['query'][:30] + ('...' if len(task['query']) > 30 else '')
            with st.expander(f"Task: {query_preview} ({task['created_at']})"):
                st.write(f"**Status:** {task['status']}")
                if task.get('findings'):
                    for f in task['findings']:
                        if not f.get('url') or f.get('title') == 'Insufficient results':
                            st.warning("⚠️ No relevant sources found for this query.")
                        else:
                            st.markdown(f"- [{f['title']}]({f['url']})")
                else:
                    st.write("No findings.")
    else:
        st.info("Nothing here yet.")

st.divider()

# ── Final Research Report ───────────────────────────────────────────────
if st.session_state.step_index >= 0 and not st.session_state.running:
    st.header("📄 Final Research Report")
    md_report, json_report = generate_report(st.session_state.task, st.session_state.findings)
    
    st.markdown(md_report)
    
    st.markdown("### Download Report")
    dl_col1, dl_col2 = st.columns(2)
    with dl_col1:
        st.download_button(
            label="⬇️ Download Markdown",
            data=md_report,
            file_name="research_report.md",
            mime="text/markdown",
            use_container_width=True
        )
    with dl_col2:
        st.download_button(
            label="⬇️ Download JSON",
            data=json_report,
            file_name="research_report.json",
            mime="application/json",
            use_container_width=True
        )
