import json
from datetime import date

import openai

from config import MODEL, MAX_TOKENS, MAX_SEARCH_TURNS_PER_AGENT, get_api_key
from prompts import (
    RERA_SYSTEM, LEGAL_SYSTEM, LOCALITY_SYSTEM, REPORT_SYSTEM, REPAIR_SYSTEM,
)

FIELDS = [
    ("project_name", "Project / property name"),
    ("promoter", "Builder / promoter"),
    ("rera_number", "RERA number given by user"),
    ("state", "State"),
    ("city", "City"),
    ("locality", "Locality / micro-market"),
    ("property_type", "Property type"),
    ("construction_status", "Construction status"),
    ("asking_price_inr", "Asking price (INR)"),
    ("size_sqft", "Size (sq ft)"),
    ("purpose", "Investor's purpose"),
    ("notes", "Extra notes from user"),
]


def _property_text(prop):
    lines = []
    for key, label in FIELDS:
        value = prop.get(key)
        if value in (None, "", 0, 0.0):
            value = "Not provided"
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def _client():
    api_key = get_api_key()
    if not api_key or api_key == "paste-your-key-here":
        raise ValueError(
            "Missing XAI_API_KEY. Add your Grok API key to "
            ".streamlit/secrets.toml or the XAI_API_KEY environment variable."
        )
    return openai.OpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1",
        max_retries=5,
        timeout=600.0,
    )


def call_grok(system, user, use_search=True):
    """Send one request to Grok and return the text answer."""
    client = _client()
    kwargs = {
        "model": MODEL,
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_output_tokens": MAX_TOKENS,
        "store": False,
    }
    if use_search:
        kwargs["tools"] = [{"type": "web_search"}]
        kwargs["extra_body"] = {"max_turns": MAX_SEARCH_TURNS_PER_AGENT}

    response = client.responses.create(**kwargs)
    return response.output_text.strip()


def extract_json(text):
    """Find and parse the JSON object inside the AI's answer."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def run_json_agent(system, user, use_search=True):
    """Run an agent that must answer in JSON. Never crashes; returns {'error': ...} on failure."""
    try:
        text = call_grok(system, user, use_search)
        data = extract_json(text)
        if data is None and text.strip():
            fixed = call_grok(REPAIR_SYSTEM, text[-12000:], use_search=False)
            data = extract_json(fixed)
        if data is None or data.get("parse_failed"):
            return {"error": "The agent's answer could not be read. Please run again."}
        return data
    except ValueError as e:
        return {"error": str(e)}
    except openai.AuthenticationError:
        return {"error": "Grok API authentication failed. Check XAI_API_KEY in your secrets."}
    except openai.RateLimitError:
        return {"error": "Rate limit reached. Wait one minute and run again."}
    except openai.APIError as e:
        return {"error": f"Grok API request failed: {str(e)[:300]}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)[:300]}"}


def run_rera_agent(prop):
    user = (
        f"Today's date: {date.today().isoformat()}\n\n"
        f"Property details:\n{_property_text(prop)}\n\n"
        "Task: verify this project's RERA registration and return the JSON."
    )
    return run_json_agent(RERA_SYSTEM, user, use_search=True)


def run_legal_agent(prop, documents):
    if documents:
        doc_text = "\n\n".join(
            f"=== DOCUMENT: {d['name']} ===\n{d['text']}" for d in documents
        )
    else:
        doc_text = "NO DOCUMENTS WERE UPLOADED."
    user = (
        f"Today's date: {date.today().isoformat()}\n\n"
        f"Property details:\n{_property_text(prop)}\n\n"
        f"Uploaded documents:\n{doc_text}\n\n"
        "Task: flag title and legal risks and return the JSON."
    )
    return run_json_agent(LEGAL_SYSTEM, user, use_search=True)


def run_locality_agent(prop):
    user = (
        f"Today's date: {date.today().isoformat()}\n\n"
        f"Property details:\n{_property_text(prop)}\n\n"
        "Task: assess this locality as an investment and return the JSON."
    )
    return run_json_agent(LOCALITY_SYSTEM, user, use_search=True)


def run_report_agent(prop, rera, legal, locality, decision):
    payload = {
        "property": prop,
        "rera_findings": rera,
        "legal_findings": legal,
        "locality_findings": locality,
        "FINAL_VERDICT": decision,
    }
    user = "Write the report from this data:\n\n" + json.dumps(payload, indent=2, default=str)
    try:
        return call_grok(REPORT_SYSTEM, user, use_search=False)
    except Exception as e:
        return f"The report could not be written: {str(e)[:300]}"