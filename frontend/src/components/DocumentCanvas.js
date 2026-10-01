import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from "react";
import { money, TYPE_MAP } from "@/lib/format";
import { isSafeLogo } from "@/lib/print";
import "@/styles/document.css";
import PageGuides from "@/components/PageGuides";

const parseNum = (s) => parseFloat(String(s == null ? "" : s).replace(/[^0-9.\-]/g, "")) || 0;
const PRICING_TYPES = new Set(["proposal", "maintenance_plan", "statement_of_work"]);
const LEGAL_TYPES = new Set(["service_agreement", "nda", "statement_of_work"]);
const SIGN_TYPES = new Set(["service_agreement", "nda", "statement_of_work", "proposal"]);

const FIELD_LABELS = {
  brand: "Brand name", tagline: "Tagline", footer_line: "Footer line", footer_contact: "Footer contact",
  bill_to_name: "Client name", bill_to_lines: "Client address", from_name: "Sender name", from_lines: "Sender address",
  issue_date: "Issue date", due_date: "Due date", project_reference: "Project reference", billing_note: "Billing note",
  payment_details: "Payment details", sign_left: "Provider signature line", sign_right: "Client signature line",
};
const labelFor = (f) => FIELD_LABELS[f] || f.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
const MULTILINE_TAGS = new Set(["div", "p"]);
const tb = (editable, label, multi = false) => (editable ? { role: "textbox", "aria-label": label, "aria-multiline": multi ? "true" : "false" } : {});

