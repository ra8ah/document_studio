import { useRef } from "react";
import DocumentCanvas from "@/components/DocumentCanvas";
import { DownloadMenu } from "@/components/DownloadMenu";
import { useZoom, ZoomFrame } from "@/components/Zoom";
import { STATUS_META, TYPE_MAP } from "@/lib/format";
import { ArrowLeft, Monitor } from "lucide-react";

/** Below md the editor is a read-only, fit-to-width preview. */
export default function MobileDocView({ doc, status, currency, theme, discount, tax, size, onBack }) {
  const box = useRef(null);
  const zoom = useZoom(box, size);
  const s = STATUS_META[status] || STATUS_META.draft;
  return (
    <div className="-m-6" data-testid="mobile-doc-view">
      <div className="sticky top-16 z-10 bg-background/95 border-b border-foreground/10 px-4 py-3 flex items-center gap-3">
        <button onClick={onBack} className="p-2 -ml-2 rounded-full hover:bg-foreground/5" aria-label="Back to documents" data-testid="editor-back"><ArrowLeft size={18} aria-hidden="true" /></button>
        <div className="min-w-0 flex-1">
          <div className="mono-label truncate">{TYPE_MAP[doc.type]?.label}</div>
          <div className="font-mono text-sm font-medium">{doc.number} <span className="ml-1 text-xs px-2 py-0.5 rounded-full" style={{ color: s.color, background: s.bg }}>{s.label}</span></div>
        </div>
        <DownloadMenu size={size} pdfPath={`/documents/${doc.id}/pdf`} />
      </div>
      <p className="flex items-center gap-2 px-4 py-2.5 text-xs bg-foreground/5" role="note" data-testid="mobile-edit-hint">
        <Monitor size={14} aria-hidden="true" /> Read-only on phones. Edit on a larger screen.
      </p>
      <div ref={box} className="py-4 overflow-hidden" style={{ background: theme === "dark" ? "#141210" : "#E7E0D3" }}>
        <ZoomFrame scale={zoom.scale}>
          <DocumentCanvas doc={doc} currency={currency} theme={theme} discount={discount} tax={tax} size={size} editable={false} />
        </ZoomFrame>
      </div>
    </div>
  );
}
