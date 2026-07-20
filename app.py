import time
import streamlit as st
from browser_controller import search_and_collect

# ── Page config ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Polo AI",
    page_icon="🐎",
    layout="wide",
)

# ── Session state defaults ──────────────────────────────────────────────
if "task" not in st.session_state:
    st.session_state.task = ""
if "step_index" not in st.session_state:
    st.session_state.step_index = -1  # -1 = not started
if "running" not in st.session_state:
    st.session_state.running = False
if "findings" not in st.session_state:
    st.session_state.findings = []

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

st.divider()

# ── Current Task ─────────────────────────────────────────────────────────
st.subheader("📌 Current Task")

if execute_clicked and not user_input.strip():
    st.warning("Please enter a task above to get started.")
elif st.session_state.task:
    st.success(st.session_state.task)
else:
    st.info("Enter a research task above and click **Execute Task** to begin.")

st.divider()

# ── Progress animation ──────────────────────────────────────────────────
# This runs once right after the user clicks Execute with valid text.
# It uses st.empty() containers so each step updates in place.

if st.session_state.running:
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
            st.markdown(f"**{idx}. {finding['title']}**")
            st.markdown(f"🔗 [{finding['url']}]({finding['url']})")
            st.caption(finding["snippet"])
            if idx < len(st.session_state.findings):
                st.markdown("---")
    else:
        st.info("Nothing here yet.")

with col3:
    st.subheader("📚 Task History")
    st.info("Nothing here yet.")
