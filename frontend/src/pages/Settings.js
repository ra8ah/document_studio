import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { API } from "@/lib/api";
import { CURRENCIES, DOC_TYPES } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Trash2, Plus, Download, Upload } from "lucide-react";
import { isSafeLogo } from "@/lib/print";
import { toast } from "sonner";
import LoadError from "@/components/LoadError";

const LOGO_TYPES = ["image/svg+xml", "image/png", "image/jpeg", "image/webp"];
const MAX_LOGO_BYTES = 2 * 1024 * 1024;

const F = ({ label, k, form, set, type = "text" }) => (
  <div>
    <Label className="mono-label">{label}</Label>
    <Input type={type} value={form[k] || ""} onChange={set(k)} className="mt-1.5 rounded-xl" data-testid={`profile-${k}`} />
  </div>
);

export default function Settings() {
  const [form, setForm] = useState(null);
  const [loadErr, setLoadErr] = useState(false);
  const [reload, setReload] = useState(0);
  const [packages, setPackages] = useState([]);
  const [pkg, setPkg] = useState({ description: "", sub: "", qty: 1, rate: 0 });
  const nav = useNavigate();

  useEffect(() => {
    api.get("/profile").then((r) => {
      const p = r.data;
      if (p.logo_url && !isSafeLogo(p.logo_url)) {
        toast.message("Your logo was a remote URL, which is no longer supported. Please upload the logo file.");
        p.logo_url = "";
      }
      setForm(p);
    }).catch(() => setLoadErr(true));
    api.get("/packages").then((r) => setPackages(r.data)).catch(() => {});
  }, [reload]);

  if (loadErr) return <LoadError onRetry={() => { setLoadErr(false); setReload((n) => n + 1); }} testid="settings-load-error" />;
  if (!form) return <div className="mono-label" role="status">Loading…</div>;
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setPrefix = (k) => (e) => setForm((f) => ({ ...f, prefixes: { ...(f.prefixes || {}), [k]: e.target.value } }));

  const save = async () => {
    try { await api.put("/profile", form); toast.success("Settings saved"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
  };

  const onLogo = (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!LOGO_TYPES.includes(file.type)) return toast.error("Use an SVG, PNG, JPEG or WebP file");
    if (file.size > MAX_LOGO_BYTES) return toast.error("Logo must be 2 MB or smaller");
    const reader = new FileReader();
    reader.onload = () => {
      const uri = String(reader.result || "");
      if (!isSafeLogo(uri)) return toast.error("Could not read this image");
      setForm((f) => ({ ...f, logo_url: uri }));
      toast.success("Logo ready — save changes to apply it to new documents");
    };
    reader.onerror = () => toast.error("Could not read this image");
    reader.readAsDataURL(file); // original bytes, no re-encoding → natural resolution
  };

  const addPackage = async () => {
    if (!pkg.description.trim()) return toast.error("Description required");
    const { data } = await api.post("/packages", { ...pkg, qty: Number(pkg.qty), rate: Number(pkg.rate) });
    setPackages((p) => [...p, data]); setPkg({ description: "", sub: "", qty: 1, rate: 0 });
  };
  const delPackage = async (id) => { await api.delete(`/packages/${id}`); setPackages((p) => p.filter((x) => x.id !== id)); };

  return (
    <div className="rise space-y-8 max-w-3xl">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="mono-label">Configuration / 04</div>
          <h1 className="headline text-4xl sm:text-5xl mt-2">Settings<span className="dotaccent">.</span></h1>
        </div>
        <Button data-testid="save-settings-button" onClick={save} className="rounded-full">Save changes</Button>
      </div>

      <Tabs defaultValue="brand">
        <TabsList className="rounded-full flex-wrap h-auto">
          <TabsTrigger value="brand" className="rounded-full">Brand</TabsTrigger>
          <TabsTrigger value="contact" className="rounded-full">Contact</TabsTrigger>
          <TabsTrigger value="bank" className="rounded-full">Payment</TabsTrigger>
          <TabsTrigger value="defaults" className="rounded-full">Defaults</TabsTrigger>
          <TabsTrigger value="numbering" className="rounded-full">Numbering</TabsTrigger>
          <TabsTrigger value="packages" className="rounded-full">Packages</TabsTrigger>
          <TabsTrigger value="data" className="rounded-full">Data</TabsTrigger>
        </TabsList>

        <TabsContent value="brand" className="grid sm:grid-cols-2 gap-4 mt-6">
          <F label="Agency name" k="agency_name" form={form} set={set} />
          <F label="Legal name" k="legal_name" form={form} set={set} />
          <div className="sm:col-span-2"><F label="Tagline" k="tagline" form={form} set={set} /></div>
          <div className="sm:col-span-2">
            <Label className="mono-label">Logo</Label>
            <div className="mt-1.5 flex flex-wrap items-center gap-3 rounded-xl border border-foreground/15 p-3">
              {isSafeLogo(form.logo_url)
                ? <img src={form.logo_url} alt="Logo preview" className="h-12 max-w-[200px] object-contain" data-testid="logo-preview" />
                : <span className="text-sm text-muted-foreground">No logo — the agency name is used instead.</span>}
              <label className="ml-auto inline-flex cursor-pointer items-center gap-1 rounded-full border border-foreground/20 px-4 py-1.5 text-sm hover:bg-foreground/5">
                <Upload size={14} /> Upload
                <input type="file" accept={LOGO_TYPES.join(",")} className="hidden" onChange={onLogo} data-testid="logo-upload-input" />
              </label>
              {form.logo_url && <Button type="button" variant="ghost" size="sm" className="rounded-full" onClick={() => setForm((f) => ({ ...f, logo_url: "" }))} data-testid="logo-remove">Remove</Button>}
            </div>
            <p className="mt-1.5 text-xs text-muted-foreground">SVG (best — stays vector in PDFs) or a high-resolution PNG / JPEG / WebP, max 2 MB. Stored with your settings; remote URLs are not used.</p>
          </div>
        </TabsContent>

        <TabsContent value="contact" className="grid sm:grid-cols-2 gap-4 mt-6">
          <F label="Email" k="email" form={form} set={set} />
          <F label="Phone" k="phone" form={form} set={set} />
          <F label="Website" k="website" form={form} set={set} />
          <F label="Tax IDs (GST / VAT / GSTIN)" k="tax_ids" form={form} set={set} />
          <div className="sm:col-span-2"><Label className="mono-label">Address</Label>
            <Textarea value={form.address} onChange={set("address")} className="mt-1.5 rounded-xl" data-testid="profile-address" /></div>
        </TabsContent>

        <TabsContent value="bank" className="grid sm:grid-cols-2 gap-4 mt-6">
          <F label="Bank name" k="bank_name" form={form} set={set} />
          <F label="Account number" k="bank_account" form={form} set={set} />
          <F label="IFSC" k="ifsc" form={form} set={set} />
          <F label="SWIFT" k="swift" form={form} set={set} />
          <F label="UPI ID" k="upi" form={form} set={set} />
          <div className="sm:col-span-2"><Label className="mono-label">Payment links</Label>
            <Textarea value={form.payment_links} onChange={set("payment_links")} className="mt-1.5 rounded-xl" /></div>
        </TabsContent>

        <TabsContent value="defaults" className="grid sm:grid-cols-2 gap-4 mt-6">
          <div><Label className="mono-label">Default currency</Label>
            <Select value={form.default_currency} onValueChange={(v) => setForm((f) => ({ ...f, default_currency: v }))}>
              <SelectTrigger className="mt-1.5" data-testid="profile-default-currency"><SelectValue /></SelectTrigger>
              <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
            </Select></div>
          <div className="sm:col-span-2"><Label className="mono-label">Default terms</Label>
            <Textarea value={form.default_terms} onChange={set("default_terms")} className="mt-1.5 rounded-xl" /></div>
          <div className="sm:col-span-2"><Label className="mono-label">Default notes</Label>
            <Textarea value={form.default_notes} onChange={set("default_notes")} className="mt-1.5 rounded-xl" /></div>
        </TabsContent>

        <TabsContent value="numbering" className="mt-6">
          <p className="text-sm text-muted-foreground mb-4">Configure the prefix for each document type. Numbers auto-increment (e.g. INV-0001).</p>
          <div className="grid sm:grid-cols-2 gap-4">
            {DOC_TYPES.map((t) => (
              <div key={t.id}><Label className="mono-label">{t.label}</Label>
                <Input value={(form.prefixes || {})[t.id] || ""} onChange={setPrefix(t.id)} className="mt-1.5 rounded-xl" data-testid={`prefix-${t.id}`} /></div>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="packages" className="mt-6 space-y-4">
          <p className="text-sm text-muted-foreground">Reusable services you can add to any document with one click.</p>
          <div className="grid sm:grid-cols-[1fr_1fr_80px_120px_auto] gap-2 items-end">
            <div><Label className="mono-label">Service</Label><Input value={pkg.description} onChange={(e) => setPkg((p) => ({ ...p, description: e.target.value }))} className="mt-1.5" data-testid="package-desc" /></div>
            <div><Label className="mono-label">Detail</Label><Input value={pkg.sub} onChange={(e) => setPkg((p) => ({ ...p, sub: e.target.value }))} className="mt-1.5" /></div>
            <div><Label className="mono-label">Qty</Label><Input type="number" value={pkg.qty} onChange={(e) => setPkg((p) => ({ ...p, qty: e.target.value }))} className="mt-1.5" /></div>
            <div><Label className="mono-label">Rate</Label><Input type="number" value={pkg.rate} onChange={(e) => setPkg((p) => ({ ...p, rate: e.target.value }))} className="mt-1.5" /></div>
            <Button onClick={addPackage} className="rounded-full" data-testid="add-package-button"><Plus size={16} /></Button>
          </div>
          <div className="divide-y divide-foreground/10">
            {packages.map((p) => (
              <div key={p.id} className="flex items-center justify-between py-3">
                <div><div className="font-medium">{p.description}</div><div className="mono-label">{p.sub} · {p.qty} × {p.rate}</div></div>
                <button onClick={() => delPackage(p.id)} className="p-2 hover:text-[#C04C20]" data-testid={`del-package-${p.id}`}><Trash2 size={16} /></button>
              </div>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="data" className="mt-6 space-y-3">
          <p className="text-sm text-muted-foreground">Export all your data.</p>
          <div className="flex flex-wrap gap-3">
            <a href={`${API}/export/documents.csv`}><Button variant="outline" className="rounded-full gap-2" data-testid="export-docs-csv"><Download size={15} /> Documents CSV</Button></a>
            <a href={`${API}/export/documents.json`}><Button variant="outline" className="rounded-full gap-2" data-testid="export-docs-json"><Download size={15} /> Documents JSON</Button></a>
            <a href={`${API}/export/clients.csv`}><Button variant="outline" className="rounded-full gap-2" data-testid="export-clients-csv"><Download size={15} /> Clients CSV</Button></a>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
