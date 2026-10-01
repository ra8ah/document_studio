import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";

const isTyping = (el) => !!el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.closest?.("[contenteditable=true],[role=textbox],[role=combobox],[role=listbox],[role=menu]"));
const MOD = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl";

const LIST = [
  [[MOD, "K"], "Open command palette"],
  [[MOD, "S"], "Save the document (editor)"],
  [["N"], "New document"],
  [["G", "D"], "Go to Dashboard"],
  [["G", "C"], "Go to Clients"],
  [["G", "S"], "Go to Settings"],
  [["G", "T"], "Go to Trash"],
  [["?"], "Show this list"],
];
const GO = { d: "/", c: "/clients", s: "/settings", t: "/trash" };

/** Global single-key shortcuts. Ignored while typing in inputs or editable regions, or with modifiers. */
export function useShortcuts() {
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const pendingG = useRef(0);
  useEffect(() => {
    const h = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.defaultPrevented || isTyping(e.target)) return;
      if (document.querySelector("[role=dialog],[role=alertdialog]") && e.key !== "?") return;
      const k = e.key.toLowerCase();
      if (e.key === "?") { e.preventDefault(); setOpen((o) => !o); return; }
      if (Date.now() - pendingG.current < 1200 && GO[k]) { e.preventDefault(); pendingG.current = 0; nav(GO[k]); return; }
      if (k === "g") { pendingG.current = Date.now(); return; }
      if (k === "n") { e.preventDefault(); nav("/documents/new"); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [nav]);
  return [open, setOpen];
}

export function ShortcutsDialog({ open, setOpen }) {
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-md" data-testid="shortcuts-dialog">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>Single-key shortcuts are off while you type in a field or on the document.</DialogDescription>
        </DialogHeader>
        <dl className="divide-y divide-foreground/10">
          {LIST.map(([keys, label]) => (
            <div key={label} className="flex items-center justify-between py-2.5 text-sm">
              <dt>{label}</dt>
              <dd className="flex gap-1">{keys.map((k, i) => (
                <span key={i} className="flex items-center gap-1">{i > 0 && keys[0] === "G" && <span className="text-muted-foreground text-xs">then</span>}
                  <kbd className="min-w-6 px-1.5 py-0.5 rounded-md border border-foreground/20 bg-foreground/5 font-mono text-xs text-center">{k}</kbd></span>
              ))}</dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  );
}
