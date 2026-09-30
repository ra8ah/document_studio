import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { money, fmtDate, TYPE_MAP, STATUS_META } from "@/lib/format";
import { AlertTriangle, ArrowUpRight, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

function Stat({ label, code, value, sub, dark }) {
  return (
    <div className={`rounded-2xl p-6 ${dark ? "bg-[#2C2824] text-[#F2ECE0]" : "bg-card border border-foreground/10"}`}>
      <div className="mono-label" style={dark ? { color: "#A8A29A" } : {}}>{label} / {code}</div>
      <div className="headline text-3xl sm:text-4xl mt-3">{value}</div>
      {sub && <div className="text-sm mt-1 opacity-70">{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const [d, setD] = useState(null);
  const nav = useNavigate();

  useEffect(() => {
    api.post("/recurring/run").catch(() => {});
    api.get("/dashboard").then((r) => setD(r.data));
  }, []);

  if (!d) return <div className="mono-label">Loading…</div>;
  const cur = d.currency;

  return (
    <div className="rise space-y-10">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="mono-label">Overview / 01</div>
          <h1 className="headline text-4xl sm:text-5xl mt-2">
            Your studio, <span className="text-muted-foreground">at a glance</span><span className="dotaccent">.</span>
          </h1>
        </div>
        <Button data-testid="dashboard-new-doc" onClick={() => nav("/documents/new")} className="rounded-full gap-2">
          <Plus size={16} /> New document
        </Button>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <Stat dark label="Revenue" code="this month" value={money(d.this_month_revenue, cur)} sub="Paid invoices & receipts" />
        <Stat label="Outstanding" code="total" value={money(d.outstanding, cur)} sub="Across unpaid invoices" />
        <Stat label="Unpaid" code="invoices" value={d.unpaid_count} sub="Awaiting payment" />
        <Stat label="Overdue" code="alerts" value={d.overdue_count} sub={d.overdue_count ? "Needs attention" : "All clear"} />
      </div>

      {d.overdue.length > 0 && (
        <div className="rounded-2xl border border-[#C04C20]/30 bg-[#C04C20]/5 p-6">
          <div className="flex items-center gap-2 mono-label text-[#C04C20]"><AlertTriangle size={14} /> Overdue / alerts</div>
          <div className="mt-4 divide-y divide-foreground/10">
            {d.overdue.map((o) => (
              <button key={o.id} onClick={() => nav(`/documents/${o.id}`)} data-testid={`overdue-${o.id}`}
                className="w-full flex items-center justify-between py-3 text-left hover:opacity-70">
                <div>
                  <span className="font-mono text-sm">{o.number}</span>
                  <span className="ml-3 text-sm text-muted-foreground">{o.client_name}</span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-sm text-muted-foreground">Due {fmtDate(o.due_date)}</span>
                  <span className="font-medium">{money(o.total, o.currency)}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="flex items-center justify-between">
          <div className="mono-label">Recent documents / 02</div>
          <button onClick={() => nav("/documents")} className="text-sm flex items-center gap-1 hover:text-[#C04C20]">
            View all <ArrowUpRight size={14} />
          </button>
        </div>
        <div className="rule mt-3" />
        {d.recent.length === 0 ? (
          <div className="py-16 text-center text-muted-foreground">
            <p>No documents yet.</p>
            <Button className="rounded-full mt-4" onClick={() => nav("/documents/new")}>Create your first document</Button>
          </div>
        ) : (
          <div className="divide-y divide-foreground/10">
            {d.recent.map((r) => {
              const t = TYPE_MAP[r.type];
              const s = STATUS_META[r.status] || STATUS_META.draft;
              return (
                <button key={r.id} onClick={() => nav(`/documents/${r.id}`)} data-testid={`recent-${r.id}`}
                  className="w-full flex items-center justify-between py-4 text-left hover:pl-2 transition-all">
                  <div className="flex items-center gap-4 min-w-0">
                    {t && <t.icon size={18} className="text-muted-foreground shrink-0" />}
                    <div className="min-w-0">
                      <div className="font-medium truncate">{r.client_name || t?.label}</div>
                      <div className="mono-label">{r.number} · {t?.label}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 shrink-0">
                    <span className="text-xs px-2.5 py-1 rounded-full" style={{ color: s.color, background: s.bg }}>{s.label}</span>
                    <span className="font-medium w-28 text-right">{r.total ? money(r.total, r.currency) : "—"}</span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
