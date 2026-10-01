import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Printer, Loader2 } from "lucide-react";
import { printDocument } from "@/lib/print";

/** Single "Print / Save as PDF" action with a short print-dialog hint. */
export default function PrintButton({ size = "A4", variant = "outline", className = "" }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const go = async () => {
    setBusy(true);
    setOpen(false);
    try {
      // let the popover unmount before the print snapshot
      await new Promise((r) => setTimeout(r, 60));
      await printDocument();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant={variant} size="sm" className={`rounded-full gap-1 ${className}`} data-testid="print-button" disabled={busy}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Printer size={14} />} Print / Save as PDF
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 rounded-2xl" data-testid="print-hint">
        <div className="mono-label">In the print dialog</div>
        <ol className="mt-3 space-y-2 text-sm">
          <li className="flex gap-2"><span className="mono-label pt-0.5">01</span><span>Destination: <b>Save as PDF</b></span></li>
          <li className="flex gap-2"><span className="mono-label pt-0.5">02</span><span>Enable <b>Background graphics</b> <span className="text-muted-foreground">(“Print backgrounds” in Firefox / Safari)</span></span></li>
          <li className="flex gap-2"><span className="mono-label pt-0.5">03</span><span>Turn <b>Headers and footers</b> off</span></li>
        </ol>
        <div className="mt-3 text-xs text-muted-foreground">Paper: <b data-testid="print-hint-size">{size === "Letter" ? "US Letter" : "A4"}</b> · margins are set automatically.</div>
        <Button size="sm" className="rounded-full w-full mt-4 gap-1" onClick={go} data-testid="print-confirm">
          <Printer size={14} /> Open print dialog
        </Button>
      </PopoverContent>
    </Popover>
  );
}
