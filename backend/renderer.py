"""Currency formatting and document -> print-ready HTML rendering."""
from html import escape

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
}

LEGAL_NOTE_TYPES = {"service_agreement", "nda", "statement_of_work"}


def _page_css(theme: str, page_size: str) -> str:
    if page_size == "Letter":
        pw, ph, ph_min = "216mm", "279mm", "272mm"
    else:
        pw, ph, ph_min = "210mm", "297mm", "290mm"
    if theme == "dark":
        v = {
            "paper": "#1C1815", "text": "#F2ECE0", "dark": "#2C2824", "darktext": "#F2ECE0",
            "accent": "#E0673B", "muted": "#A8A29A", "rule": "rgba(242,236,224,.9)",
            "rule2": "rgba(168,162,154,.4)", "surface": "#252019",
        }
    else:
        v = {
            "paper": "#F2ECE0", "text": "#201C18", "dark": "#2C2824", "darktext": "#F2ECE0",
            "accent": "#C04C20", "muted": "#78746C", "rule": "#201C18",
            "rule2": "rgba(120,116,108,.6)", "surface": "#EAE3D5",
        }
    return f"""
  :root{{
    --paper:{v['paper']}; --text:{v['text']}; --dark:{v['dark']}; --darktext:{v['darktext']};
    --accent:{v['accent']}; --muted:{v['muted']}; --rule:{v['rule']}; --rule2:{v['rule2']}; --surface:{v['surface']};
    --sans:'Poppins','Helvetica Neue',Arial,sans-serif;
    --mono:'IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{background:var(--paper);color:var(--text);font-family:var(--sans);-webkit-print-color-adjust:exact;print-color-adjust:exact}}
  .page{{width:{pw};min-height:{ph_min};margin:0 auto;padding:14mm 19mm 12mm;background:var(--paper);position:relative;display:flex;flex-direction:column}}
  .mono{{font-family:var(--mono);font-size:7.5pt;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-weight:400}}
  .dot{{color:var(--accent)}}
  .mast{{display:flex;justify-content:space-between;align-items:flex-start}}
  .brand{{font-weight:500;font-size:12.5pt;display:flex;align-items:center;gap:6px}}
  .brand i{{font-style:normal;color:var(--accent);font-size:8pt}}
  .brand img{{max-height:40px;max-width:150px;object-fit:contain}}
  .tag{{margin-top:4px}}
  .docno{{font-family:var(--mono);font-size:7.5pt;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);text-align:right}}
  .docno b{{color:var(--accent);font-weight:600}}
  .hero{{display:flex;justify-content:space-between;align-items:flex-end;margin-top:8mm;padding-bottom:5mm;border-bottom:.75pt solid var(--rule)}}
  h1{{font-weight:500;font-size:52pt;line-height:.95;letter-spacing:-.045em}}
  .hero .sub{{font-size:9pt;color:var(--muted);max-width:70mm;text-align:right}}
  .due{{text-align:right}}
  .due .amt{{font-weight:500;font-size:27pt;letter-spacing:-.02em;color:var(--accent);margin-top:2mm}}
  .paidstamp{{display:inline-block;margin-top:3mm;border:1.5pt solid var(--accent);color:var(--accent);font-family:var(--mono);font-size:9pt;letter-spacing:.2em;padding:2mm 4mm;border-radius:2mm;transform:rotate(-4deg)}}
  .parties{{display:grid;grid-template-columns:1.05fr 1.1fr .95fr;gap:8mm;padding:3mm 0 3mm}}
  .parties .mono{{margin-bottom:2.5mm}}
  .parties .name{{font-weight:500;font-size:10.5pt}}
  .parties .sub{{font-size:8pt;color:var(--muted);margin-top:1mm;white-space:pre-line}}
  .parties .val{{font-weight:500;font-size:9pt}}
  .parties .val + .mono{{margin-top:4mm}}
  .project{{display:grid;grid-template-columns:40mm 1fr;align-items:center;padding:2mm 0;border-top:.4pt solid var(--rule2)}}
  .project .v{{font-weight:500;font-size:9pt}}
  table{{width:100%;border-collapse:collapse;margin-top:4mm}}
  th{{font-family:var(--mono);font-weight:400;font-size:7.5pt;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);text-align:right;padding:0 0 2.5mm;border-bottom:.75pt solid var(--rule)}}
  th:first-child,td:first-child{{text-align:left}}
  td{{padding:1.7mm 0 1.5mm;vertical-align:top;border-bottom:.4pt solid var(--rule2);font-size:8.6pt;text-align:right}}
  td:first-child{{padding-right:6mm}}
  td .d{{font-weight:500;font-size:9pt;display:block}}
  td .s{{font-size:7pt;color:var(--muted);margin-top:.8mm;display:block}}
  col.c2{{width:14mm}} col.c3{{width:30mm}} col.c4{{width:32mm}}
  td.amount{{font-weight:500}}
  .sums{{margin-left:auto;width:78mm;margin-top:1mm}}
  .sums .row{{display:flex;justify-content:space-between;align-items:baseline;padding:2mm 0;border-bottom:.4pt solid var(--rule2)}}
  .sums .row:last-child{{border-bottom:0}}
  .sums .v{{font-weight:500;font-size:8.6pt}}
  .total{{margin-top:4mm;background:var(--dark);color:var(--darktext);border-radius:5mm;display:flex;justify-content:space-between;align-items:center;padding:7mm 9mm}}
  .total .mono{{color:var(--darktext)}}
  .total .mono::before{{content:"\\25CF";color:var(--accent);margin-right:3mm}}
  .total .big{{font-weight:500;font-size:33pt;letter-spacing:-.02em}}
  .pay{{display:grid;grid-template-columns:1fr 1fr;gap:10mm;margin-top:4mm}}
  .pay .mono{{margin-bottom:2.5mm}}
  .pay p{{font-size:8.3pt;line-height:1.55;white-space:pre-line}}
  .pay .note{{font-size:7pt;color:var(--muted);margin-top:1.5mm;white-space:pre-line}}
  .meta{{display:grid;grid-template-columns:repeat(3,1fr);gap:8mm;padding:7mm 0 5mm;border-bottom:.4pt solid var(--rule2)}}
  .meta .mono{{margin-bottom:2mm}}
  .meta .val{{font-weight:500;font-size:9.5pt}}
  .section{{padding:6mm 0;border-bottom:.4pt solid var(--rule2)}}
  .section .mono{{margin-bottom:2.5mm}}
  .section h3{{font-weight:500;font-size:14pt;letter-spacing:-.02em;margin-bottom:2.5mm}}
  .section .body{{font-size:9pt;line-height:1.65;white-space:pre-line}}
  .legal{{margin-top:6mm;padding:4mm 5mm;border:.5pt dashed var(--accent);border-radius:3mm;font-size:7.5pt;line-height:1.5;color:var(--muted)}}
  .sign{{display:grid;grid-template-columns:1fr 1fr;gap:12mm;margin-top:12mm}}
  .sign .line{{border-top:.75pt solid var(--rule);padding-top:2mm;font-size:8pt;color:var(--muted)}}
  footer{{margin-top:auto;padding-top:5mm}}
  footer .in{{display:flex;gap:6mm;align-items:baseline;border-top:.75pt solid var(--rule);padding-top:2.5mm;flex-wrap:wrap}}
  footer b{{font-weight:500;font-size:8pt}}
  footer .mono{{letter-spacing:.06em;text-transform:none}}
  @page{{size:{pw} {ph};margin:0}}
"""


