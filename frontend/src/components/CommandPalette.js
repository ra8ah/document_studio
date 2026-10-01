import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api from "@/lib/api";
import { DOC_TYPES, TYPE_MAP, STATUS_META } from "@/lib/format";
import {
  CommandDialog, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import { LayoutDashboard, Users, FileText, Settings as Cog, Trash2, Clock, Loader2 } from "lucide-react";

const NAV = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard },
  { path: "/documents", label: "All documents", icon: FileText },
  { path: "/clients", label: "Clients", icon: Users },
  { path: "/trash", label: "Trash", icon: Trash2 },
  { path: "/settings", label: "Settings", icon: Cog },
];
const match = (q, ...s) => !q || s.some((x) => (x || "").toLowerCase().includes(q.toLowerCase()));

const DocItem = ({ d, onSelect, prefix }) => {
  const t = TYPE_MAP[d.type];
  const Icon = t?.icon || FileText;
  return (
    <CommandItem value={`${prefix}-${d.id}`} onSelect={onSelect} data-testid={`palette-${prefix}-${d.id}`}>
      <Icon className="mr-2 h-4 w-4" />
      <span className="font-mono text-xs mr-2">{d.number}</span>
      <span className="truncate">{d.client_name || t?.label}</span>
      <span className="ml-auto text-xs text-muted-foreground">{STATUS_META[d.status]?.label}</span>
    </CommandItem>
  );
};

export default function CommandPalette({ open, setOpen }) {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [res, setRes] = useState({ documents: [], clients: [] });
  const [recent, setRecent] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) { setQ(""); setRes({ documents: [], clients: [] }); return; }
    api.get("/documents", { params: { sort: "-updated_at", page_size: 5 } }).then((r) => setRecent(r.data.items)).catch(() => {});
  }, [open]);

  useEffect(() => {
    if (!q.trim()) { setRes({ documents: [], clients: [] }); setBusy(false); return; }
    const ctrl = new AbortController();
    setBusy(true);
    const t = setTimeout(() => api.get("/search", { params: { q }, signal: ctrl.signal })
      .then((r) => { setRes(r.data); setBusy(false); })
      .catch((e) => { if (!ctrl.signal.aborted) setBusy(false); }), 200);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [q]);

  const go = (path) => { setOpen(false); nav(path); };
  const createDoc = async (type) => {
    setOpen(false);
    try {
      const { data } = await api.post("/documents", { type, theme: "light" });
      nav(`/documents/${data.id}`);
    } catch {
      toast.error("Couldn't create the document — please try again");
    }
  };

  const navItems = NAV.filter((n) => match(q, n.label));
  const createItems = DOC_TYPES.filter((t) => match(q, t.label, `new ${t.label}`));
  const nothing = !busy && q.trim() && !res.documents.length && !res.clients.length && !navItems.length && !createItems.length;

  return (
    <CommandDialog open={open} onOpenChange={setOpen} commandProps={{ shouldFilter: false, loop: true }}>
      <CommandInput placeholder="Search documents, clients or commands…" value={q} onValueChange={setQ} data-testid="command-input" aria-label="Search" />
      <CommandList>
        {busy && <div className="flex items-center gap-2 px-4 py-3 text-sm text-muted-foreground" role="status" data-testid="palette-searching"><Loader2 className="h-4 w-4 animate-spin" /> Searching…</div>}
        {nothing && (
          <div className="py-8 text-center text-sm" role="status" data-testid="palette-empty">
            No matches for “{q}”.<div className="text-muted-foreground text-xs mt-1">Try a document number, client name or reference.</div>
          </div>
        )}
        {!q.trim() && recent.length > 0 && (
          <CommandGroup heading="Recent">
            {recent.map((d) => <DocItem key={d.id} d={d} prefix="recent" onSelect={() => go(`/documents/${d.id}`)} />)}
          </CommandGroup>
        )}
        {res.documents.length > 0 && (
          <CommandGroup heading="Documents">
            {res.documents.map((d) => <DocItem key={d.id} d={d} prefix="doc" onSelect={() => go(`/documents/${d.id}`)} />)}
          </CommandGroup>
        )}
        {res.clients.length > 0 && (
          <CommandGroup heading="Clients">
            {res.clients.map((c) => (
              <CommandItem key={c.id} value={`client-${c.id}`} onSelect={() => go(`/clients/${c.id}`)} data-testid={`palette-client-${c.id}`}>
                <Users className="mr-2 h-4 w-4" />{c.name}<span className="ml-auto text-xs text-muted-foreground truncate">{c.company || c.email}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {navItems.length > 0 && (
          <CommandGroup heading="Navigate">
            {navItems.map((n) => (
              <CommandItem key={n.path} value={`nav-${n.path}`} onSelect={() => go(n.path)}><n.icon className="mr-2 h-4 w-4" />{n.label}</CommandItem>
            ))}
          </CommandGroup>
        )}
        {createItems.length > 0 && (
          <CommandGroup heading="Create new">
            {createItems.map((t) => (
              <CommandItem key={t.id} value={`new-${t.id}`} onSelect={() => createDoc(t.id)} data-testid={`palette-new-${t.id}`}>
                <t.icon className="mr-2 h-4 w-4" />New {t.label}
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {!q.trim() && <div className="px-4 py-2 text-[11px] text-muted-foreground border-t flex items-center gap-1"><Clock className="h-3 w-3" /> ↑↓ to move · Enter to open · Esc to close</div>}
      </CommandList>
    </CommandDialog>
  );
}
