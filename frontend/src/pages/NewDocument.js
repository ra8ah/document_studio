import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { DOC_TYPES } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

export default function NewDocument() {
  const [type, setType] = useState(null);
  const [clientId, setClientId] = useState("none");
  const [theme, setTheme] = useState("light");
  const [clients, setClients] = useState([]);
  const [creating, setCreating] = useState(false);
  const nav = useNavigate();

  // client picker: first 100 clients alphabetically (API max page size)
  useEffect(() => { api.get("/clients", { params: { page_size: 100 } }).then((r) => setClients(r.data.items)); }, []);

  const create = async () => {
    if (!type) return toast.error("Choose a document type");
    setCreating(true);
    try {
      const { data } = await api.post("/documents", {
        type, theme, client_id: clientId === "none" ? null : clientId,
      });
      nav(`/documents/${data.id}`);
    } catch (e) { toast.error("Could not create document"); setCreating(false); }
  };

  return (
    <div className="rise space-y-8">
      <div>
        <div className="mono-label">Create / choose a type</div>
        <h1 className="headline text-4xl sm:text-5xl mt-2">
          New document<span className="dotaccent">.</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-2">Pick a type, choose a client, and start editing — three clicks.</p>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {DOC_TYPES.map((t) => {
          const selected = type === t.id;
          return (
            <button key={t.id} data-testid={`document-type-card-${t.id}`} onClick={() => setType(t.id)}
              className={`text-left rounded-2xl p-6 border transition-all duration-200 ${
                selected ? "bg-[#2C2824] text-[#F2ECE0] border-[#2C2824] scale-[1.02]" : "bg-card border-foreground/10 hover:border-foreground/30"
              }`}>
              <div className="flex items-center justify-between">
                <t.icon size={22} className={selected ? "text-[#E0673B]" : "text-[#C04C20]"} />
                <span className="mono-label" style={selected ? { color: "#A8A29A" } : {}}>{t.label.split(" ")[0]} / {t.code}</span>
              </div>
              <div className="headline text-xl mt-4">{t.label}</div>
              <div className="text-xs mt-2 opacity-70 leading-relaxed">{t.desc}</div>
            </button>
          );
        })}
      </div>

      <div className="sticky bottom-4 rounded-2xl border border-foreground/15 bg-background/90 backdrop-blur p-4 flex flex-wrap items-center gap-3">
        <div className="min-w-[200px] flex-1">
          <Select value={clientId} onValueChange={setClientId}>
            <SelectTrigger data-testid="new-doc-client-select" className="rounded-full"><SelectValue placeholder="Choose client (optional)" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">No client</SelectItem>
              {clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="flex rounded-full border border-foreground/15 p-1">
          {["light", "dark"].map((th) => (
            <button key={th} onClick={() => setTheme(th)} data-testid={`theme-${th}`}
              className={`px-4 py-1.5 rounded-full text-sm capitalize transition-colors ${theme === th ? "bg-primary text-primary-foreground" : ""}`}>{th}</button>
          ))}
        </div>
        <Button data-testid="create-document-button" onClick={create} disabled={creating || !type} className="rounded-full px-8">
          {creating ? "Creating…" : "Create & edit"}
        </Button>
      </div>
    </div>
  );
}
