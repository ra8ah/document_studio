import {
  FileText, Receipt, FileSignature, ShieldCheck, ClipboardList, Wrench,
  Sparkles, HeartHandshake, ScrollText, FileCheck2, Quote, Mail,
} from "lucide-react";

export const CURRENCIES = ["USD", "EUR", "GBP", "AED", "INR", "CAD", "AUD", "SGD", "JPY", "CHF", "SAR", "ZAR", "NZD"];

export function money(amount, currency = "USD") {
  const n = Number(amount) || 0;
  try {
    return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", {
      style: "currency", currency, minimumFractionDigits: currency === "JPY" ? 0 : 2,
      maximumFractionDigits: currency === "JPY" ? 0 : 2,
    }).format(n);
  } catch {
    return `${currency} ${n.toFixed(2)}`;
  }
}

export const DOC_TYPES = [
  { id: "invoice", label: "Invoice", code: "01", layout: "financial", icon: FileText, desc: "Billable line items, tax, payment status and bank details." },
  { id: "quotation", label: "Quotation / Estimate", code: "02", layout: "financial", icon: FileCheck2, desc: "Priced estimate with acceptance terms." },
  { id: "proposal", label: "Proposal", code: "03", layout: "content", icon: ClipboardList, desc: "Overview, scope, deliverables, timeline, pricing, terms." },
  { id: "statement_of_work", label: "Statement of Work", code: "04", layout: "content", icon: ScrollText, desc: "Milestones, responsibilities and acceptance criteria." },
  { id: "service_agreement", label: "Service Agreement", code: "05", layout: "content", icon: FileSignature, desc: "Cover and signature page scaffold." },
  { id: "nda", label: "Non-Disclosure Agreement", code: "06", layout: "content", icon: ShieldCheck, desc: "Confidentiality layout scaffold." },
  { id: "receipt", label: "Receipt", code: "07", layout: "financial", icon: Receipt, desc: "Payment confirmation with paid stamp." },
  { id: "project_status", label: "Project Status Report", code: "08", layout: "content", icon: ClipboardList, desc: "Progress, blockers and next steps." },
  { id: "maintenance_plan", label: "Maintenance & Support", code: "09", layout: "content", icon: Wrench, desc: "Retainer, SLA and support tiers." },
  { id: "welcome_doc", label: "Welcome Document", code: "10", layout: "content", icon: Sparkles, desc: "Onboarding, portal and questionnaire links." },
  { id: "thank_you_doc", label: "Thank-You Document", code: "11", layout: "content", icon: HeartHandshake, desc: "Handover note with testimonial link." },
  { id: "letterhead", label: "Letterhead", code: "12", layout: "letterhead", icon: Mail, desc: "Official correspondence template." },
];

export const TYPE_MAP = Object.fromEntries(DOC_TYPES.map((t) => [t.id, t]));

export const STATUSES = ["draft", "sent", "viewed", "paid", "overdue", "cancelled"];

export const STATUS_META = {
  draft: { label: "Draft", color: "#78746C", bg: "rgba(120,116,108,.14)" },
  sent: { label: "Sent", color: "#2C5E8A", bg: "rgba(44,94,138,.14)" },
  viewed: { label: "Viewed", color: "#7A5AA6", bg: "rgba(122,90,166,.14)" },
  paid: { label: "Paid", color: "#2E6B48", bg: "rgba(46,107,72,.16)" },
  overdue: { label: "Overdue", color: "#C04C20", bg: "rgba(192,76,32,.14)" },
  cancelled: { label: "Cancelled", color: "#96918A", bg: "rgba(150,145,138,.14)" },
};

export function fmtDate(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return iso; }
}