def _masthead(d, currency):
    logo = d.get("logo_url", "")
    if logo:
        brand = f'<div class="brand"><img src="{escape(logo)}" alt=""></div>'
    else:
        brand = f'<div class="brand"><i>\u25cf</i><span>{escape(d.get("brand","Your Agency"))}</span></div>'
    return f"""
  <div class="mast">
    <div>
      {brand}
      <div class="mono tag">{escape(d.get('tagline',''))}</div>
    </div>
    <div class="docno">{escape(d.get('label',''))} / <b>{escape(d.get('number',''))}</b></div>
  </div>"""


def _footer(d):
    return f"""
  <footer><div class="in">
    <b>{escape(d.get('footer_line','Thank you for working with us.'))}</b>
    <span class="mono">{escape(d.get('footer_contact',''))}</span>
  </div></footer>"""


def _financial_body(doc, d, currency):
    t = compute_totals(doc)
    is_receipt = doc.get("type") == "receipt"
    rows = ""
    for it in (doc.get("line_items") or []):
        amt = float(it.get("qty", 0) or 0) * float(it.get("rate", 0) or 0)
        rows += f"""<tr>
          <td><span class="d">{escape(str(it.get('description','')))}</span><span class="s">{escape(str(it.get('sub','')))}</span></td>
          <td>{escape(str(it.get('qty','')))}</td>
          <td>{fmt_money(it.get('rate',0),currency)}</td>
          <td class="amount">{fmt_money(amt,currency)}</td></tr>"""

    disc = doc.get("discount") or {}
    tax = doc.get("tax") or {}
    disc_row = ""
    if disc.get("enabled"):
        disc_row = f'<div class="row"><span class="mono">{escape(disc.get("label","Discount"))}</span><span class="v">\u2212 {fmt_money(t["discount"],currency)}</span></div>'
    tax_row = ""
    if tax.get("enabled"):
        tax_row = f'<div class="row"><span class="mono">{escape(tax.get("label","Tax"))}</span><span class="v">{fmt_money(t["tax"],currency)}</span></div>'

    if is_receipt:
        hero_right = f"""<div class="due"><div class="mono">Amount paid</div>
          <div class="amt">{fmt_money(t['total'],currency)}</div>
          <div class="paidstamp">PAID</div></div>"""
        total_label = "Amount paid"
    else:
        hero_right = f"""<div class="due"><div class="mono">Amount due</div>
          <div class="amt">{fmt_money(t['total'],currency)}</div></div>"""
        total_label = "Total due"

    due_block = "" if is_receipt else f"""<div class="mono">Due date</div><div class="val">{escape(d.get('due_date',''))}</div>"""
    pay_second = ""
    if is_receipt:
        pay_second = f"""<div><div class="mono">Payment received</div>
          <p>{escape(d.get('payment_method','Bank transfer'))}</p>
          <p class="note">{escape(d.get('paid_date',''))}</p></div>"""
    else:
        pay_second = f"""<div><div class="mono">Payment terms</div>
          <p>{escape(d.get('payment_terms',''))}</p>
          <p class="note">{escape(d.get('note',''))}</p></div>"""

    return f"""
  <div class="hero">
    <h1>{escape(d.get('label',''))}<span class="dot">.</span></h1>
    {hero_right}
  </div>
  <div class="parties">
    <div><div class="mono">{'Received from' if is_receipt else 'Bill to'}</div>
      <div class="name">{escape(d.get('bill_to_name',''))}</div>
      <div class="sub">{escape(d.get('bill_to_lines',''))}</div></div>
    <div><div class="mono">From</div>
      <div class="name">{escape(d.get('from_name',''))}</div>
      <div class="sub">{escape(d.get('from_lines',''))}</div></div>
    <div><div class="mono">{'Payment date' if is_receipt else 'Issue date'}</div>
      <div class="val">{escape(d.get('issue_date',''))}</div>
      {due_block}</div>
  </div>
  <div class="project">
    <div class="mono">{escape(d.get('reference_label','Project reference'))}</div>
    <div class="v">{escape(d.get('project_reference',''))}</div>
  </div>
  <table><colgroup><col class="c1"><col class="c2"><col class="c3"><col class="c4"></colgroup>
    <thead><tr><th>Description</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead>
    <tbody>{rows}</tbody></table>
  <div class="sums">
    <div class="row"><span class="mono">Subtotal</span><span class="v">{fmt_money(t['subtotal'],currency)}</span></div>
    {disc_row}{tax_row}
  </div>
  <div class="total"><div class="mono">{total_label}</div><div class="big">{fmt_money(t['total'],currency)}</div></div>
  <div class="pay">
    <div><div class="mono">Payment details</div><p>{escape(d.get('payment_details',''))}</p></div>
    {pay_second}
  </div>"""


