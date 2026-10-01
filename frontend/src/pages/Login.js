import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const { login, user } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [show, setShow] = useState(false);

  useEffect(() => { if (user) nav("/", { replace: true }); }, [user, nav]);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true); setError("");
    const res = await login(email.trim(), password);
    setLoading(false);
    if (res.ok) { toast.success("Welcome back"); nav("/"); }
    else setError(res.error || "Login failed");
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-[#F2ECE0] text-[#201C18]">
      {/* Left editorial panel */}
      <div className="hidden lg:flex flex-col justify-between p-14 bg-[#201C18] text-[#F2ECE0]">
        <div className="mono-label" style={{ color: "#A8A29A" }}>Document System / 01</div>
        <div>
          <h1 className="headline text-5xl xl:text-6xl">
            Professional documents,<br />
            <span style={{ color: "#9A958C" }}>created in a few clicks</span>
            <span style={{ color: "#E0673B" }}>.</span>
          </h1>
          <p className="mt-6 text-sm max-w-md" style={{ color: "#B4B0A6" }}>
            Invoices, proposals, agreements and more — one design system, your brand,
            print-quality exports.
          </p>
        </div>
        <div className="mono-label" style={{ color: "#A8A29A" }}>Internal · Secure · Premium</div>
      </div>

      {/* Right form */}
      <div className="flex items-center justify-center p-8">
        <form onSubmit={submit} className="w-full max-w-sm rise">
          <div className="lg:hidden headline text-3xl mb-8">Studio<span className="dotaccent">.</span></div>
          <div className="mono-label mb-2 !text-[#5F5B54]">Sign in / Admin</div>
          <h2 className="headline text-3xl mb-8">Welcome back<span className="dotaccent">.</span></h2>
          <div className="space-y-4">
            <div>
              <Label htmlFor="email" className="mono-label !text-[#5F5B54]">Email</Label>
              <Input id="email" data-testid="login-email-input" type="email" value={email} autoComplete="email" inputMode="email"
                aria-invalid={!!error} aria-describedby={error ? "login-error" : undefined}
                onChange={(e) => setEmail(e.target.value)} className="mt-1.5 rounded-xl bg-white/50 border-[#201C18]/40" required />
            </div>
            <div>
              <Label htmlFor="password" className="mono-label !text-[#5F5B54]">Password</Label>
              <div className="relative mt-1.5">
                <Input id="password" data-testid="login-password-input" type={show ? "text" : "password"} value={password} autoComplete="current-password"
                  aria-invalid={!!error} aria-describedby={error ? "login-error" : undefined}
                  onChange={(e) => setPassword(e.target.value)} className="rounded-xl bg-white/50 border-[#201C18]/40 pr-11" required />
                <button type="button" onClick={() => setShow((v) => !v)} data-testid="toggle-password-visibility"
                  aria-label={show ? "Hide password" : "Show password"} aria-pressed={show} aria-controls="password"
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 p-2 rounded-full hover:bg-[#201C18]/5">
                  {show ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
                </button>
              </div>
            </div>
            <p id="login-error" role="alert" aria-live="assertive" className="text-sm text-[#A63F19] min-h-[1.25rem]" data-testid="login-error">{error}</p>
            <Button type="submit" data-testid="login-submit-button" disabled={loading}
              className="w-full rounded-full bg-[#201C18] hover:bg-[#2C2824] text-[#F2ECE0] h-11">
              {loading ? "Signing in…" : "Sign in"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
