import { useRef, useState } from "react";
import api from "@/lib/api";
import { printDocument } from "@/lib/print";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ChevronDown, Download, FileText, Loader2, Printer } from "lucide-react";
import { toast } from "sonner";

const SLOW_MS = 6000; // free-tier hosts sleep: tell the user why it is taking long
const TIMEOUT_MS = 120000;

const filenameFrom = (cd, fallback) => {
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd || "");
  if (star) { try { return decodeURIComponent(star[1]); } catch { /* fall through */ } }
  const plain = /filename="?([^";]+)"?/i.exec(cd || "");
  return plain ? plain[1] : fallback;
};

const errorText = async (e) => {
  if (e?.code === "ECONNABORTED") return "the server took too long";
  const blob = e?.response?.data;
  if (blob instanceof Blob) { try { return JSON.parse(await blob.text()).detail; } catch { /* ignore */ } }
  return e?.response ? `server error ${e.response.status}` : "the server could not be reached";
};

const printNow = () => setTimeout(() => printDocument(), 80); // let the menu close before the print snapshot

/** Split "Download PDF" control: server PDF (main), A4/Letter, browser Print…, optional Word. */
export function DownloadMenu({ size = "A4", pdfPath, beforeDownload, onDocx, variant = "default" }) {
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);
  const busyRef = useRef(false);

  const download = async (sz) => {
    if (busyRef.current) return;
    if (beforeDownload && !(await beforeDownload())) return; // latest edits must be in the file
    busyRef.current = true; setBusy(true);
    const t = setTimeout(() => setSlow(true), SLOW_MS);
    try {
      const r = await api.get(pdfPath, { params: { size: sz }, responseType: "blob", timeout: TIMEOUT_MS });
      const url = URL.createObjectURL(new Blob([r.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = filenameFrom(r.headers["content-disposition"], "document.pdf");
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (e) {
      toast.error(`Couldn't create the PDF — ${await errorText(e)}.`, {
        duration: 10000, action: { label: "Print instead", onClick: printNow },
      });
    } finally {
      clearTimeout(t); busyRef.current = false; setBusy(false); setSlow(false);
    }
  };

  const items = (
    <DropdownMenuContent align="end" className="w-64">
      <DropdownMenuItem onClick={() => download("A4")} data-testid="download-pdf-a4"><Download size={14} className="mr-2" /> Download PDF (A4)</DropdownMenuItem>
      <DropdownMenuItem onClick={() => download("Letter")} data-testid="download-pdf-letter"><Download size={14} className="mr-2" /> Download PDF (US Letter)</DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem onClick={printNow} data-testid="print-browser" className="flex-col items-start gap-0.5">
        <span className="flex items-center"><Printer size={14} className="mr-2" /> Print…</span>
        <span className="text-xs text-muted-foreground pl-6" data-testid="print-hint">Choose Save as PDF as the destination.</span>
      </DropdownMenuItem>
      {onDocx && (<>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onDocx} data-testid="download-docx"><FileText size={14} className="mr-2" /> Download Word (.docx)</DropdownMenuItem>
      </>)}
    </DropdownMenuContent>
  );
  const icon = busy ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />;
  const label = busy ? (slow ? "Waking up server…" : "Preparing PDF…") : null;

  return (
    <>
      <div className="hidden md:inline-flex items-center" data-testid="download-split">
        <Button variant={variant} size="sm" className="rounded-l-full rounded-r-none gap-1" disabled={busy}
          onClick={() => download(size)} data-testid="download-pdf-button" aria-busy={busy}
          title={slow ? "The PDF server is starting up — this can take up to a minute" : `Download PDF (${size === "Letter" ? "US Letter" : "A4"})`}>
          {icon} {label || "Download PDF"}
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant={variant} size="sm" className="rounded-r-full rounded-l-none px-2 border-l border-l-background/30" disabled={busy}
              data-testid="download-menu-trigger" aria-label="More download options"><ChevronDown size={14} /></Button>
          </DropdownMenuTrigger>
          {items}
        </DropdownMenu>
      </div>
      <div className="md:hidden">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant={variant} size="sm" className="rounded-full gap-1" disabled={busy} data-testid="download-menu-mobile">
              {icon} {label || "Download"}
            </Button>
          </DropdownMenuTrigger>
          {items}
        </DropdownMenu>
      </div>
    </>
  );
}
