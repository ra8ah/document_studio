import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { API } from "@/lib/api";
import axios from "axios";
import DocumentCanvas from "@/components/DocumentCanvas";
import { DownloadMenu } from "@/components/DownloadMenu";
import usePrintSetup from "@/hooks/usePrintSetup";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export default function ShareView() {
  const { token } = useParams();
  const [doc, setDoc] = useState(null);
  const [err, setErr] = useState(false);
  const [scale, setScale] = useState(1);
  const [pageSize, setPageSize] = useState("A4");

  useEffect(() => {
    axios.get(`${API}/share/${token}`).then((r) => {
      setDoc(r.data);
      setPageSize(r.data.page_size === "Letter" ? "Letter" : "A4");
    }).catch(() => setErr(true));
    const onResize = () => setScale(Math.min(1, Math.min(window.innerWidth - 24, 900) / 816));
    onResize(); window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [token]);

  usePrintSetup({ size: pageSize, theme: doc?.theme === "dark" ? "dark" : "light" });

  if (err) return <div className="min-h-screen flex items-center justify-center mono-label">Document not found.</div>;
  if (!doc) return <div className="min-h-screen flex items-center justify-center mono-label">Loading…</div>;

  return (
    <div className="min-h-screen" style={{ background: doc.theme === "dark" ? "#141210" : "#E7E0D3" }}>
      <header className="flex items-center justify-between gap-2 px-4 sm:px-6 h-16 bg-background/80 backdrop-blur border-b border-foreground/10 sticky top-0 z-10">
        <div className="headline text-xl">Studio<span className="dotaccent">.</span></div>
        <div className="flex items-center gap-2">
          <Select value={pageSize} onValueChange={setPageSize}>
            <SelectTrigger className="w-[110px] rounded-full h-9" data-testid="share-page-size-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="A4">A4</SelectItem>
              <SelectItem value="Letter">US Letter</SelectItem>
            </SelectContent>
          </Select>
          <DownloadMenu size={pageSize} pdfPath={`/share/${token}/pdf`} />
        </div>
      </header>
      <div className="py-8 px-2 overflow-x-auto">
        <div className="doc-zoom" style={{ zoom: scale }}>
          <DocumentCanvas doc={doc} currency={doc.currency} theme={doc.theme} discount={doc.discount} tax={doc.tax} size={pageSize} editable={false} />
        </div>
      </div>
    </div>
  );
}
