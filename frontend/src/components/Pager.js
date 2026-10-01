import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";

/** Prev / next pager for paginated API envelopes ({ items, total, page, page_size, pages }). */
export default function Pager({ meta, onPage, testid = "pager" }) {
  if (!meta || meta.total === 0) return null;
  const { page, pages, total, page_size: size } = meta;
  const from = (page - 1) * size + 1;
  const to = Math.min(total, page * size);
  return (
    <div className="flex items-center justify-between gap-3 pt-2" data-testid={testid}>
      <span className="mono-label" data-testid={`${testid}-summary`}>{from}–{to} of {total}</span>
      {pages > 1 && (
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="rounded-full gap-1" disabled={page <= 1}
            onClick={() => onPage(page - 1)} data-testid={`${testid}-prev`}><ChevronLeft size={14} /> Prev</Button>
          <span className="mono-label" data-testid={`${testid}-page`}>{page} / {pages}</span>
          <Button variant="outline" size="sm" className="rounded-full gap-1" disabled={page >= pages}
            onClick={() => onPage(page + 1)} data-testid={`${testid}-next`}>Next <ChevronRight size={14} /></Button>
        </div>
      )}
    </div>
  );
}
