import streamlit as st

# ── Page config ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Polo AI",
    page_icon="🐎",
    layout="wide",
)

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

execute_clicked = st.button("🚀 Execute Task", use_container_width=True)

st.divider()

# ── Current Task ─────────────────────────────────────────────────────────
st.subheader("📌 Current Task")

if execute_clicked:
    if user_input.strip():
        st.success(user_input.strip())
    else:
        st.warning("Please enter a task above to get started.")
else:
    st.info("Enter a research task above and click **Execute Task** to begin.")

st.divider()

# ── Placeholder sections ────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("📋 Task Progress")
    st.info("Nothing here yet.")

with col2:
    st.subheader("📄 Research Findings")
    st.info("Nothing here yet.")

with col3:
    st.subheader("📚 Task History")
    st.info("Nothing here yet.")
