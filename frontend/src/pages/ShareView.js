import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { API } from "@/lib/api";
import axios from "axios";
import DocumentCanvas from "@/components/DocumentCanvas";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";

export default function ShareView() {
  const { token } = useParams();
  const [doc, setDoc] = useState(null);
  const [err, setErr] = useState(false);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    axios.get(`${API}/share/${token}`).then((r) => setDoc(r.data)).catch(() => setErr(true));
    const onResize = () => setScale(Math.min(1, Math.min(window.innerWidth - 24, 900) / 794));
    onResize(); window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [token]);

  if (err) return <div className="min-h-screen flex items-center justify-center mono-label">Document not found.</div>;
  if (!doc) return <div className="min-h-screen flex items-center justify-center mono-label">Loading…</div>;

  return (
    <div className="min-h-screen" style={{ background: doc.theme === "dark" ? "#141210" : "#E7E0D3" }}>
      <header className="flex items-center justify-between px-6 h-16 bg-background/80 backdrop-blur border-b border-foreground/10 sticky top-0 z-10">
        <div className="headline text-xl">Studio<span className="dotaccent">.</span></div>
        <div className="flex gap-2">
          <a href={`${API}/share/${token}/pdf?size=A4`} target="_blank" rel="noreferrer">
            <Button size="sm" className="rounded-full gap-2" data-testid="share-download-a4"><Download size={14} /> PDF A4</Button>
          </a>
          <a href={`${API}/share/${token}/pdf?size=Letter`} target="_blank" rel="noreferrer">
            <Button size="sm" variant="outline" className="rounded-full gap-2" data-testid="share-download-letter"><Download size={14} /> US Letter</Button>
          </a>
        </div>
      </header>
      <div className="py-8 px-2 overflow-x-auto">
        <div style={{ zoom: scale }}>
          <DocumentCanvas doc={doc} currency={doc.currency} theme={doc.theme} discount={doc.discount} tax={doc.tax} editable={false} />
        </div>
      </div>
    </div>
  );
}