def _content_body(doc, d, currency):
    dtype = doc.get("type")
    sections_html = ""
    for i, s in enumerate(d.get("sections", []) or []):
        label = s.get("label") or f"{i+1:02d}"
        sections_html += f"""<div class="section">
          <div class="mono">{escape(label)}</div>
          <h3>{escape(s.get('heading',''))}</h3>
          <div class="body">{escape(s.get('body',''))}</div></div>"""

    # optional pricing table for proposal / maintenance
    pricing = ""
    if (doc.get("line_items") or []) and dtype in ("proposal", "maintenance_plan", "statement_of_work"):
        t = compute_totals(doc)
        rows = ""
        for it in doc["line_items"]:
            amt = float(it.get("qty", 0) or 0) * float(it.get("rate", 0) or 0)
            rows += f"""<tr><td><span class="d">{escape(str(it.get('description','')))}</span><span class="s">{escape(str(it.get('sub','')))}</span></td>
              <td>{escape(str(it.get('qty','')))}</td><td>{fmt_money(it.get('rate',0),currency)}</td>
              <td class="amount">{fmt_money(amt,currency)}</td></tr>"""
        pricing = f"""<div class="section"><div class="mono">Pricing</div>
          <table><colgroup><col class="c1"><col class="c2"><col class="c3"><col class="c4"></colgroup>
          <thead><tr><th>Item</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead>
          <tbody>{rows}</tbody></table>
          <div class="total"><div class="mono">Total</div><div class="big">{fmt_money(t['total'],currency)}</div></div></div>"""

    legal = ""
    if dtype in LEGAL_NOTE_TYPES:
        legal = '<div class="legal">This document is a layout scaffold. All legal text must be reviewed and approved by a qualified lawyer before use.</div>'

    sign = ""
    if dtype in ("service_agreement", "nda", "statement_of_work", "proposal"):
        sign = f"""<div class="sign">
          <div class="line">{escape(d.get('sign_left','Service Provider — signature & date'))}</div>
          <div class="line">{escape(d.get('sign_right','Client — signature & date'))}</div></div>"""

    subtitle = f'<div class="sub">{escape(d.get("subtitle",""))}</div>' if d.get("subtitle") else ""
    return f"""
  <div class="hero"><h1>{escape(d.get('label',''))}<span class="dot">.</span></h1>{subtitle}</div>
  <div class="meta">
    <div><div class="mono">Prepared for</div><div class="val">{escape(d.get('bill_to_name',''))}</div></div>
    <div><div class="mono">Prepared by</div><div class="val">{escape(d.get('from_name',''))}</div></div>
    <div><div class="mono">Date</div><div class="val">{escape(d.get('issue_date',''))}</div></div>
  </div>
  {sections_html}{pricing}{legal}{sign}"""


