import os
import streamlit as st

# The AI model used by all agents.
MODEL = "grok-4.7"

MAX_TOKENS = 4000              # max length of each agent's answer
MAX_SEARCH_TURNS_PER_AGENT = 5 # limits agentic web-search turns per agent
MAX_DOC_CHARS = 30000          # max characters read from uploaded PDFs

# After you create a Google Form for feedback, paste its link between the quotes.
FEEDBACK_FORM_URL = ""


def _secret(name):
    """Read a secret from Streamlit secrets, or from environment variables."""
    try:
        value = st.secrets[name]
    except Exception:
        value = ""
    if value == "paste-your-key-here":
        value = ""
    return value or os.environ.get(name, "")


def get_api_key():
    return _secret("XAI_API_KEY")


def get_app_password():
    return _secret("APP_PASSWORD")