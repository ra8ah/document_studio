import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { API } from "@/lib/api";
import { money, fmtDate, TYPE_MAP, STATUS_META, STATUSES, DOC_TYPES } from "@/lib/format";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Search, Plus, Trash2, Download, X } from "lucide-react";
import { toast } from "sonner";
import Pager from "@/components/Pager";
import LoadError from "@/components/LoadError";
import { ListSkeleton } from "@/components/Skeletons";

const PAGE_SIZE = 25;

function BulkBar({ ids, onDone, onClear }) {
  const [busy, setBusy] = useState(false);
  const run = async (fn, ok) => {
    setBusy(true);
    try { await fn(); ok(); } catch { toast.error("Bulk action failed — nothing was changed on the failed items"); }
    setBusy(false);
  };
  const setStatus = (status) => run(() => api.post("/documents/bulk", { ids, action: "status", status }), () => {
    toast.success(`${ids.length} document(s) marked ${STATUS_META[status].label.toLowerCase()}`); onDone();
  });
  const trash = () => run(() => api.post("/documents/bulk", { ids, action: "trash" }), () => {
    const moved = [...ids];
    toast.success(`${moved.length} document(s) moved to Trash`, {
      duration: 10000,
      action: { label: "Undo", onClick: () => api.post("/trash/restore", { ids: moved, action: "restore" }).then(onDone, () => toast.error("Couldn't restore")) },
    });
    onDone();
  });
  const exportCsv = () => window.open(`${API}/export/documents.csv?ids=${ids.join(",")}`, "_blank");
  return (
    <div className="sticky top-16 z-10 flex flex-wrap items-center gap-3 rounded-full bg-primary text-primary-foreground px-4 py-2" role="region" aria-label="Bulk actions" data-testid="bulk-bar">
      <span className="text-sm font-medium" data-testid="bulk-count">{ids.length} selected</span>
      <Select onValueChange={setStatus} disabled={busy}>
        <SelectTrigger className="w-[160px] h-8 rounded-full bg-background text-foreground" data-testid="bulk-status-select" aria-label="Change status of selected"><SelectValue placeholder="Change status" /></SelectTrigger>
        <SelectContent>{STATUSES.map((s) => <SelectItem key={s} value={s} data-testid={`bulk-status-${s}`}>{STATUS_META[s].label}</SelectItem>)}</SelectContent>
      </Select>
      <Button size="sm" variant="secondary" className="rounded-full gap-1 h-8" disabled={busy} onClick={trash} data-testid="bulk-trash"><Trash2 size={14} /> Move to Trash</Button>
      <Button size="sm" variant="secondary" className="rounded-full gap-1 h-8" disabled={busy} onClick={exportCsv} data-testid="bulk-export"><Download size={14} /> Export CSV</Button>
      <button className="ml-auto p-1.5 rounded-full hover:bg-background/20" onClick={onClear} aria-label="Clear selection" data-testid="bulk-clear"><X size={16} /></button>
    </div>
  );
}

