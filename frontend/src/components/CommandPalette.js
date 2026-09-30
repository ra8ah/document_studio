import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { DOC_TYPES } from "@/lib/format";
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import { LayoutDashboard, Users, FileText, Settings as Cog } from "lucide-react";

export default function CommandPalette({ open, setOpen }) {
  const nav = useNavigate();

  const go = (path) => { setOpen(false); nav(path); };

  const createDoc = async (type) => {
    setOpen(false);
    const { data } = await api.post("/documents", { type, theme: "light" });
    nav(`/documents/${data.id}`);
  };

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Type a command or search…" data-testid="command-input" />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Navigate">
          <CommandItem onSelect={() => go("/")}><LayoutDashboard className="mr-2 h-4 w-4" />Dashboard</CommandItem>
          <CommandItem onSelect={() => go("/documents")}><FileText className="mr-2 h-4 w-4" />All documents</CommandItem>
          <CommandItem onSelect={() => go("/clients")}><Users className="mr-2 h-4 w-4" />Clients</CommandItem>
          <CommandItem onSelect={() => go("/settings")}><Cog className="mr-2 h-4 w-4" />Settings</CommandItem>
        </CommandGroup>
        <CommandGroup heading="Create new">
          {DOC_TYPES.map((t) => (
            <CommandItem key={t.id} onSelect={() => createDoc(t.id)} data-testid={`palette-new-${t.id}`}>
              <t.icon className="mr-2 h-4 w-4" />New {t.label}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
