import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { CURRENCIES } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Search, Plus, Pencil } from "lucide-react";
import { toast } from "sonner";
import Pager from "@/components/Pager";
import LoadError from "@/components/LoadError";

const PAGE_SIZE = 25;

const EMPTY = { name: "", company: "", email: "", phone: "", address: "", tax_id: "", currency: "INR", notes: "" };

export default function Clients() {
  const [clients, setClients] = useState([]);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState(null);
  const nav = useNavigate();

  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState(null);
  const [err, setErr] = useState(false);
  const load = (q = search, p = page) => api.get("/clients", { params: { search: q, page: p, page_size: PAGE_SIZE } })
    .then((r) => {
      // deleting the last row of the last page: step back a page
      if (r.data.items.length === 0 && p > 1) { setPage(p - 1); return; }
      setClients(r.data.items); setMeta(r.data); setErr(false);
    }).catch(() => setErr(true));
  useEffect(() => { setPage(1); }, [search]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { const t = setTimeout(() => load(search, page), 250); return () => clearTimeout(t); }, [search, page]);

  const openNew = () => { setForm(EMPTY); setEditId(null); setOpen(true); };
  const openEdit = (c) => { setForm({ ...EMPTY, ...c }); setEditId(c.id); setOpen(true); };

  const save = async () => {
    if (!form.name.trim()) return toast.error("Name is required");
    const payload = { ...form }; delete payload.id; delete payload.created_at;
    try {
      if (editId) await api.put(`/clients/${editId}`, payload);
      else await api.post("/clients", payload);
    } catch (e) {
      return toast.error(`Couldn't save the client${typeof e?.response?.data?.detail === "string" ? `: ${e.response.data.detail}` : ""}`);
    }
    toast.success("Client saved");
    setOpen(false);
    load(search);
  };

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="rise space-y-8">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="mono-label">Directory / 03</div>
          <h1 className="headline text-4xl sm:text-5xl mt-2">Clients<span className="dotaccent">.</span></h1>
        </div>
        <Button data-testid="new-client-button" onClick={openNew} className="rounded-full gap-2"><Plus size={16} /> New client</Button>
      </div>

      <div className="relative max-w-md">
        <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input data-testid="client-search-input" value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder="Search clients…" className="pl-11 rounded-full" />
      </div>

      <div className="rule" />
      {err ? (
        <LoadError onRetry={() => load()} testid="clients-load-error" />
      ) : clients.length === 0 ? (
        <div className="py-16 text-center text-muted-foreground">No clients yet.</div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {clients.map((c) => (
            <div key={c.id} data-testid={`client-card-${c.id}`}
              className="rounded-2xl border border-foreground/10 p-5 hover:border-foreground/30 transition-colors group">
              <div className="flex items-start justify-between">
                <button onClick={() => nav(`/clients/${c.id}`)} className="text-left">
                  <div className="font-medium text-lg">{c.name}</div>
                  <div className="text-sm text-muted-foreground">{c.company || c.email}</div>
                </button>
                <button onClick={() => openEdit(c)} data-testid={`edit-client-${c.id}`}
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-full hover:bg-foreground/5">
                  <Pencil size={15} />
                </button>
              </div>
              <div className="mono-label mt-4">{c.currency} · {c.phone || "no phone"}</div>
            </div>
          ))}
        </div>
      )}
      <Pager meta={meta} onPage={setPage} testid="clients-pager" />

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>{editId ? "Edit client" : "New client"}</DialogTitle></DialogHeader>
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="sm:col-span-2"><Label className="mono-label">Name</Label>
              <Input data-testid="client-name-input" value={form.name} onChange={set("name")} className="mt-1.5" /></div>
            <div><Label className="mono-label">Company</Label><Input value={form.company} onChange={set("company")} className="mt-1.5" /></div>
            <div><Label className="mono-label">Email</Label><Input value={form.email} onChange={set("email")} className="mt-1.5" /></div>
            <div><Label className="mono-label">Phone</Label><Input value={form.phone} onChange={set("phone")} className="mt-1.5" /></div>
            <div><Label className="mono-label">Tax ID</Label><Input value={form.tax_id} onChange={set("tax_id")} className="mt-1.5" /></div>
            <div className="sm:col-span-2"><Label className="mono-label">Address</Label><Textarea value={form.address} onChange={set("address")} className="mt-1.5" /></div>
            <div><Label className="mono-label">Currency</Label>
              <Select value={form.currency} onValueChange={(v) => setForm((f) => ({ ...f, currency: v }))}>
                <SelectTrigger className="mt-1.5" data-testid="client-currency-select"><SelectValue /></SelectTrigger>
                <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button data-testid="save-client-button" onClick={save} className="rounded-full">Save client</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