export default function DocumentsList() {
  const [docs, setDocs] = useState([]);
  const [search, setSearch] = useState("");
  const [type, setType] = useState("all");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState("-created_at");
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(false);
  const [reload, setReload] = useState(0);
  const [sel, setSel] = useState(() => new Set());
  const nav = useNavigate();

  // any filter change starts again from page 1
  useEffect(() => { setPage(1); }, [search, type, status, sort]);

  useEffect(() => {
    // AbortController: a slower, older search can never overwrite the newer result
    const ctrl = new AbortController();
    setLoading(true);
    const t = setTimeout(() => api.get("/documents", {
      signal: ctrl.signal,
      params: { search, type: type === "all" ? "" : type, status: status === "all" ? "" : status, sort, page, page_size: PAGE_SIZE },
    }).then((r) => { setDocs(r.data.items); setMeta(r.data); setErr(false); setLoading(false); })
      .catch((e) => { if (e?.code === "ERR_CANCELED" || ctrl.signal.aborted) return; setErr(true); setLoading(false); }), 200);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [search, type, status, sort, page, reload]);

  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const allOnPage = docs.length > 0 && docs.every((d) => sel.has(d.id));
  const toggleAll = () => setSel((s) => { const n = new Set(s); docs.forEach((d) => (allOnPage ? n.delete(d.id) : n.add(d.id))); return n; });
  const done = () => { setSel(new Set()); setReload((n) => n + 1); };

  return (
    <div className="rise space-y-8">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="mono-label">Library / 02</div>
          <h1 className="headline text-4xl sm:text-5xl mt-2">Documents<span className="dotaccent">.</span></h1>
        </div>
        <Button data-testid="new-document-list-button" onClick={() => nav("/documents/new")} className="rounded-full gap-2"><Plus size={16} /> New document</Button>
      </div>

      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input data-testid="doc-search-input" aria-label="Search documents" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search number, client, reference…" className="pl-11 rounded-full" />
        </div>
        <Select value={type} onValueChange={setType}>
          <SelectTrigger className="w-[180px] rounded-full" data-testid="filter-type" aria-label="Filter by type"><SelectValue placeholder="Type" /></SelectTrigger>
          <SelectContent><SelectItem value="all">All types</SelectItem>{DOC_TYPES.map((t) => <SelectItem key={t.id} value={t.id}>{t.label}</SelectItem>)}</SelectContent>
        </Select>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-[150px] rounded-full" data-testid="filter-status" aria-label="Filter by status"><SelectValue placeholder="Status" /></SelectTrigger>
          <SelectContent><SelectItem value="all">All status</SelectItem>{STATUSES.map((s) => <SelectItem key={s} value={s}>{STATUS_META[s].label}</SelectItem>)}</SelectContent>
        </Select>
        <Select value={sort} onValueChange={setSort}>
          <SelectTrigger className="w-[160px] rounded-full" data-testid="filter-sort" aria-label="Sort"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="-created_at">Newest first</SelectItem>
            <SelectItem value="created_at">Oldest first</SelectItem>
            <SelectItem value="-number">Number ↓</SelectItem>
            <SelectItem value="number">Number ↑</SelectItem>
            <SelectItem value="-total">Amount ↓</SelectItem>
            <SelectItem value="total">Amount ↑</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {sel.size > 0 && <BulkBar ids={[...sel]} onDone={done} onClear={() => setSel(new Set())} />}

      <div className="rule relative flex items-center">
        {docs.length > 0 && !err && (
          <label className="absolute -top-7 left-0 flex items-center gap-2 mono-label cursor-pointer">
            <Checkbox checked={allOnPage} onCheckedChange={toggleAll} data-testid="select-all" aria-label="Select all on this page" /> Select page
          </label>
        )}
        {loading && meta && <span className="absolute right-0 -top-5 mono-label" role="status" data-testid="documents-refreshing">Updating…</span>}
      </div>
      {err ? (
        <LoadError onRetry={() => setReload((n) => n + 1)} testid="documents-load-error" />
      ) : loading && !meta ? (
        <ListSkeleton testid="documents-loading" />
      ) : docs.length === 0 ? (
        <div className="py-16 text-center text-muted-foreground">No documents match.</div>
      ) : (
        <div className="divide-y divide-foreground/10">
          {docs.map((r) => {
            const t = TYPE_MAP[r.type];
            const s = STATUS_META[r.status] || STATUS_META.draft;
            return (
              <div key={r.id} className={`flex items-center gap-3 ${sel.has(r.id) ? "bg-foreground/[0.04]" : ""}`}>
                <Checkbox checked={sel.has(r.id)} onCheckedChange={() => toggle(r.id)} data-testid={`select-doc-${r.id}`} aria-label={`Select ${r.number}`} />
                <button onClick={() => nav(`/documents/${r.id}`)} data-testid={`doc-row-${r.id}`}
                  className="flex-1 min-w-0 grid grid-cols-[1fr_auto] sm:grid-cols-[auto_1fr_120px_110px_130px] items-center gap-4 py-4 text-left motion-safe:transition-[padding] hover:pl-2">
                  {t && <t.icon size={18} className="text-muted-foreground hidden sm:block" aria-hidden="true" />}
                  <div className="min-w-0">
                    <div className="font-medium truncate">{r.client_name || t?.label}</div>
                    <div className="mono-label">{r.number} · {t?.label}</div>
                  </div>
                  <div className="mono-label hidden sm:block">{fmtDate(r.created_at)}</div>
                  <span className="text-xs px-2.5 py-1 rounded-full justify-self-start" style={{ color: s.color, background: s.bg }}>{s.label}</span>
                  <span className="font-medium text-right">{r.total ? money(r.total, r.currency) : "—"}</span>
                </button>
              </div>
            );
          })}
        </div>
      )}
      <Pager meta={meta} onPage={setPage} testid="documents-pager" />
    </div>
  );
}
