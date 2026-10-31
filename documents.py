from pypdf import PdfReader
from config import MAX_DOC_CHARS


def extract_text_from_pdfs(uploaded_files):
    """Read text from uploaded PDFs. Returns (documents, warnings)."""
    docs = []
    warnings = []
    total = 0

    for f in uploaded_files or []:
        try:
            reader = PdfReader(f)
            text = ""
            for page in reader.pages:
                text += (page.extract_text() or "") + "\n"
            text = text.strip()
        except Exception as e:
            warnings.append(f"Could not read {f.name}: {e}")
            continue

        if len(text) < 50:
            warnings.append(
                f"{f.name} has no readable text (it may be a scanned image). "
                "It was NOT reviewed. Upload a text-based PDF if possible."
            )
            continue

        remaining = MAX_DOC_CHARS - total
        if remaining <= 0:
            warnings.append(f"{f.name} was skipped because the size limit was reached.")
            continue

        snippet = text[:remaining]
        if len(text) > remaining:
            warnings.append(f"{f.name} was too long, so only the first part was reviewed.")

        docs.append({"name": f.name, "text": snippet})
        total += len(snippet)

    return docs, warnings