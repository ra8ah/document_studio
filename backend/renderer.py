"""Currency formatting, totals and document-type metadata.

PDF output is produced client-side by the browser's native print engine
(see frontend/src/styles/print.css); there is no server-side HTML renderer.
"""

CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "AED": "AED\u00a0", "INR": "\u20b9",
    "CAD": "C$", "AUD": "A$", "SGD": "S$", "JPY": "\u00a5", "CHF": "CHF\u00a0",
    "SAR": "SAR\u00a0", "ZAR": "R", "NZD": "NZ$",
}


def _indian_group(intpart: str) -> str:
    if len(intpart) <= 3:
        return intpart
    last3 = intpart[-3:]
    rest = intpart[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return ",".join(parts) + "," + last3


def fmt_money(amount, currency="USD") -> str:
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        amount = 0.0
    sym = CURRENCY_SYMBOLS.get(currency, (currency + " ") if currency else "")
    decimals = 0 if currency == "JPY" else 2
    neg = amount < 0
    amount = abs(round(amount, decimals))
    if decimals == 0:
        intpart = f"{int(amount)}"
        frac = ""
    else:
        s = f"{amount:.2f}"
        intpart, frac = s.split(".")
        frac = "." + frac
    if currency == "INR":
        intpart = _indian_group(intpart)
    else:
        intpart = f"{int(intpart):,}"
    return f"{'-' if neg else ''}{sym}{intpart}{frac}"


def compute_totals(doc: dict):
    items = doc.get("line_items", []) or []
    subtotal = sum((float(i.get("qty", 0) or 0) * float(i.get("rate", 0) or 0)) for i in items)
    disc = doc.get("discount") or {}
    tax = doc.get("tax") or {}
    discount_amt = 0.0
    if disc.get("enabled"):
        v = float(disc.get("value", 0) or 0)
        discount_amt = subtotal * v / 100 if disc.get("mode") == "percent" else v
    taxed_base = subtotal - discount_amt
    tax_amt = 0.0
    if tax.get("enabled"):
        v = float(tax.get("value", 0) or 0)
        tax_amt = taxed_base * v / 100 if tax.get("mode") == "percent" else v
    total = taxed_base + tax_amt
    return {"subtotal": subtotal, "discount": discount_amt, "tax": tax_amt, "total": total}


TYPE_META = {
    "invoice": {"label": "Invoice", "layout": "financial"},
    "quotation": {"label": "Quotation", "layout": "financial"},
    "receipt": {"label": "Receipt", "layout": "financial"},
    "proposal": {"label": "Proposal", "layout": "content"},
    "statement_of_work": {"label": "Statement of Work", "layout": "content"},
    "service_agreement": {"label": "Service Agreement", "layout": "content"},
    "nda": {"label": "Non-Disclosure Agreement", "layout": "content"},
    "project_status": {"label": "Project Status", "layout": "content"},
    "maintenance_plan": {"label": "Maintenance & Support", "layout": "content"},
    "welcome_doc": {"label": "Welcome", "layout": "content"},
    "thank_you_doc": {"label": "Thank You", "layout": "content"},
    "letterhead": {"label": "Letterhead", "layout": "letterhead"},
    "expense_report": {"label": "Expense Report", "layout": "financial"},
}
