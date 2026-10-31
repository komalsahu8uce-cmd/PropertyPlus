import time

import streamlit as st

from config import FEEDBACK_FORM_URL, get_api_key, get_app_password
from documents import extract_text_from_pdfs
from agents import (
    run_rera_agent, run_legal_agent, run_locality_agent, run_report_agent,
)
from decision import enrich_locality, decide

st.set_page_config(page_title="Property Due-Diligence Agent", page_icon="🏠", layout="wide")

# ---------- Access code gate (protects your API credits) ----------
app_password = get_app_password()
if app_password:
    if "authed" not in st.session_state:
        st.session_state.authed = False
    if not st.session_state.authed:
        st.title("🏠 Property Due-Diligence Agent")
        entered = st.text_input("Enter access code", type="password")
        if st.button("Unlock"):
            if entered == app_password:
                st.session_state.authed = True
                st.rerun()
            else:
                st.error("Wrong access code.")
        st.stop()


# ---------- Helper functions to display results ----------
def fmt(value, suffix=""):
    if value is None or value == "":
        return "Unknown"
    return f"{value}{suffix}"


def show_evidence(items):
    if not items:
        st.caption("No sources listed.")
        return
    for e in items:
        if not isinstance(e, dict):
            continue
        claim = e.get("claim", "")
        source = e.get("source", "source")
        url = str(e.get("url", "") or "")
        if url.startswith("http"):
            st.markdown(f"- {claim} — [{source}]({url})")
        else:
            st.markdown(f"- {claim} — {source}")


def show_confidence(result):
    st.markdown(f"**Confidence:** {result.get('confidence', 'Low')}")
    notes = result.get("uncertainty_notes")
    if notes:
        st.info(f"What the agent is not sure about: {notes}")


def show_rera(rera):
    if rera.get("error"):
        st.error(rera["error"])
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Status", fmt(rera.get("status")))
    c2.metric("Valid till", fmt(rera.get("registration_valid_till")))
    c3.metric("RERA number", fmt(rera.get("rera_number")))
    st.markdown(f"**Promoter:** {fmt(rera.get('promoter_name'))}")
    st.markdown(f"**Registered project name:** {fmt(rera.get('project_name_registered'))}")
    st.markdown(f"**Declared completion date:** {fmt(rera.get('declared_completion_date'))}")
    complaints = rera.get("complaints_or_penalties") or []
    if complaints:
        st.markdown("**Complaints / penalties found:**")
        for c in complaints:
            st.markdown(f"- {c}")
    st.markdown("**Sources**")
    show_evidence(rera.get("evidence"))
    show_confidence(rera)


def show_legal(legal):
    if legal.get("error"):
        st.error(legal["error"])
        return
    icons = {"high": "🔴", "medium": "🟠", "low": "🟡"}
    flags = [f for f in (legal.get("risk_flags") or []) if isinstance(f, dict)]
    if not flags:
        st.success("No specific risk flags were found. This does NOT mean the title is clean.")
    for f in flags:
        sev = str(f.get("severity", "")).lower()
        st.markdown(
            f"{icons.get(sev, '⚪')} **{f.get('issue', '')}** "
            f"({f.get('severity', '')} · {f.get('category', '')})"
        )
        st.markdown(f"   Evidence: {f.get('evidence', '')}")
        st.markdown(f"   Recommended action: {f.get('recommended_action', '')}")
    reviewed = legal.get("documents_reviewed") or []
    missing = legal.get("documents_missing") or []
    st.markdown("**Documents reviewed:** " + (", ".join(reviewed) if reviewed else "None"))
    if missing:
        st.markdown("**Documents still needed:**")
        for m in missing:
            st.markdown(f"- {m}")
    st.markdown("**Sources**")
    show_evidence(legal.get("evidence"))
    show_confidence(legal)


def show_locality(loc):
    if loc.get("error"):
        st.error(loc["error"])
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Overall score", fmt(loc.get("overall_locality_score"), "/10"))
    c2.metric("Infrastructure", fmt(loc.get("infrastructure_score"), "/10"))
    c3.metric("Price trend", fmt(loc.get("price_trend_score"), "/10"))
    c4.metric("Rental yield score", fmt(loc.get("rental_yield_score"), "/10"))
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Market price / sq ft", fmt(loc.get("typical_price_per_sqft_inr"), " ₹"))
    d2.metric("Gross rental yield", fmt(loc.get("computed_gross_yield_percent"), "%"))
    d3.metric("Price change (12m)", fmt(loc.get("price_change_12m_percent"), "%"))
    d4.metric("Your price vs market", fmt(loc.get("price_premium_vs_market_percent"), "%"))
    if loc.get("infrastructure_highlights"):
        st.markdown("**Infrastructure highlights**")
        for h in loc["infrastructure_highlights"]:
            st.markdown(f"- {h}")
    if loc.get("infrastructure_concerns"):
        st.markdown("**Concerns**")
        for h in loc["infrastructure_concerns"]:
            st.markdown(f"- {h}")
    st.markdown("**Sources**")
    show_evidence(loc.get("evidence"))
    show_confidence(loc)


