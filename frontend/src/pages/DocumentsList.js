import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { money, fmtDate, TYPE_MAP, STATUS_META, STATUSES, DOC_TYPES } from "@/lib/format";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Search, Plus } from "lucide-react";
import Pager from "@/components/Pager";
import LoadError from "@/components/LoadError";

const PAGE_SIZE = 25;

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
          <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input data-testid="doc-search-input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search number, client, reference…" className="pl-11 rounded-full" />
        </div>
        <Select value={type} onValueChange={setType}>
          <SelectTrigger className="w-[180px] rounded-full" data-testid="filter-type"><SelectValue placeholder="Type" /></SelectTrigger>
          <SelectContent><SelectItem value="all">All types</SelectItem>{DOC_TYPES.map((t) => <SelectItem key={t.id} value={t.id}>{t.label}</SelectItem>)}</SelectContent>
        </Select>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-[150px] rounded-full" data-testid="filter-status"><SelectValue placeholder="Status" /></SelectTrigger>
          <SelectContent><SelectItem value="all">All status</SelectItem>{STATUSES.map((s) => <SelectItem key={s} value={s}>{STATUS_META[s].label}</SelectItem>)}</SelectContent>
        </Select>
        <Select value={sort} onValueChange={setSort}>
          <SelectTrigger className="w-[160px] rounded-full" data-testid="filter-sort"><SelectValue /></SelectTrigger>
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

      <div className="rule relative">{loading && meta && <span className="absolute right-0 -top-5 mono-label" role="status" data-testid="documents-refreshing">Loading…</span>}</div>
      {err ? (
        <LoadError onRetry={() => setReload((n) => n + 1)} testid="documents-load-error" />
      ) : loading && !meta ? (
        <div className="py-16 text-center mono-label" role="status" data-testid="documents-loading">Loading…</div>
      ) : docs.length === 0 ? (
        <div className="py-16 text-center text-muted-foreground">No documents match.</div>
      ) : (
        <div className="divide-y divide-foreground/10">
          {docs.map((r) => {
            const t = TYPE_MAP[r.type];
            const s = STATUS_META[r.status] || STATUS_META.draft;
            return (
              <button key={r.id} onClick={() => nav(`/documents/${r.id}`)} data-testid={`doc-row-${r.id}`}
                className="w-full grid grid-cols-[1fr_auto] sm:grid-cols-[auto_1fr_120px_110px_130px] items-center gap-4 py-4 text-left hover:pl-2 transition-all">
                {t && <t.icon size={18} className="text-muted-foreground hidden sm:block" />}
                <div className="min-w-0">
                  <div className="font-medium truncate">{r.client_name || t?.label}</div>
                  <div className="mono-label">{r.number} · {t?.label}</div>
                </div>
                <div className="mono-label hidden sm:block">{fmtDate(r.created_at)}</div>
                <span className="text-xs px-2.5 py-1 rounded-full justify-self-start" style={{ color: s.color, background: s.bg }}>{s.label}</span>
                <span className="font-medium text-right">{r.total ? money(r.total, r.currency) : "—"}</span>
              </button>
            );
          })}
        </div>
      )}
      <Pager meta={meta} onPage={setPage} testid="documents-pager" />
    </div>
  );
}
