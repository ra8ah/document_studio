import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { money, fmtDate, TYPE_MAP } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { RotateCcw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import LoadError from "@/components/LoadError";
import { ListSkeleton } from "@/components/Skeletons";

export default function Trash() {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(false);
  const [confirm, setConfirm] = useState(null);

  const load = useCallback(() => {
    setErr(false);
    api.get("/trash").then((r) => setRows(r.data)).catch(() => setErr(true));
  }, []);
  useEffect(() => { load(); }, [load]);

  const restore = async (d) => {
    try {
      await api.post(`/documents/${d.id}/restore`);
      setRows((r) => r.filter((x) => x.id !== d.id));
      toast.success(`${d.number} restored`);
    } catch { toast.error("Couldn't restore the document"); }
  };
  const purge = async (d) => {
    setConfirm(null);
    try {
      await api.delete(`/documents/${d.id}/permanent`);
      setRows((r) => r.filter((x) => x.id !== d.id));
      toast.success(`${d.number} deleted permanently`);
    } catch { toast.error("Couldn't delete the document"); }
  };

  return (
    <div className="rise space-y-8">
      <div>
        <div className="mono-label">Recovery / 05</div>
        <h1 className="headline text-4xl sm:text-5xl mt-2">Trash<span className="dotaccent">.</span></h1>
        <p className="text-sm text-muted-foreground mt-3">Deleted documents stay here for 30 days, then they are removed for good.</p>
      </div>
      <div className="rule" />
      {err ? <LoadError onRetry={load} testid="trash-load-error" />
        : rows === null ? <ListSkeleton rows={4} />
        : rows.length === 0 ? <div className="py-16 text-center text-muted-foreground" data-testid="trash-empty">Trash is empty.</div>
        : (
          <ul className="divide-y divide-foreground/10" data-testid="trash-list">
            {rows.map((d) => {
              const t = TYPE_MAP[d.type];
              return (
                <li key={d.id} className="flex flex-wrap items-center gap-4 py-4" data-testid={`trash-row-${d.id}`}>
                  <div className="min-w-0 flex-1">
                    <div className="font-medium truncate">{d.client_name || t?.label}</div>
                    <div className="mono-label">{d.number} · {t?.label} · deleted {fmtDate(d.deleted_at)} · {d.days_left} days left</div>
                  </div>
                  <span className="font-medium">{d.total ? money(d.total, d.currency) : "—"}</span>
                  <Button size="sm" variant="outline" className="rounded-full gap-1" onClick={() => restore(d)} data-testid={`trash-restore-${d.id}`}><RotateCcw size={14} /> Restore</Button>
                  <Button size="sm" variant="outline" className="rounded-full gap-1 text-[#A63F19] border-[#A63F19]/40" onClick={() => setConfirm(d)} data-testid={`trash-purge-${d.id}`}><Trash2 size={14} /> Delete permanently</Button>
                </li>
              );
            })}
          </ul>
        )}
      <AlertDialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
        <AlertDialogContent data-testid="purge-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {confirm?.number} permanently?</AlertDialogTitle>
            <AlertDialogDescription>This can't be undone. The document and its share link are removed for good.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction className="bg-[#A63F19] hover:bg-[#8a3415]" onClick={() => purge(confirm)} data-testid="purge-confirm">Delete permanently</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