// content is set once on mount: React 19 re-writes innerHTML on every render otherwise, wiping what the user typed.
// The editor remounts the canvas (key) whenever stored content must replace the on-screen text.
function Editable({ field, tag = "span", className = "", initial = "", editable }) {
  const Tag = tag;
  const ref = useRef(null);
  useLayoutEffect(() => {
    if (ref.current) ref.current.innerHTML = (initial || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\n/g, "<br>");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const a11y = editable ? { role: "textbox", "aria-label": labelFor(field), "aria-multiline": MULTILINE_TAGS.has(tag) ? "true" : "false", tabIndex: 0 } : {};
  return <Tag ref={ref} contentEditable={editable} suppressContentEditableWarning data-field={field} className={className} {...a11y} />;
}

const DocumentCanvas = forwardRef(function DocumentCanvas(
  { doc, currency, theme, discount, tax, editable = true, size = "A4", onChange, guides = false }, ref
) {
  const rootRef = useRef(null);
  const meta = TYPE_MAP[doc.type] || { layout: "content" };
  const layout = meta.layout;
  const data = doc.data || {};

  const [rows, setRows] = useState(() =>
    (doc.line_items || []).map((it, i) => ({ key: `r${i}-${Math.random()}`, ...it }))
  );
  const [sections, setSections] = useState(() =>
    (data.sections || []).map((s, i) => ({ key: `s${i}-${Math.random()}`, ...s }))
  );
  const [totals, setTotals] = useState({ sub: 0, disc: 0, tax: 0, total: 0 });

  const recalc = () => {
    const root = rootRef.current;
    if (!root) return;
    let sub = 0;
    root.querySelectorAll("tr[data-row]").forEach((tr) => {
      const q = parseNum(tr.querySelector(".qty")?.innerText);
      const r = parseNum(tr.querySelector(".rate")?.innerText);
      const amt = q * r;
      sub += amt;
      const cell = tr.querySelector(".amount");
      if (cell) cell.innerText = money(amt, currency);
    });
    let disc = 0;
    if (discount?.enabled) { const v = Number(discount.value) || 0; disc = discount.mode === "percent" ? (sub * v) / 100 : v; }
    const base = sub - disc;
    let tx = 0;
    if (tax?.enabled) { const v = Number(tax.value) || 0; tx = tax.mode === "percent" ? (base * v) / 100 : v; }
    setTotals({ sub, disc, tax: tx, total: base + tx });
  };

  useEffect(() => { recalc(); }, [rows, currency, discount, tax]); // eslint-disable-line react-hooks/exhaustive-deps

  // structural edits (row / section added or removed) count as changes; skip the initial mount
  const prevStruct = useRef({ rows, sections }); // identity check is StrictMode-safe (effects run twice on mount)
  useEffect(() => {
    if (prevStruct.current.rows === rows && prevStruct.current.sections === sections) return;
    prevStruct.current = { rows, sections };
    if (onChange) onChange();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, sections]);

  useImperativeHandle(ref, () => ({
    addLineItem: (item) => setRows((r) => [...r, { key: `r${Date.now()}-${Math.random()}`, description: item?.description || "New service", sub: item?.sub || "Short description", qty: item?.qty ?? 1, rate: item?.rate ?? 0 }]),
    addSection: () => setSections((s) => [...s, { key: `s${Date.now()}`, label: String(s.length + 1).padStart(2, "0"), heading: "New section", body: "Add content…" }]),
    collect: () => {
      const root = rootRef.current;
      // empty-overwrite guard: never report a payload before the canvas is mounted/populated
      if (!root || !root.isConnected || root.querySelectorAll("[data-field]").length === 0) return null;
      // start from the stored data so non-editable fields (label, logo_url, reference_label…) survive a save
      const d = { ...(doc.data || {}) };
      delete d.sections;
      delete d.logo_url; // not editable here; the server keeps it (merge-patch) and it keeps payloads small
      root.querySelectorAll("[data-field]").forEach((el) => { d[el.dataset.field] = el.innerText.trim(); });
      const line_items = [...root.querySelectorAll("tr[data-row]")].map((tr) => ({
        description: tr.querySelector(".d")?.innerText.trim() || "",
        sub: tr.querySelector(".s")?.innerText.trim() || "",
        qty: parseNum(tr.querySelector(".qty")?.innerText),
        rate: parseNum(tr.querySelector(".rate")?.innerText),
      }));
      const secs = [...root.querySelectorAll("[data-section]")].map((s) => ({
        label: s.querySelector(".sec-label")?.innerText.trim() || "",
        heading: s.querySelector(".sec-h")?.innerText.trim() || "",
        body: s.querySelector(".sec-b")?.innerText.trim() || "",
      }));
      d.sections = secs;
      return { data: d, line_items };
    },
  }));

  const rateBlur = (e) => { e.target.innerText = money(parseNum(e.target.innerText), currency); recalc(); };

  const Masthead = (
    <div className="mast">
      <div>
        <div className="brand">
          {isSafeLogo(data.logo_url)
            ? <img src={data.logo_url} alt={data.brand || "Logo"} decoding="sync" data-testid="doc-logo" />
            : <><i className="bdot" aria-hidden="true" /><Editable field="brand" editable={editable} initial={data.brand || "Your Agency"} /></>}
        </div>
        <Editable field="tagline" tag="div" className="mono tag" editable={editable} initial={data.tagline || ""} />
      </div>
      <div className="docno">{data.label} / <b data-testid="doc-number">{doc.number || data.number}</b></div>
    </div>
  );

  const Footer = (
    <footer><div className="in">
      <Editable field="footer_line" tag="b" editable={editable} initial={data.footer_line || "Thank you for working with us."} />
      <Editable field="footer_contact" tag="span" className="mono" editable={editable} initial={data.footer_contact || ""} />
    </div></footer>
  );

  const Table = (showTable) => showTable && (
    <>
      <table className="items" onInput={recalc}>
        <colgroup><col className="c1" /><col className="c2" /><col className="c3" /><col className="c4" /></colgroup>
        <thead><tr><th>Description</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead>
        <tbody>
          {rows.map((it, i) => (
            <tr key={it.key} data-row>
              <td>
                {editable && <button type="button" className="rm" title="Remove line item" aria-label={`Remove line item ${i + 1}`} data-testid="remove-line-item" onClick={() => { setRows((r) => r.filter((x) => x.key !== it.key)); }}>×</button>}
                <span className="d" contentEditable={editable} suppressContentEditableWarning {...tb(editable, `Line ${i + 1} description`)}>{it.description}</span>
                <span className="s" contentEditable={editable} suppressContentEditableWarning {...tb(editable, `Line ${i + 1} detail`)}>{it.sub}</span>
              </td>
              <td className="qty" contentEditable={editable} suppressContentEditableWarning onInput={recalc} {...tb(editable, `Line ${i + 1} quantity`)}>{it.qty}</td>
              <td className="rate" contentEditable={editable} suppressContentEditableWarning onBlur={rateBlur} onInput={recalc} {...tb(editable, `Line ${i + 1} rate`)}>{money(it.rate, currency)}</td>
              <td className="amount">{money((Number(it.qty) || 0) * (Number(it.rate) || 0), currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {editable && (
        <button
          type="button"
          className="doc-add-row"
          data-testid="canvas-add-line-item"
          onClick={() => setRows((r) => [...r, { key: `r${Date.now()}-${Math.random()}`, description: "New service", sub: "Short description", qty: 1, rate: 0 }])}
        >
          + Add line item
        </button>
      )}
    </>
  );

  const sumsBlock = (
    <div className="sums">
      <div className="row"><span className="mono">Subtotal</span><span className="v">{money(totals.sub, currency)}</span></div>
      {discount?.enabled && <div className="row"><span className="mono">{discount.label || "Discount"}{discount.mode === "percent" ? ` (${discount.value}%)` : ""}</span><span className="v">− {money(totals.disc, currency)}</span></div>}
      {tax?.enabled && <div className="row"><span className="mono">{tax.label || "Tax"}{tax.mode === "percent" ? ` (${tax.value}%)` : ""}</span><span className="v">{money(totals.tax, currency)}</span></div>}
    </div>
  );

  let body;
  if (layout === "financial") {
    const isReceipt = doc.type === "receipt";
    const isExpense = doc.type === "expense_report";
    const party1Label = isExpense ? "Submitted to" : isReceipt ? "Received from" : "Bill to";
    const party3Label = isExpense ? "Date" : isReceipt ? "Payment date" : "Issue date";
    const totalLabel = isExpense ? "Total reimbursable" : isReceipt ? "Amount paid" : "Total due";
    const payLabel = isExpense ? "Reimburse to" : "Payment details";
    body = (
      <>
        <div className="hero">
          <h1>{data.label}<span className="dot">.</span></h1>
          {isReceipt && <div className="paidstamp">PAID</div>}
        </div>
        <div className="parties">
          <div><div className="mono">{party1Label}</div>
            <Editable field="bill_to_name" tag="div" className="name" editable={editable} initial={data.bill_to_name || ""} />
            <Editable field="bill_to_lines" tag="div" className="sub" editable={editable} initial={data.bill_to_lines || ""} /></div>
          <div><div className="mono">From</div>
            <Editable field="from_name" tag="div" className="name" editable={editable} initial={data.from_name || ""} />
            <Editable field="from_lines" tag="div" className="sub" editable={editable} initial={data.from_lines || ""} /></div>
          <div><div className="mono">{party3Label}</div>
            <Editable field="issue_date" tag="div" className="val" editable={editable} initial={data.issue_date || ""} />
            {!isReceipt && !isExpense && <><div className="mono">Due date</div><Editable field="due_date" tag="div" className="val" editable={editable} initial={data.due_date || ""} /></>}</div>
        </div>
        <div className="project">
          <div className="mono">{data.reference_label || "Project reference"}</div>
          <Editable field="project_reference" tag="div" className="v" editable={editable} initial={data.project_reference || ""} />
        </div>
        {Table(true)}
        <div className="closing">
        <div className="billing">
          <div className="bnote">
            <div className="mono">Billing note</div>
            <Editable field="billing_note" tag="p" editable={editable} initial={data.billing_note || "Professional services are billed separately from third-party subscriptions, domains and platform charges."} />
          </div>
          <div className="totcol">
            {sumsBlock}
            <div className="total"><div className="mono">{totalLabel}</div><div className="big">{money(totals.total, currency)}</div></div>
          </div>
        </div>
        <div className="pay">
          <div><div className="mono">{payLabel}</div><Editable field="payment_details" tag="p" editable={editable} initial={data.payment_details || ""} /></div>
          {isExpense ? (
            <div><div className="mono">Notes</div>
              <Editable field="payment_terms" tag="p" editable={editable} initial={data.payment_terms || ""} />
              <Editable field="note" tag="p" className="note" editable={editable} initial={data.note || ""} /></div>
          ) : isReceipt ? (
            <div><div className="mono">Payment received</div>
              <Editable field="payment_method" tag="p" editable={editable} initial={data.payment_method || "Bank transfer"} />
              <Editable field="paid_date" tag="p" className="note" editable={editable} initial={data.paid_date || ""} /></div>
          ) : (
            <div><div className="mono">Payment terms</div>
              <Editable field="payment_terms" tag="p" editable={editable} initial={data.payment_terms || ""} />
              <Editable field="note" tag="p" className="note" editable={editable} initial={data.note || ""} /></div>
          )}
        </div>
        </div>
      </>
    );
  } else if (layout === "letterhead") {
    body = (
      <>
        <div className="hero"><h1><Editable field="brand" editable={editable} initial={data.brand || "Your Agency"} /><span className="dot">.</span></h1>
          <Editable field="subtitle" tag="div" className="sub" editable={editable} initial={data.subtitle || ""} /></div>
        <div className="meta">
          <div><div className="mono">Date</div><Editable field="issue_date" tag="div" className="val" editable={editable} initial={data.issue_date || ""} /></div>
          <div><div className="mono">Reference</div><div className="val">{data.number}</div></div>
          <div><div className="mono">Contact</div><Editable field="footer_contact_meta" tag="div" className="val" editable={editable} initial={data.footer_contact || ""} /></div>
        </div>
        <div className="section" style={{ border: 0, minHeight: "120mm" }}>
          <Editable field="letter_body" tag="div" className="body" editable={editable} initial={data.letter_body || "Write your letter here…"} />
        </div>
      </>
    );
  } else {
    const showPricing = PRICING_TYPES.has(doc.type) || rows.length > 0;
    body = (
      <>
        <div className="hero"><h1>{data.label}<span className="dot">.</span></h1>
          <Editable field="subtitle" tag="div" className="sub" editable={editable} initial={data.subtitle || ""} /></div>
        <div className="meta">
          <div><div className="mono">Prepared for</div><Editable field="bill_to_name" tag="div" className="val" editable={editable} initial={data.bill_to_name || ""} /></div>
          <div><div className="mono">Prepared by</div><Editable field="from_name" tag="div" className="val" editable={editable} initial={data.from_name || ""} /></div>
          <div><div className="mono">Date</div><Editable field="issue_date" tag="div" className="val" editable={editable} initial={data.issue_date || ""} /></div>
        </div>
        {sections.map((s) => (
          <div className="section" data-section key={s.key}>
            <div className="mono">
              <span className="sec-label" contentEditable={editable} suppressContentEditableWarning {...tb(editable, "Section number")}>{s.label}</span>
              {editable && <button type="button" className="secrm" aria-label={`Remove section ${s.heading}`} onClick={() => setSections((x) => x.filter((y) => y.key !== s.key))}>remove</button>}
            </div>
            <h3 className="sec-h" contentEditable={editable} suppressContentEditableWarning {...tb(editable, "Section heading")}>{s.heading}</h3>
            <div className="body sec-b" contentEditable={editable} suppressContentEditableWarning {...tb(editable, "Section text", true)}>{s.body}</div>
          </div>
        ))}
        {showPricing && (
          <div className="section">
            <div className="mono">Pricing</div>
            {Table(true)}
            <div className="closing">
              {sumsBlock}
              <div className="total"><div className="mono">Total</div><div className="big">{money(totals.total, currency)}</div></div>
            </div>
          </div>
        )}
        {LEGAL_TYPES.has(doc.type) && (
          <div className="legal">This document is a layout scaffold. All legal text must be reviewed and approved by a qualified lawyer before use.</div>
        )}
        {SIGN_TYPES.has(doc.type) && (
          <div className="sign">
            <div className="line"><Editable field="sign_left" editable={editable} initial={data.sign_left || "Service Provider — signature & date"} /></div>
            <div className="line"><Editable field="sign_right" editable={editable} initial={data.sign_right || "Client — signature & date"} /></div>
          </div>
        )}
      </>
    );
  }

  return (
    <div className={`doc-wrap ${theme === "dark" ? "doc-dark" : "doc-light"}`} data-print-target>
      <div ref={rootRef} className={`doc-page ${size === "Letter" ? "letter" : ""}`} data-testid="document-canvas"
        onInput={editable && onChange ? () => onChange() : undefined}>
        {guides && <PageGuides rootRef={rootRef} size={size} />}
        {/* print-frame: plain block on screen; in Firefox/Safari print its spacer rows repeat on every page as margins */}
        <table className="print-frame" role="presentation">
          <thead><tr><td><div className="pf-top" /></td></tr></thead>
          <tbody><tr><td>
            {Masthead}
            {body}
            {Footer}
          </td></tr></tbody>
          <tfoot><tr><td><div className="pf-bot" /></td></tr></tfoot>
        </table>
      </div>
    </div>
  );
});

export default DocumentCanvas;
