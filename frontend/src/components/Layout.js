import { useEffect, useState } from "react";
import { Outlet, useNavigate, useLocation, Link } from "react-router-dom";
import { LayoutDashboard, FileText, Users, Settings as Cog, Moon, Sun, Command, LogOut, Plus, Menu } from "lucide-react";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import CommandPalette from "@/components/CommandPalette";
import { Button } from "@/components/ui/button";

const NAV = [
  { to: "/", label: "Dashboard", code: "01", icon: LayoutDashboard },
  { to: "/documents", label: "Documents", code: "02", icon: FileText },
  { to: "/clients", label: "Clients", code: "03", icon: Users },
  { to: "/settings", label: "Settings", code: "04", icon: Cog },
];

export default function Layout() {
  const { logout } = useAuth();
  const { dark, toggle } = useTheme();
  const nav = useNavigate();
  const loc = useLocation();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const h = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  const active = (to) => (to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(to));

  return (
    <div className="min-h-screen flex bg-background text-foreground">
      <CommandPalette open={paletteOpen} setOpen={setPaletteOpen} />

      {/* Sidebar */}
      <aside className="hidden md:flex flex-col w-64 border-r border-foreground/10 p-6 sticky top-0 h-screen">
        <Link to="/" className="headline text-2xl mb-10" data-testid="brand-logo">
          Studio<span className="dotaccent">.</span>
        </Link>
        <nav className="flex flex-col gap-1">
          {NAV.map((n) => (
            <Link
              key={n.to}
              to={n.to}
              data-testid={`nav-${n.label.toLowerCase()}`}
              className={`group flex items-center gap-3 rounded-full px-4 py-2.5 transition-all duration-200 ${
                active(n.to) ? "bg-primary text-primary-foreground" : "hover:bg-foreground/5"
              }`}
            >
              <n.icon size={17} />
              <span className="text-sm font-medium">{n.label}</span>
              <span className="mono-label ml-auto opacity-60">{n.code}</span>
            </Link>
          ))}
        </nav>
        <div className="mt-auto flex flex-col gap-2">
          <button onClick={toggle} data-testid="theme-toggle" className="flex items-center gap-3 rounded-full px-4 py-2.5 hover:bg-foreground/5 text-sm">
            {dark ? <Sun size={17} /> : <Moon size={17} />} {dark ? "Light mode" : "Dark mode"}
          </button>
          <button onClick={() => { logout(); nav("/login"); }} data-testid="logout-button" className="flex items-center gap-3 rounded-full px-4 py-2.5 hover:bg-foreground/5 text-sm">
            <LogOut size={17} /> Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="flex items-center gap-3 px-4 sm:px-10 h-16 border-b border-foreground/10 sticky top-0 bg-background/85 backdrop-blur z-20">
          {/* Mobile navigation (sidebar is hidden below md) */}
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <button className="md:hidden p-2 -ml-1 rounded-full hover:bg-foreground/5" aria-label="Open navigation" data-testid="mobile-nav-button"><Menu size={20} /></button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 p-6 flex flex-col" data-testid="mobile-nav">
              <SheetTitle className="headline text-2xl mb-8 text-left">Studio<span className="dotaccent">.</span></SheetTitle>
              <nav className="flex flex-col gap-1">
                {NAV.map((n) => (
                  <Link key={n.to} to={n.to} onClick={() => setMenuOpen(false)} data-testid={`mobile-nav-${n.label.toLowerCase()}`}
                    className={`flex items-center gap-3 rounded-full px-4 py-3 ${active(n.to) ? "bg-primary text-primary-foreground" : "hover:bg-foreground/5"}`}>
                    <n.icon size={17} /><span className="text-sm font-medium">{n.label}</span>
                  </Link>
                ))}
              </nav>
              <div className="mt-auto flex flex-col gap-2">
                <button onClick={toggle} className="flex items-center gap-3 rounded-full px-4 py-3 hover:bg-foreground/5 text-sm">
                  {dark ? <Sun size={17} /> : <Moon size={17} />} {dark ? "Light mode" : "Dark mode"}
                </button>
                <button onClick={() => { setMenuOpen(false); logout(); nav("/login"); }} data-testid="mobile-logout-button" className="flex items-center gap-3 rounded-full px-4 py-3 hover:bg-foreground/5 text-sm">
                  <LogOut size={17} /> Sign out
                </button>
              </div>
            </SheetContent>
          </Sheet>
          <button
            onClick={() => setPaletteOpen(true)}
            data-testid="command-palette-button"
            className="flex items-center gap-2 rounded-full border border-foreground/15 px-4 py-2 text-sm text-muted-foreground hover:border-foreground/30 transition-colors"
          >
            <Command size={14} /><span className="hidden sm:inline">Quick actions</span> <kbd className="mono-label ml-2 hidden sm:inline">⌘K</kbd>
          </button>
          <div className="ml-auto flex items-center gap-2">
            <Button data-testid="new-document-button" onClick={() => nav("/documents/new")} className="rounded-full gap-2">
              <Plus size={16} /><span className="hidden sm:inline">New document</span>
            </Button>
          </div>
        </header>
        <main className="flex-1 p-6 sm:p-10 lg:p-12 max-w-[1400px] w-full mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
