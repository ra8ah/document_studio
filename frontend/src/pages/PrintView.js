import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { API } from "@/lib/api";
import DocumentCanvas from "@/components/DocumentCanvas";
import usePrintSetup from "@/hooks/usePrintSetup";
import { waitForPrintAssets } from "@/lib/print";

const addMeta = (name, content) => {
  const m = document.createElement("meta");
  m.name = name; m.content = content; m.dataset.printRoute = "1";
  document.head.appendChild(m);
};

/** Headless-Chromium render target for server PDFs. Token arrives in the #fragment (never sent to the host). */
export default function PrintView() {
  const { id } = useParams();
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get("t") || "");
  const size = new URLSearchParams(window.location.search).get("size") === "Letter" ? "Letter" : "A4";
  const [doc, setDoc] = useState(null);
  const html = document.documentElement;

  useEffect(() => {
    addMeta("robots", "noindex, nofollow");
    addMeta("referrer", "no-referrer");
    if (window.location.hash) window.history.replaceState(null, "", window.location.pathname + window.location.search);
    axios.get(`${API}/print/${id}`, { headers: { "X-Print-Token": token } })
      .then((r) => setDoc(r.data))
      .catch(() => { html.dataset.printReady = "error"; });
    return () => {
      document.querySelectorAll("meta[data-print-route]").forEach((m) => m.remove());
      delete html.dataset.printReady;
    };
  }, [id, token, html]);

  usePrintSetup({ size, theme: doc?.theme, mode: "server" });

  useEffect(() => {
    if (!doc) return;
    waitForPrintAssets(document.querySelector("[data-print-target]")).then(() => { html.dataset.printReady = "1"; });
  }, [doc, html]);

  if (!doc) return <div className="mono-label p-8" data-testid="print-view-loading">Preparing…</div>;
  return (
    <div data-testid="print-view">
      <DocumentCanvas doc={doc} currency={doc.currency} theme={doc.theme} discount={doc.discount} tax={doc.tax} size={size} editable={false} />
    </div>
  );
}