# ---------- Page ----------
st.title("🏠 Property Due-Diligence Agent")
st.caption("AI-assisted screening for property investors: RERA check, legal risk flags, locality score and a go/no-go report.")

with st.expander("Important: please read"):
    st.markdown(
        "- This is a **screening tool**, not legal, financial or investment advice.\n"
        "- The tool says **NOT SURE** whenever it cannot verify something. Treat that as a stop sign.\n"
        "- Always confirm RERA registration on the official state RERA portal and have a property lawyer review title documents before paying any money.\n"
        "- Do not upload documents containing Aadhaar, PAN or bank account numbers."
    )

with st.form("property_form"):
    left, right = st.columns(2)
    with left:
        project_name = st.text_input("Project / property name *")
        promoter = st.text_input("Builder / promoter name")
        rera_number = st.text_input("RERA number (if you have it)")
        state = st.selectbox(
            "State",
            ["Telangana", "Andhra Pradesh", "Karnataka", "Maharashtra", "Tamil Nadu",
             "Gujarat", "Delhi NCR", "Other"],
        )
        city = st.text_input("City *", value="Hyderabad")
    with right:
        locality = st.text_input("Locality / micro-market *", placeholder="e.g. Kokapet")
        property_type = st.selectbox("Property type", ["Apartment", "Villa", "Plot", "Commercial"])
        construction_status = st.selectbox(
            "Construction status", ["Under construction", "Ready to move", "Resale"]
        )
        asking_price = st.number_input("Total asking price (₹)", min_value=0, step=100000, value=0)
        size_sqft = st.number_input("Size (sq ft)", min_value=0, step=50, value=0)
        purpose = st.selectbox("Your goal", ["Both", "Rental income", "Capital appreciation"])
    notes = st.text_area("Anything else the agents should know (optional)")
    files = st.file_uploader(
        "Upload documents (PDF only): EC, sale deed, approvals, builder agreement",
        type=["pdf"],
        accept_multiple_files=True,
    )
    submitted = st.form_submit_button("Run due diligence", type="primary")

# ---------- Run the agents ----------
if submitted:
    api_key = get_api_key()
    if not api_key or api_key == "paste-your-key-here":
        st.error(
            "Add your Grok API key as XAI_API_KEY in .streamlit/secrets.toml "
            "or set the XAI_API_KEY environment variable before running due diligence."
        )
    elif not project_name.strip() or not city.strip() or not locality.strip():
        st.error("Please fill in Project name, City and Locality.")
    else:
        prop = {
            "project_name": project_name.strip(),
            "promoter": promoter.strip(),
            "rera_number": rera_number.strip(),
            "state": state,
            "city": city.strip(),
            "locality": locality.strip(),
            "property_type": property_type,
            "construction_status": construction_status,
            "asking_price_inr": asking_price,
            "size_sqft": size_sqft,
            "purpose": purpose,
            "notes": notes.strip(),
        }
        start = time.time()
        docs, doc_warnings = extract_text_from_pdfs(files)

        with st.status("Agents are working. This takes 2 to 5 minutes...", expanded=True) as status:
            st.write("🔎 Agent 1 of 4: checking RERA registration...")
            rera = run_rera_agent(prop)
            st.write("⚖️ Agent 2 of 4: checking legal and title risks...")
            legal = run_legal_agent(prop, docs)
            st.write("📍 Agent 3 of 4: scoring the locality...")
            locality_result = run_locality_agent(prop)
            locality_result = enrich_locality(locality_result, asking_price, size_sqft)
            st.write("🧮 Applying decision rules...")
            decision = decide(rera, legal, locality_result, len(docs))
            st.write("📝 Agent 4 of 4: writing the report...")
            report = run_report_agent(prop, rera, legal, locality_result, decision)
            status.update(label="Done", state="complete")

        st.session_state["result"] = {
            "prop": prop,
            "rera": rera,
            "legal": legal,
            "locality": locality_result,
            "decision": decision,
            "report": report,
            "seconds": round(time.time() - start),
            "warnings": doc_warnings,
        }

# ---------- Show results ----------
if "result" in st.session_state:
    r = st.session_state["result"]
    verdict = r["decision"]["verdict"]

    st.divider()
    for w in r["warnings"]:
        st.warning(w)

    banner = {
        "GO": st.success,
        "CONDITIONAL GO": st.warning,
        "NO-GO": st.error,
        "NOT SURE": st.info,
    }.get(verdict, st.info)
    banner(f"### Verdict: {verdict}")
    for reason in r["decision"]["reasons"]:
        st.markdown(f"- {reason}")
    st.caption(f"Completed in {r['seconds']} seconds.")

    tab1, tab2, tab3, tab4 = st.tabs(["📄 Full report", "🔎 RERA", "⚖️ Legal and title", "📍 Locality"])
    with tab1:
        st.markdown(r["report"])
        st.download_button(
            "Download report (.md)",
            data=r["report"],
            file_name="due_diligence_report.md",
            mime="text/markdown",
        )
    with tab2:
        show_rera(r["rera"])
    with tab3:
        show_legal(r["legal"])
    with tab4:
        show_locality(r["locality"])

    st.divider()
    if FEEDBACK_FORM_URL:
        st.link_button("Give feedback on this report (1 minute)", FEEDBACK_FORM_URL)