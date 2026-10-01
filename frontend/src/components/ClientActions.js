import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Archive, ArchiveRestore, Trash2 } from "lucide-react";
import { toast } from "sonner";

/** Archive / unarchive + delete (blocked while the client still has documents). */
export function ClientActions({ client, onChange }) {
  const nav = useNavigate();
  const [ask, setAsk] = useState(null); // null | "delete" | {blocked}

  const setArchived = async (archived) => {
    try {
      const { data } = await api.post(`/clients/${client.id}/archive`, { archived });
      onChange(data); setAsk(null);
      toast.success(archived ? "Client archived — hidden from pickers, kept on existing documents" : "Client restored");
    } catch { toast.error("Couldn't update the client"); }
  };
  const remove = async () => {
    try {
      await api.delete(`/clients/${client.id}`);
      toast.success("Client deleted"); nav("/clients");
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (e?.response?.status === 409 && d) setAsk({ blocked: d });
      else { setAsk(null); toast.error("Couldn't delete the client"); }
    }
  };
  const blocked = ask && ask.blocked;

  return (
    <div className="flex flex-wrap gap-2">
      {client.archived
        ? <Button size="sm" variant="outline" className="rounded-full gap-1" onClick={() => setArchived(false)} data-testid="unarchive-client"><ArchiveRestore size={14} /> Unarchive</Button>
        : <Button size="sm" variant="outline" className="rounded-full gap-1" onClick={() => setArchived(true)} data-testid="archive-client"><Archive size={14} /> Archive</Button>}
      <Button size="sm" variant="outline" className="rounded-full gap-1 text-[#A63F19] border-[#A63F19]/40" onClick={() => setAsk("delete")} data-testid="delete-client"><Trash2 size={14} /> Delete</Button>
      <AlertDialog open={!!ask} onOpenChange={(o) => !o && setAsk(null)}>
        <AlertDialogContent data-testid={blocked ? "client-delete-blocked" : "client-delete-dialog"}>
          <AlertDialogHeader>
            <AlertDialogTitle>{blocked ? "This client can't be deleted" : `Delete ${client.name}?`}</AlertDialogTitle>
            <AlertDialogDescription data-testid="client-delete-message">
              {blocked
                ? `${client.name} still has ${blocked.document_count} document(s)${blocked.trashed_count ? ` and ${blocked.trashed_count} in Trash` : ""}. Archive the client instead: it disappears from pickers but stays on existing documents.`
                : "This permanently removes the client. Clients with documents can only be archived."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            {blocked
              ? (!client.archived && <AlertDialogAction onClick={() => setArchived(true)} data-testid="archive-instead">Archive client</AlertDialogAction>)
              : <Button className="bg-[#A63F19] hover:bg-[#8a3415]" onClick={remove} data-testid="client-delete-confirm">Delete</Button>}
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
