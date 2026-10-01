import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { API } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import DocumentCanvas from "@/components/DocumentCanvas";
import { DownloadMenu } from "@/components/DownloadMenu";
import LoadError from "@/components/LoadError";
import usePrintSetup from "@/hooks/usePrintSetup";
import { CURRENCIES, STATUSES, STATUS_META, TYPE_MAP } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  ArrowLeft, Save, Share2, MoreVertical, Plus, Copy, RefreshCw, BadgeCheck, Trash2, Package, Sun, Moon, Loader2, Eraser,
} from "lucide-react";
import { toast } from "sonner";

const CONVERT_LABEL = { quotation: "invoice", proposal: "statement_of_work", invoice: "receipt" };
const AUTOSAVE_MS = 1500;
const MAX_ATTEMPTS = 5;
const UNDO_MS = 10000;
const draftKey = (id) => `docstudio:draft:${id}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// localStorage can throw (private mode, quota, disabled storage) — never let it break editing
const readDraft = (id) => { try { const v = localStorage.getItem(draftKey(id)); return v ? JSON.parse(v) : null; } catch { return null; } };
const writeDraft = (id, v) => { try { localStorage.setItem(draftKey(id), JSON.stringify(v)); } catch { /* ignore */ } };
const clearDraft = (id) => { try { localStorage.removeItem(draftKey(id)); } catch { /* ignore */ } };

const ago = (t) => {
  if (!t) return "";
  const s = Math.round((Date.now() - t) / 1000);
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  return m < 60 ? `${m}m ago` : `${Math.round(m / 60)}h ago`;
};
const detailOf = (e) => {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : d?.message || (Array.isArray(d) ? d.map((x) => x.msg).join(" ") : null);
};

export default function DocumentEditor() {
  const { id } = useParams();
  const nav = useNavigate();
  const { setUser } = useAuth();
  const canvasRef = useRef(null);
  const [doc, setDoc] = useState(null);
  const [loadErr, setLoadErr] = useState(null); // null | "notfound" | "error"
  const [canvasKey, setCanvasKey] = useState(0);
  const [currency, setCurrency] = useState("INR");
  const [theme, setTheme] = useState("light");
  const [pageSize, setPageSize] = useState("A4");
  const [status, setStatus] = useState("draft");
  const [discount, setDiscount] = useState({ enabled: false, mode: "percent", value: 0, label: "Discount" });
  const [tax, setTax] = useState({ enabled: false, mode: "percent", value: 0, label: "Tax" });
  const [packages, setPackages] = useState([]);
  const [shareOpen, setShareOpen] = useState(false);
  const [shareLink, setShareLink] = useState("");
  const [scale, setScale] = useState(1);
  // save state machine: idle | dirty | saving | saved | error | conflict
  const [save, setSave] = useState({ state: "idle", at: null, msg: "" });
  const [, tick] = useState(0);
  const [draftOffer, setDraftOffer] = useState(null);
  const [conflictOpen, setConflictOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [resetMode, setResetMode] = useState(null); // second-confirm step for sent/paid docs

  // refs: latest values for the async save engine
  const live = useRef({});
  live.current = { currency, theme, pageSize, discount, tax, status };
  const updatedAtRef = useRef(null);
  const dirtyRef = useRef(false);
  const timerRef = useRef(null);
  const chainRef = useRef(Promise.resolve(true));
  const loadedRef = useRef(false);
  const lastKeyRef = useRef(null); // JSON of the last loaded/saved payload: edits are only "dirty" if content differs

  const applyDoc = useCallback((d, { remount = true } = {}) => {
    setDoc(d); setCurrency(d.currency); setTheme(d.theme); setStatus(d.status);
    setPageSize(d.page_size === "Letter" ? "Letter" : "A4");
    if (d.discount) setDiscount((x) => ({ ...x, ...d.discount }));
    if (d.tax) setTax((x) => ({ ...x, ...d.tax }));
    updatedAtRef.current = d.updated_at;
    if (remount) setCanvasKey((k) => k + 1);
  }, []);

  const load = useCallback(() => {
    setLoadErr(null); loadedRef.current = false;
    api.get(`/documents/${id}`).then((r) => {
      const d = r.data;
      applyDoc(d);
      const draft = readDraft(id);
      const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
      const draftIsSaved = draft?.payload && Object.entries(draft.payload.data || {}).every(([k, v]) => same(v, d.data?.[k]))
        && same(draft.payload.line_items, d.line_items);
      if (draftIsSaved) clearDraft(id); // e.g. the keepalive save on unload landed after all
      else if (draft && draft.payload) setDraftOffer({ ...draft, serverChanged: draft.base_updated_at !== d.updated_at });
      setTimeout(() => { loadedRef.current = true; }, 0);
    }).catch((e) => setLoadErr(e?.response?.status === 404 || e?.response?.status === 422 ? "notfound" : "error"));
    api.get("/packages").then((r) => setPackages(r.data)).catch(() => {});
  }, [id, applyDoc]);

  useEffect(() => {
    load();
    const onResize = () => { const w = Math.min(window.innerWidth - 40, 900); setScale(Math.min(1, w / 816)); };
    onResize(); window.addEventListener("resize", onResize);
    const t = setInterval(() => tick((n) => n + 1), 30000);
    return () => { window.removeEventListener("resize", onResize); clearInterval(t); };
  }, [load]);

  usePrintSetup({ size: pageSize, theme });

  // ---------------------------------------------------------------- save engine
  const buildPayload = () => {
    const c = canvasRef.current?.collect();
    if (!c || !c.data || Object.keys(c.data).length === 0) return null; // empty-overwrite guard
    const { currency: cu, theme: th, pageSize: ps, discount: di, tax: tx } = live.current;
    return { data: c.data, line_items: c.line_items, currency: cu, theme: th, page_size: ps, discount: di, tax: tx };
  };

  const doSave = async (force = false) => {
    if (!dirtyRef.current && !force) return true;
    const payload = buildPayload();
    if (!payload) return !dirtyRef.current;
    dirtyRef.current = false; // edits made while this request is in flight re-mark it
    setSave((s) => ({ ...s, state: "saving" }));
    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
      try {
        const { data: updated } = await api.put(`/documents/${id}`, {
          ...payload, expected_updated_at: updatedAtRef.current, ...(force ? { force: true } : {}),
        });
        updatedAtRef.current = updated.updated_at;
        lastKeyRef.current = JSON.stringify(payload);
        setDoc((d) => ({ ...d, ...updated, data: updated.data })); // no remount: keep caret/DOM
        if (!dirtyRef.current) clearDraft(id);
        setSave({ state: dirtyRef.current ? "dirty" : "saved", at: Date.now(), msg: "" });
        return true;
      } catch (e) {
        const code = e?.response?.status;
        if (code === 409) {
          dirtyRef.current = true;
          setSave({ state: "conflict", at: null, msg: "This document changed elsewhere" });
          setConflictOpen(true);
          return false;
        }
        if (code === 401) {
          dirtyRef.current = true; // draft stays in localStorage and is offered after re-login
          setSave({ state: "error", at: null, msg: "Session expired" });
          toast.error("Your session expired — log in again. Your unsaved changes are kept on this device.");
          setUser(false);
          return false;
        }
        if (code === 404 || code === 422) {
          dirtyRef.current = true;
          const msg = code === 404 ? "This document no longer exists" : (detailOf(e) || "The server rejected these changes");
          setSave({ state: "error", at: null, msg });
          toast.error(`Not saved: ${msg}`);
          return false;
        }
        // network error or 5xx: exponential backoff 0.5s, 1s, 2s, 4s
        if (attempt < MAX_ATTEMPTS) { await sleep(500 * 2 ** (attempt - 1)); continue; }
        dirtyRef.current = true;
        setSave({ state: "error", at: null, msg: "Not saved" });
        toast.error("Couldn't save your changes. They are kept on this device.", {
          action: { label: "Retry", onClick: () => flush() },
        });
        return false;
      }
    }
    return false;
  };

  // serialize: never overlap requests, each run sends the latest state
  const runSave = (force = false) => {
    chainRef.current = chainRef.current.then(() => doSave(force), () => doSave(force));
    return chainRef.current;
  };
  const flush = (force = false) => { clearTimeout(timerRef.current); return runSave(force); };

  const markDirty = () => {
    if (!loadedRef.current) return;
    const p = buildPayload();
    // no real change (mount effects, focus/blur, re-formatting, printing) -> no autosave
    if (!p) return;
    const key = JSON.stringify(p);
    if (lastKeyRef.current === null) { lastKeyRef.current = key; return; } // first snapshot after (re)mount is the baseline
    if (key === lastKeyRef.current && !dirtyRef.current) return;
    dirtyRef.current = true;
    if (p) writeDraft(id, { payload: p, base_updated_at: updatedAtRef.current, saved_at: Date.now() });
    setSave((s) => (s.state === "saving" || s.state === "conflict" ? s : { ...s, state: "dirty" }));
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => runSave(), AUTOSAVE_MS);
  };
  const markDirtyRef = useRef(markDirty);
  markDirtyRef.current = markDirty;

  // settings changes count as edits — compared with the values the document was loaded/reset with,
  // so loading, remounting or a no-op change never triggers an autosave
  const baselineRef = useRef("");
  const settingsKey = JSON.stringify({ currency, theme, pageSize, discount, tax });
  useEffect(() => {
    baselineRef.current = settingsKey;
    lastKeyRef.current = null;
    const t = setTimeout(() => { const p = buildPayload(); lastKeyRef.current = p ? JSON.stringify(p) : null; }, 0);
    return () => clearTimeout(t);
    /* eslint-disable-next-line */
  }, [canvasKey]);
  useEffect(() => {
    if (settingsKey !== baselineRef.current) { baselineRef.current = settingsKey; markDirtyRef.current(); }
  }, [settingsKey]);

  // keepalive flush for tab hide / route change / unload (fire-and-forget, survives navigation)
  const keepaliveSave = useCallback(() => {
    if (!dirtyRef.current) return;
    const p = (() => { try { return buildPayload(); } catch { return null; } })();
    if (!p) return;
    writeDraft(id, { payload: p, base_updated_at: updatedAtRef.current, saved_at: Date.now() });
    clearTimeout(timerRef.current);
    try {
      fetch(`${API}/documents/${id}`, {
        method: "PUT", keepalive: true, credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...p, expected_updated_at: updatedAtRef.current }),
      }).then(async (r) => {
        if (r.ok) { const u = await r.json(); updatedAtRef.current = u.updated_at; dirtyRef.current = false; clearDraft(id); setSave({ state: "saved", at: Date.now(), msg: "" }); }
      }).catch(() => {});
    } catch { /* draft is in localStorage */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    const onBeforeUnload = (e) => { if (dirtyRef.current) { keepaliveSave(); e.preventDefault(); e.returnValue = ""; } };
    const onVis = () => { if (document.visibilityState === "hidden") keepaliveSave(); };
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); dirtyRef.current = true; flush().then((ok) => ok && toast.success("Saved")); }
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("keydown", onKey);
      keepaliveSave(); // leaving the editor (route change)
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keepaliveSave]);

  if (loadErr) return <LoadError notFound={loadErr === "notfound"} message={loadErr === "notfound" ? "Document not found. It may have been deleted." : undefined} onRetry={load} testid="editor-load-error" />;
  if (!doc) return <div className="mono-label" role="status">Loading…</div>;
  const meta = TYPE_MAP[doc.type] || {};
  const showLineItems = meta.layout === "financial" || ["proposal", "maintenance_plan", "statement_of_work"].includes(doc.type);
  const isContent = meta.layout === "content";
  const saving = save.state === "saving";

  // ---------------------------------------------------------------- actions
  const ensureSaved = async () => {
    const ok = await flush();
    if (!ok) toast.error("Couldn't save your latest changes — action cancelled so nothing is left out.");
    return ok;
  };
  const guard = (fn, failMsg) => async (...a) => {
    try { await fn(...a); } catch (e) { toast.error(`${failMsg}${detailOf(e) ? `: ${detailOf(e)}` : ""}`); }
  };

  const setStatusNow = guard(async (sNew) => {
    const prev = status;
    if (!(await ensureSaved())) return; // status change bumps updated_at: save pending edits first to avoid a false 409
    setStatus(sNew);
    try {
      const { data } = await api.post(`/documents/${id}/status`, { status: sNew });
      updatedAtRef.current = data.updated_at;
      toast.success(`Marked ${STATUS_META[sNew].label.toLowerCase()}`);
    } catch (e) { setStatus(prev); throw e; } // roll back
  }, "Couldn't change status");

  const exportDocx = async () => { if (await ensureSaved()) window.open(`${API}/documents/${id}/docx`, "_blank"); };

  const share = guard(async () => {
    if (!(await ensureSaved())) return;
    const { data } = await api.post(`/documents/${id}/share`);
    setShareLink(`${window.location.origin}/share/${data.token}`); setShareOpen(true);
    if (status === "draft") setStatusNow("sent");
  }, "Couldn't create share link");
  const duplicate = guard(async () => {
    if (!(await ensureSaved())) return;
    const { data } = await api.post(`/documents/${id}/duplicate`); toast.success("Duplicated"); nav(`/documents/${data.id}`);
  }, "Couldn't duplicate");
  const convert = guard(async () => {
    if (!(await ensureSaved())) return;
    const { data } = await api.post(`/documents/${id}/convert`, {}); toast.success("Converted"); nav(`/documents/${data.id}`);
  }, "Couldn't convert");
  const markPaid = guard(async () => {
    if (!(await ensureSaved())) return;
    const { data } = await api.post(`/documents/${id}/mark-paid`);
    setStatus("paid");
    toast.success("Marked paid" + (data.receipt ? " · receipt created" : ""));
    if (data.receipt) nav(`/documents/${data.receipt.id}`);
  }, "Couldn't mark as paid");
  const remove = guard(async () => {
    clearTimeout(timerRef.current); dirtyRef.current = false;
    await api.delete(`/documents/${id}`); clearDraft(id); toast.success("Deleted"); nav("/documents");
  }, "Couldn't delete");

  const doReset = guard(async (mode) => {
    setResetOpen(false); setResetMode(null);
    clearTimeout(timerRef.current);
    await chainRef.current;
    const snap = buildPayload(); // includes on-screen unsaved edits
    const { data } = await api.post(`/documents/${id}/reset`, { mode });
    dirtyRef.current = false; clearDraft(id);
    loadedRef.current = false; applyDoc(data); setTimeout(() => { loadedRef.current = true; }, 0);
    setSave({ state: "saved", at: Date.now(), msg: "" });
    toast.success(mode === "blank" ? "Cleared — blank document" : "Reset to template defaults", {
      duration: UNDO_MS,
      action: snap ? { label: "Undo", onClick: () => undoReset(snap) } : undefined,
    });
  }, "Couldn't reset the document");
  const undoReset = guard(async (snap) => {
    const { data } = await api.put(`/documents/${id}`, { ...snap, expected_updated_at: updatedAtRef.current, force: true });
    loadedRef.current = false; applyDoc(data); setTimeout(() => { loadedRef.current = true; }, 0);
    toast.success("Restored previous content");
  }, "Couldn't undo");
  const askReset = (mode) => {
    if (["paid", "sent", "viewed"].includes(status) && resetMode !== mode) { setResetMode(mode); return; }
    doReset(mode);
  };

  const restoreDraft = () => {
    const p = draftOffer.payload;
    setDraftOffer(null);
    loadedRef.current = false;
    applyDoc({ ...doc, ...p, data: { ...doc.data, ...p.data } });
    setTimeout(() => { loadedRef.current = true; dirtyRef.current = true; flush(); }, 50);
    toast.success("Unsaved changes restored");
  };
  const discardDraft = () => { clearDraft(id); setDraftOffer(null); };

  const s = STATUS_META[status] || STATUS_META.draft;
  const label = {
    idle: "", dirty: "Unsaved changes", saving: "Saving…", saved: `Saved · ${ago(save.at)}`,
    error: save.msg === "Not saved" ? "Not saved" : `Not saved — ${save.msg}`, conflict: "Changed elsewhere",
  }[save.state];

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

        <Select value={pageSize} onValueChange={setPageSize}>
          <SelectTrigger className="w-[110px] rounded-full h-9" data-testid="page-size-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="A4" data-testid="page-size-a4">A4</SelectItem>
            <SelectItem value="Letter" data-testid="page-size-letter">US Letter</SelectItem>
          </SelectContent>
        </Select>

        <button onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))} data-testid="doc-theme-toggle"
          className="p-2 rounded-full hover:bg-foreground/5 border border-foreground/15" title="Toggle paper theme">
          {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
        </button>

        <div role="status" aria-live="polite" className="flex items-center gap-2 text-xs ml-1" data-testid="save-status" data-state={save.state}>
          {saving && <Loader2 size={12} className="animate-spin" />}
          <span className={save.state === "error" || save.state === "conflict" ? "text-[#C04C20] font-medium" : "text-muted-foreground"}>{label}</span>
          {(save.state === "error") && (
            <button className="underline text-[#C04C20]" onClick={() => flush()} data-testid="save-retry">Retry</button>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2 flex-wrap">
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
          {status === "draft" && (
            <Button variant="outline" size="sm" className="rounded-full gap-1 text-[#C04C20] border-[#C04C20]/40 hover:bg-[#C04C20]/10" disabled={saving}
              onClick={() => { setResetMode(null); setResetOpen(true); }} data-testid="reset-button"><Eraser size={14} /> Clear &amp; start fresh</Button>
          )}

          <DownloadMenu size={pageSize} pdfPath={`/documents/${id}/pdf`} beforeDownload={ensureSaved} onDocx={exportDocx} />

          <Button variant="outline" size="sm" className="rounded-full gap-1" onClick={share} data-testid="share-button"><Share2 size={14} /> Share</Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="outline" size="sm" className="rounded-full px-2" data-testid="more-menu"><MoreVertical size={16} /></Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={duplicate} data-testid="duplicate-doc"><Copy size={14} className="mr-2" /> Duplicate</DropdownMenuItem>
              {CONVERT_LABEL[doc.type] && <DropdownMenuItem onClick={convert} data-testid="convert-doc"><RefreshCw size={14} className="mr-2" /> Convert to {TYPE_MAP[CONVERT_LABEL[doc.type]].label}</DropdownMenuItem>}
              {doc.type === "invoice" && <DropdownMenuItem onClick={markPaid} data-testid="mark-paid"><BadgeCheck size={14} className="mr-2" /> Mark as paid</DropdownMenuItem>}
              <DropdownMenuSeparator />
              <DropdownMenuItem disabled={saving} onClick={() => { setResetMode(null); setResetOpen(true); }} className="text-[#C04C20]" data-testid="reset-doc"><Eraser size={14} className="mr-2" /> Clear &amp; start fresh</DropdownMenuItem>
              <DropdownMenuItem onClick={() => setDeleteOpen(true)} className="text-[#C04C20]" data-testid="delete-doc"><Trash2 size={14} className="mr-2" /> Delete</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <Button size="sm" className="rounded-full gap-1" onClick={() => { dirtyRef.current = true; flush().then((ok) => ok && toast.success("Saved")); }} disabled={saving} data-testid="save-document-button">
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
          <span className="mono-label self-center ml-auto text-muted-foreground">Click any text on the page to edit · changes save automatically</span>
        </div>
      )}

      {/* Canvas */}
      <div className="py-8 px-2 overflow-x-auto" style={{ background: theme === "dark" ? "#141210" : "#E7E0D3" }}>
        <div className="doc-zoom" style={{ zoom: scale }}>
          <DocumentCanvas key={canvasKey} ref={canvasRef} doc={doc} currency={currency} theme={theme} discount={discount} tax={tax} size={pageSize} editable onChange={() => markDirtyRef.current()} />
        </div>
      </div>

      <Dialog open={shareOpen} onOpenChange={setShareOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Private share link</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Anyone with this link can view this document and print or save it as a PDF.</p>
          <div className="flex gap-2">
            <Input value={shareLink} readOnly data-testid="share-link-input" className="rounded-full" />
            <Button className="rounded-full" onClick={() => { navigator.clipboard?.writeText(shareLink).then(() => toast.success("Copied"), () => toast.error("Copy failed — select the link and copy it manually")); }} data-testid="copy-share-link">Copy</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Restore local draft */}
      <AlertDialog open={!!draftOffer}>
        <AlertDialogContent data-testid="draft-restore-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Restore unsaved changes?</AlertDialogTitle>
            <AlertDialogDescription>
              This device has changes from {draftOffer ? new Date(draftOffer.saved_at).toLocaleString() : ""} that were not saved.
              {draftOffer?.serverChanged ? " The saved document has also changed since then; restoring will replace those changes." : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={discardDraft} data-testid="draft-discard">Discard</AlertDialogCancel>
            <AlertDialogAction onClick={restoreDraft} data-testid="draft-restore">Restore unsaved changes</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 409 conflict */}
      <AlertDialog open={conflictOpen} onOpenChange={setConflictOpen}>
        <AlertDialogContent data-testid="conflict-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>This document changed elsewhere</AlertDialogTitle>
            <AlertDialogDescription>It was saved from another tab or device after you opened it. Reload to see the newer version (your edits here are discarded), or overwrite it with what is on this screen.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => { dirtyRef.current = false; clearDraft(id); setSave({ state: "idle", at: null, msg: "" }); load(); }} data-testid="conflict-reload">Reload</AlertDialogCancel>
            <AlertDialogAction onClick={() => { dirtyRef.current = true; flush(true); }} data-testid="conflict-overwrite">Overwrite</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete */}
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent data-testid="delete-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {doc.number}?</AlertDialogTitle>
            <AlertDialogDescription>This permanently deletes the document and its share link. This can't be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={remove} className="bg-[#C04C20] hover:bg-[#a63f19]" data-testid="delete-confirm">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Clear & start fresh */}
      <AlertDialog open={resetOpen} onOpenChange={(o) => { setResetOpen(o); if (!o) setResetMode(null); }}>
        <AlertDialogContent data-testid="reset-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>{resetMode ? `This document is ${STATUS_META[status]?.label.toLowerCase()}` : "Clear & start fresh"}</AlertDialogTitle>
            <AlertDialogDescription>
              {resetMode
                ? "It has already been sent to (or paid by) the client. Resetting changes what they may have seen. Are you sure?"
                : "The number, client and status are kept. All content, line items, discount and tax are replaced. You can undo for 10 seconds."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="gap-2">
            <AlertDialogCancel data-testid="reset-cancel">Cancel</AlertDialogCancel>
            {resetMode ? (
              <Button className="rounded-md bg-[#C04C20] hover:bg-[#a63f19]" onClick={() => askReset(resetMode)} data-testid="reset-confirm-again">Yes, reset it</Button>
            ) : (<>
              <Button variant="outline" disabled={saving} onClick={() => askReset("defaults")} data-testid="reset-defaults">Reset to template defaults</Button>
              <Button disabled={saving} className="bg-[#C04C20] hover:bg-[#a63f19]" onClick={() => askReset("blank")} data-testid="reset-blank">Completely blank</Button>
            </>)}
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
