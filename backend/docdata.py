"""Default document content builder — pulls from business profile + client."""
from datetime import datetime, timezone, timedelta
from renderer import TYPE_META


def _profile_from_lines(profile: dict) -> str:
    parts = [profile.get("address", ""), profile.get("email", ""), profile.get("website", "")]
    return "\n".join([p for p in parts if p])


def _payment_details(profile: dict) -> str:
    lines = []
    if profile.get("bank_name"):
        lines.append(profile["bank_name"])
    if profile.get("bank_account"):
        lines.append(f"A/C: {profile['bank_account']}")
    if profile.get("ifsc"):
        lines.append(f"IFSC: {profile['ifsc']}")
    if profile.get("swift"):
        lines.append(f"SWIFT: {profile['swift']}")
    if profile.get("upi"):
        lines.append(f"UPI: {profile['upi']}")
    if profile.get("payment_links"):
        lines.append(profile["payment_links"])
    return "\n".join(lines) or "[Add bank / payment details in Settings]"


CONTENT_SECTIONS = {
    "proposal": [
        ("Overview", "A short summary of the engagement, goals and the problem being solved."),
        ("Scope", "What is included in this engagement and the boundaries of the work."),
        ("Deliverables", "The concrete outputs the client will receive."),
        ("Timeline", "Key phases and expected dates from kickoff to handover."),
        ("Pricing", "Fee structure and payment schedule."),
        ("Terms", "Assumptions, revisions policy and acceptance conditions."),
    ],
    "statement_of_work": [
        ("Background", "Context and objectives for this statement of work."),
        ("Scope of work", "Detailed description of tasks and responsibilities."),
        ("Milestones", "Project milestones with acceptance criteria."),
        ("Assumptions", "Dependencies and assumptions this SOW relies on."),
        ("Acceptance", "How deliverables are reviewed and signed off."),
    ],
    "service_agreement": [
        ("Parties", "This agreement is made between the Service Provider and the Client."),
        ("Services", "Description of the services to be provided."),
        ("Term & termination", "Duration of the agreement and how it may be ended."),
        ("Fees & payment", "Fees, invoicing and payment terms."),
        ("Confidentiality", "Handling of confidential information."),
        ("Liability", "Limitation of liability and warranties."),
    ],
    "nda": [
        ("Purpose", "The parties wish to explore a potential working relationship and may share confidential information."),
        ("Confidential information", "Definition of what is considered confidential."),
        ("Obligations", "How each party must protect the confidential information."),
        ("Exclusions", "Information not covered by this agreement."),
        ("Term", "Duration of the confidentiality obligations."),
    ],
    "project_status": [
        ("Summary", "Overall status and headline update for the reporting period."),
        ("Completed", "Work completed since the last report."),
        ("In progress", "Work currently underway."),
        ("Blockers", "Risks and blockers requiring attention."),
        ("Next steps", "Planned work for the next period."),
    ],
    "maintenance_plan": [
        ("Overview", "Summary of the ongoing maintenance and support arrangement."),
        ("What's included", "Services, monitoring and updates covered by this plan."),
        ("Support tiers & SLA", "Response times and included hours per month."),
        ("Out of scope", "Work billed separately from this plan."),
        ("Terms", "Billing cycle, renewal and cancellation."),
    ],
    "welcome_doc": [
        ("Welcome", "A warm welcome and what to expect working together."),
        ("How we work", "Communication channels, cadence and key contacts."),
        ("Getting started", "First steps and what we need from you."),
        ("Client portal", "[Add client portal access link]"),
        ("Questionnaire", "[Add onboarding questionnaire link]"),
    ],
    "thank_you_doc": [
        ("Thank you", "A note of thanks for the completed project."),
        ("What we delivered", "A short recap of the outcome."),
        ("Staying in touch", "Ongoing maintenance and support options."),
        ("Testimonial", "[Add testimonial / review link] — we'd love your feedback."),
    ],
}


def build_default_data(dtype: str, profile: dict, client: dict, number: str) -> dict:
    meta = TYPE_META.get(dtype, {})
    today = datetime.now(timezone.utc).date()
    due = today + timedelta(days=14)
    profile = profile or {}
    client = client or {}
    d = {
        "brand": profile.get("agency_name", "") or "Your Agency",
        "tagline": profile.get("tagline", ""),
        "logo_url": profile.get("logo_url", ""),
        "label": meta.get("label", "Document"),
        "number": number,
        "from_name": profile.get("agency_name", "") or "Your Agency",
        "from_lines": _profile_from_lines(profile),
        "bill_to_name": client.get("name", "") or client.get("company", "") or "[Client name]",
        "bill_to_lines": "\n".join([x for x in [client.get("company", ""), client.get("address", ""), client.get("email", "")] if x]) or "[Client address / email]",
        "issue_date": today.isoformat(),
        "due_date": due.isoformat(),
        "project_reference": "",
        "reference_label": "Project reference",
        "payment_details": _payment_details(profile),
        "payment_terms": profile.get("default_terms", "Payment due within 14 days of the issue date."),
        "note": profile.get("default_notes", ""),
        "footer_line": "Thank you for working with us.",
        "footer_contact": " · ".join([x for x in [profile.get("website", ""), profile.get("email", "")] if x]),
    }
    layout = meta.get("layout", "content")
    if layout == "content":
        d["sections"] = [{"label": f"{i+1:02d}", "heading": h, "body": b}
                         for i, (h, b) in enumerate(CONTENT_SECTIONS.get(dtype, []))]
        d["subtitle"] = ""
    if layout == "letterhead":
        d["subtitle"] = profile.get("tagline", "")
        d["letter_body"] = ""
    if dtype == "receipt":
        d["payment_method"] = "Bank transfer"
        d["paid_date"] = today.isoformat()
        d["reference_label"] = "Payment for"
    if dtype == "expense_report":
        d["reference_label"] = "Purpose"
        d["billing_note"] = "All expenses listed are business-related and supported by receipts available on request."
        d["payment_terms"] = "Please reimburse within 14 days of approval."
        d["footer_line"] = "Submitted for reimbursement."
    return d


def default_line_items(dtype: str):
    if dtype == "expense_report":
        return [{"description": "Expense item", "sub": "Category \u00b7 date", "qty": 1, "rate": 0}]
    if TYPE_META.get(dtype, {}).get("layout") == "financial" or dtype in ("proposal", "maintenance_plan", "statement_of_work"):
        return [{"description": "New service", "sub": "Short description", "qty": 1, "rate": 0}]
    return []
