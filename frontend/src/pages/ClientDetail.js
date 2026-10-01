import { useEffect, useState } from "react";
import LoadError from "@/components/LoadError";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { money, fmtDate, TYPE_MAP, STATUS_META } from "@/lib/format";
import { ArrowLeft } from "lucide-react";

export default function ClientDetail() {
  const { id } = useParams();
  const [client, setClient] = useState(null);
  const [docs, setDocs] = useState([]);
  const [err, setErr] = useState(null);
  const [reload, setReload] = useState(0);
  const nav = useNavigate();

  useEffect(() => {
    setErr(null);
    api.get(`/clients/${id}`).then((r) => setClient(r.data)).catch((e) => setErr(e?.response?.status === 404 ? "notfound" : "error"));
    api.get(`/clients/${id}/documents`).then((r) => setDocs(r.data)).catch(() => {});
  }, [id, reload]);

  if (err) return <LoadError notFound={err === "notfound"} message={err === "notfound" ? "Client not found." : undefined} onRetry={() => setReload((n) => n + 1)} testid="client-load-error" />;
  if (!client) return <div className="mono-label" role="status">Loading…</div>;

  return (
    <div className="rise space-y-8">
      <button onClick={() => nav("/clients")} className="flex items-center gap-2 mono-label hover:text-[#C04C20]">
        <ArrowLeft size={14} /> Back to clients
      </button>
      <div>
        <div className="mono-label">Client / {client.currency}</div>
        <h1 className="headline text-4xl sm:text-5xl mt-2">{client.name}<span className="dotaccent">.</span></h1>
        <div className="grid sm:grid-cols-3 gap-6 mt-6 text-sm">
          <div><div className="mono-label mb-1">Company</div>{client.company || "—"}</div>
          <div><div className="mono-label mb-1">Email</div>{client.email || "—"}</div>
          <div><div className="mono-label mb-1">Phone</div>{client.phone || "—"}</div>
          <div className="sm:col-span-2"><div className="mono-label mb-1">Address</div><span className="whitespace-pre-line">{client.address || "—"}</span></div>
          <div><div className="mono-label mb-1">Tax ID</div>{client.tax_id || "—"}</div>
        </div>
      </div>

      <div>
        <div className="mono-label">Documents / {docs.length}</div>
        <div className="rule mt-3" />
        {docs.length === 0 ? (
          <div className="py-12 text-center text-muted-foreground">No documents for this client yet.</div>
        ) : (
          <div className="divide-y divide-foreground/10">
            {docs.map((r) => {
              const t = TYPE_MAP[r.type];
              const s = STATUS_META[r.status] || STATUS_META.draft;
              return (
                <button key={r.id} onClick={() => nav(`/documents/${r.id}`)} data-testid={`client-doc-${r.id}`}
                  className="w-full flex items-center justify-between py-4 text-left hover:pl-2 transition-all">
                  <div className="flex items-center gap-4">
                    {t && <t.icon size={18} className="text-muted-foreground" />}
                    <div>
                      <div className="font-medium">{t?.label}</div>
                      <div className="mono-label">{r.number} · {fmtDate(r.created_at)}</div>
                    </div>
                  </div>
                  <span className="text-xs px-2.5 py-1 rounded-full" style={{ color: s.color, background: s.bg }}>{s.label}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