def _letterhead_body(doc, d, currency):
    return f"""
  <div class="hero"><h1>{escape(d.get('brand','Your Agency'))}<span class="dot">.</span></h1>
    <div class="sub">{escape(d.get('subtitle',''))}</div></div>
  <div class="meta">
    <div><div class="mono">Date</div><div class="val">{escape(d.get('issue_date',''))}</div></div>
    <div><div class="mono">Reference</div><div class="val">{escape(d.get('number',''))}</div></div>
    <div><div class="mono">Contact</div><div class="val">{escape(d.get('footer_contact',''))}</div></div>
  </div>
  <div class="section" style="border:0;min-height:120mm"><div class="body">{escape(d.get('letter_body',''))}</div></div>"""


def render_document(doc: dict, page_size: str = "A4") -> str:
    theme = doc.get("theme", "light")
    d = doc.get("data", {}) or {}
    d.setdefault("label", TYPE_META.get(doc.get("type"), {}).get("label", "Document"))
    d.setdefault("number", doc.get("number", ""))
    currency = doc.get("currency", "USD")
    layout = TYPE_META.get(doc.get("type"), {}).get("layout", "content")
    if layout == "financial":
        body = _financial_body(doc, d, currency)
    elif layout == "letterhead":
        body = _letterhead_body(doc, d, currency)
    else:
        body = _content_body(doc, d, currency)
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Poppins:wght@400;500&display=swap" rel="stylesheet">
<style>{_page_css(theme, page_size)}</style></head>
<body><div class="page">{_masthead(d, currency)}{body}{_footer(d)}</div></body></html>"""
