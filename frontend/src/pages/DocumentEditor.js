import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { API } from "@/lib/api";
import DocumentCanvas from "@/components/DocumentCanvas";
import { CURRENCIES, STATUSES, STATUS_META, TYPE_MAP } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  ArrowLeft, Save, Download, Share2, MoreVertical, Plus, Copy, RefreshCw, BadgeCheck, Trash2, Package, Sun, Moon, Loader2,
} from "lucide-react";
import { toast } from "sonner";

const CONVERT_LABEL = { quotation: "invoice", proposal: "statement_of_work", invoice: "receipt" };

export default function DocumentEditor() {
  const { id } = useParams();
  const nav = useNavigate();
  const canvasRef = useRef(null);
  const [doc, setDoc] = useState(null);
  const [currency, setCurrency] = useState("USD");
  const [theme, setTheme] = useState("light");
  const [status, setStatus] = useState("draft");
  const [discount, setDiscount] = useState({ enabled: false, mode: "percent", value: 0, label: "Discount" });
  const [tax, setTax] = useState({ enabled: false, mode: "percent", value: 0, label: "Tax" });
  const [packages, setPackages] = useState([]);
  const [saving, setSaving] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [shareLink, setShareLink] = useState("");
  const [scale, setScale] = useState(1);

  useEffect(() => {
    api.get(`/documents/${id}`).then((r) => {
      const d = r.data;
      setDoc(d); setCurrency(d.currency); setTheme(d.theme); setStatus(d.status);
      if (d.discount) setDiscount({ ...discount, ...d.discount });
      if (d.tax) setTax({ ...tax, ...d.tax });
    });
    api.get("/packages").then((r) => setPackages(r.data));
    const onResize = () => { const w = Math.min(window.innerWidth - 40, 900); setScale(Math.min(1, (w) / 794)); };
    onResize(); window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
    // eslint-disable-next-line
  }, [id]);

  if (!doc) return <div className="mono-label">Loading…</div>;
  const meta = TYPE_MAP[doc.type] || {};
  const showLineItems = meta.layout === "financial" || ["proposal", "maintenance_plan", "statement_of_work"].includes(doc.type);
  const isContent = meta.layout === "content";

  const save = async (silent) => {
    setSaving(true);
    const { data, line_items } = canvasRef.current.collect();
    try {
      const { data: updated } = await api.put(`/documents/${id}`, {
        data, line_items, currency, theme, status, discount, tax,
      });
      setDoc(updated);
      if (!silent) toast.success("Saved");
    } catch { toast.error("Save failed"); }
    setSaving(false);
  };

  const setStatusNow = async (s) => {
    setStatus(s);
    await api.post(`/documents/${id}/status`, { status: s });
    toast.success(`Marked ${STATUS_META[s].label.toLowerCase()}`);
  };

  const exportFile = (kind) => {
    const url = kind === "docx" ? `${API}/documents/${id}/docx` : `${API}/documents/${id}/pdf?size=${kind}`;
    window.open(url, "_blank");
  };

  const share = async () => {
    const { data } = await api.post(`/documents/${id}/share`);
    const link = `${window.location.origin}/share/${data.token}`;
    setShareLink(link); setShareOpen(true);
    if (status === "draft") setStatusNow("sent");
  };

  const duplicate = async () => { const { data } = await api.post(`/documents/${id}/duplicate`); toast.success("Duplicated"); nav(`/documents/${data.id}`); };
  const convert = async () => { const { data } = await api.post(`/documents/${id}/convert`, {}); toast.success("Converted"); nav(`/documents/${data.id}`); };
  const markPaid = async () => {
    const { data } = await api.post(`/documents/${id}/mark-paid`);
    setStatus("paid");
    toast.success("Marked paid" + (data.receipt ? " · receipt created" : ""));
    if (data.receipt) nav(`/documents/${data.receipt.id}`);
  };
  const remove = async () => { if (!window.confirm("Delete this document?")) return; await api.delete(`/documents/${id}`); toast.success("Deleted"); nav("/documents"); };

  const s = STATUS_META[status] || STATUS_META.draft;

  return (
    <div className="rise -m-6 sm:-m-10 lg:-m-12">
      {/* Toolbar */}
      <div className="sticky top-16 z-10 bg-background/90 backdrop-blur border-b border-foreground/10 px-4 sm:px-8 py-3 flex flex-wrap items-center gap-2">
        <button onClick={() => nav("/documents")} className="p-2 rounded-full hover:bg-foreground/5" data-testid="editor-back"><ArrowLeft size={18} /></button>
        <div className="mr-2">
          <div className="mono-label">{meta.label}</div>
          <div className="font-mono text-sm font-medium">{doc.number}</div>
        </div>

        <Select value={status} onValueChange={setStatusNow}>
          <SelectTrigger className="w-[130px] rounded-full h-9" data-testid="status-select">
            <span className="w-2 h-2 rounded-full mr-1" style={{ background: s.color }} /><SelectValue />
          </SelectTrigger>
          <SelectContent>{STATUSES.map((x) => <SelectItem key={x} value={x}>{STATUS_META[x].label}</SelectItem>)}</SelectContent>
        </Select>

        <Select value={currency} onValueChange={setCurrency}>
          <SelectTrigger className="w-[90px] rounded-full h-9" data-testid="currency-select"><SelectValue /></SelectTrigger>
          <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
        </Select>

        <button onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))} data-testid="doc-theme-toggle"
          className="p-2 rounded-full hover:bg-foreground/5 border border-foreground/15" title="Toggle paper theme">
          {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
        </button>

        <div className="ml-auto flex items-center gap-2">
          {showLineItems && (
            <>
              <Button variant="outline" size="sm" className="rounded-full gap-1" data-testid="add-line-item-button" onClick={() => canvasRef.current.addLineItem()}><Plus size={14} /> Line item</Button>
              {packages.length > 0 && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild><Button variant="outline" size="sm" className="rounded-full gap-1" data-testid="add-package-menu"><Package size={14} /> Package</Button></DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {packages.map((p) => <DropdownMenuItem key={p.id} onClick={() => canvasRef.current.addLineItem(p)}>{p.description}</DropdownMenuItem>)}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </>
          )}
          {isContent && <Button variant="outline" size="sm" className="rounded-full gap-1" data-testid="add-section-button" onClick={() => canvasRef.current.addSection()}><Plus size={14} /> Section</Button>}

          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="outline" size="sm" className="rounded-full gap-1" data-testid="export-menu"><Download size={14} /> Export</Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => exportFile("A4")} data-testid="export-pdf-a4">PDF · A4</DropdownMenuItem>
              <DropdownMenuItem onClick={() => exportFile("Letter")} data-testid="export-pdf-letter">PDF · US Letter</DropdownMenuItem>
              <DropdownMenuItem onClick={() => exportFile("docx")} data-testid="export-docx">Word · DOCX</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <Button variant="outline" size="sm" className="rounded-full gap-1" onClick={share} data-testid="share-button"><Share2 size={14} /> Share</Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="outline" size="sm" className="rounded-full px-2" data-testid="more-menu"><MoreVertical size={16} /></Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={duplicate} data-testid="duplicate-doc"><Copy size={14} className="mr-2" /> Duplicate</DropdownMenuItem>
              {CONVERT_LABEL[doc.type] && <DropdownMenuItem onClick={convert} data-testid="convert-doc"><RefreshCw size={14} className="mr-2" /> Convert to {TYPE_MAP[CONVERT_LABEL[doc.type]].label}</DropdownMenuItem>}
              {doc.type === "invoice" && <DropdownMenuItem onClick={markPaid} data-testid="mark-paid"><BadgeCheck size={14} className="mr-2" /> Mark as paid</DropdownMenuItem>}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={remove} className="text-[#C04C20]" data-testid="delete-doc"><Trash2 size={14} className="mr-2" /> Delete</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <Button size="sm" className="rounded-full gap-1" onClick={() => save(false)} disabled={saving} data-testid="save-document-button">
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save
          </Button>
        </div>
      </div>

      {/* Discount / Tax controls */}
      {showLineItems && (
        <div className="px-4 sm:px-8 py-3 flex flex-wrap gap-6 border-b border-foreground/10 text-sm">
          <div className="flex items-center gap-2" data-testid="discount-controls">
            <Switch checked={discount.enabled} onCheckedChange={(v) => setDiscount((d) => ({ ...d, enabled: v }))} data-testid="discount-toggle" />
            <span className="mono-label">Discount</span>
            {discount.enabled && (<>
              <Input className="w-20 h-8" value={discount.value} onChange={(e) => setDiscount((d) => ({ ...d, value: e.target.value }))} data-testid="discount-value" />
              <Select value={discount.mode} onValueChange={(v) => setDiscount((d) => ({ ...d, mode: v }))}><SelectTrigger className="w-24 h-8"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="percent">%</SelectItem><SelectItem value="fixed">Fixed</SelectItem></SelectContent></Select>
              <Input className="w-28 h-8" value={discount.label} onChange={(e) => setDiscount((d) => ({ ...d, label: e.target.value }))} placeholder="Label" />
            </>)}
          </div>
          <div className="flex items-center gap-2" data-testid="tax-controls">
            <Switch checked={tax.enabled} onCheckedChange={(v) => setTax((t) => ({ ...t, enabled: v }))} data-testid="tax-toggle" />
            <span className="mono-label">Tax</span>
            {tax.enabled && (<>
              <Input className="w-20 h-8" value={tax.value} onChange={(e) => setTax((t) => ({ ...t, value: e.target.value }))} data-testid="tax-value" />
              <Select value={tax.mode} onValueChange={(v) => setTax((t) => ({ ...t, mode: v }))}><SelectTrigger className="w-24 h-8"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="percent">%</SelectItem><SelectItem value="fixed">Fixed</SelectItem></SelectContent></Select>
              <Input className="w-28 h-8" value={tax.label} onChange={(e) => setTax((t) => ({ ...t, label: e.target.value }))} placeholder="Label (GST/VAT)" />
            </>)}
          </div>
          <span className="mono-label self-center ml-auto text-muted-foreground">Click any text on the page to edit · hover a row to remove</span>
        </div>
      )}

      {/* Canvas */}
      <div className="py-8 px-2 overflow-x-auto" style={{ background: theme === "dark" ? "#141210" : "#E7E0D3" }}>
        <div style={{ zoom: scale }}>
          <DocumentCanvas ref={canvasRef} doc={doc} currency={currency} theme={theme} discount={discount} tax={tax} editable />
        </div>
      </div>

      <Dialog open={shareOpen} onOpenChange={setShareOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Private share link</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Anyone with this link can view (and download) this document.</p>
          <div className="flex gap-2">
            <Input value={shareLink} readOnly data-testid="share-link-input" className="rounded-full" />
            <Button className="rounded-full" onClick={() => { navigator.clipboard.writeText(shareLink); toast.success("Copied"); }} data-testid="copy-share-link">Copy</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
