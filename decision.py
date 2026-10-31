# The verdict is decided here by fixed rules, NOT by the AI.


def to_float(value):
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.replace(",", "").replace("₹", "").strip()
        return float(value)
    except (ValueError, TypeError):
        return None


def _yield_score(yield_percent):
    """Convert gross rental yield % into a 0-10 score (Indian residential yields are low)."""
    if yield_percent < 2:
        return 3.0
    if yield_percent < 3:
        return 5.0
    if yield_percent < 4:
        return 7.0
    if yield_percent < 5:
        return 8.5
    return 9.5


def enrich_locality(locality, asking_price, size_sqft):
    """Adds computed yield, overall score and price-vs-market to the locality result."""
    if locality.get("error"):
        return locality

    price = to_float(locality.get("typical_price_per_sqft_inr"))
    rent = to_float(locality.get("typical_monthly_rent_per_sqft_inr"))

    gross_yield = None
    if price and rent and price > 0:
        gross_yield = round(rent * 12 / price * 100, 2)
    locality["computed_gross_yield_percent"] = gross_yield

    infra = to_float(locality.get("infrastructure_score"))
    trend = to_float(locality.get("price_trend_score"))
    yield_score = _yield_score(gross_yield) if gross_yield is not None else None
    locality["rental_yield_score"] = yield_score

    parts = [(infra, 0.35), (trend, 0.35), (yield_score, 0.30)]
    valid = [(s, w) for s, w in parts if s is not None]
    if valid:
        total_weight = sum(w for _, w in valid)
        locality["overall_locality_score"] = round(
            sum(s * w for s, w in valid) / total_weight, 1
        )
    else:
        locality["overall_locality_score"] = None

    ask = to_float(asking_price)
    size = to_float(size_sqft)
    asking_psf = None
    premium = None
    if ask and size and size > 0:
        asking_psf = round(ask / size)
        if price and price > 0:
            premium = round((asking_psf - price) / price * 100, 1)
    locality["asking_price_per_sqft_inr"] = asking_psf
    locality["price_premium_vs_market_percent"] = premium
    return locality


def decide(rera, legal, locality, documents_count):
    """Returns {'verdict': ..., 'reasons': [...]}"""
    # 1. If any agent failed, we cannot judge.
    for name, result in (("RERA", rera), ("Legal", legal), ("Locality", locality)):
        if result.get("error"):
            return {
                "verdict": "NOT SURE",
                "reasons": [f"The {name} check could not be completed: {result['error']}"],
            }

    status = str(rera.get("status", "Unclear")).strip()
    flags = [f for f in (legal.get("risk_flags") or []) if isinstance(f, dict)]
    high = [f for f in flags if str(f.get("severity", "")).lower() == "high"]
    medium = [f for f in flags if str(f.get("severity", "")).lower() == "medium"]

    # 2. Hard NO-GO rules
    if status in ("Expired", "Revoked"):
        return {
            "verdict": "NO-GO",
            "reasons": [f"RERA registration is {status.lower()}. Do not invest."],
        }
    if high:
        return {
            "verdict": "NO-GO",
            "reasons": ["High-severity risk found: " + str(f.get("issue", "")) for f in high],
        }

    # 3. "I'm not sure" rules
    unsure = []
    if status != "Verified":
        unsure.append(
            f"RERA registration could not be verified (status: {status}). "
            "Do not pay any money until you verify it on the official state RERA portal."
        )
    for name, result in (("RERA", rera), ("Legal", legal), ("Locality", locality)):
        if str(result.get("confidence", "Low")).strip().lower() == "low":
            unsure.append(f"The {name} agent has low confidence in its findings.")
    score = locality.get("overall_locality_score")
    if score is None:
        unsure.append("Not enough data to score the locality.")
    if unsure:
        return {"verdict": "NOT SURE", "reasons": unsure}

    # 4. Score-based verdict, with caps
    if score < 5:
        return {
            "verdict": "NO-GO",
            "reasons": [f"Locality investment score is weak ({score}/10)."],
        }

    verdict = "GO" if score >= 7 else "CONDITIONAL GO"
    reasons = [f"RERA verified. Locality score {score}/10. No high-severity legal risk found."]

    if documents_count == 0:
        verdict = "CONDITIONAL GO"
        reasons.append("No documents were uploaded, so title was NOT checked. Get a lawyer to review.")
    if medium:
        verdict = "CONDITIONAL GO"
        reasons.append(f"{len(medium)} medium-severity risk(s) need review before buying.")
    premium = locality.get("price_premium_vs_market_percent")
    if premium is not None and premium > 15:
        verdict = "CONDITIONAL GO"
        reasons.append(f"Asking price is about {premium}% above the typical market rate.")
    if any(
        str(r.get("confidence", "")).strip().lower() == "medium"
        for r in (rera, legal, locality)
    ):
        verdict = "CONDITIONAL GO"
        reasons.append("At least one agent has only medium confidence.")

    return {"verdict": verdict, "reasons": reasons}