import axios from "axios";

// Empty REACT_APP_BACKEND_URL => relative "/api" (Vercel rewrites it to the backend, cookies stay first-party).
const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");
export const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API, withCredentials: true });

// Access tokens live 60 min; on a 401, refresh once (single-flight) and replay the request,
// so reloading the page after an hour keeps the session (refresh token lasts 7 days).
let refreshing = null;
const NO_RETRY = ["/auth/login", "/auth/refresh", "/auth/logout"];
api.interceptors.response.use(undefined, async (error) => {
  const cfg = error.config;
  const status = error.response?.status;
  if (status !== 401 || !cfg || cfg.__retried || NO_RETRY.some((u) => (cfg.url || "").endsWith(u))) {
    throw error;
  }
  cfg.__retried = true;
  refreshing = refreshing || api.post("/auth/refresh").finally(() => { refreshing = null; });
  try {
    await refreshing;
  } catch {
    throw error;
  }
  return api(cfg);
});

export function formatApiError(detail) {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).filter(Boolean).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export default api;
