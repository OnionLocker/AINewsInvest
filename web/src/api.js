const BASE = "";

function authHeaders() {
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(method, path, body = null, opts = {}) {
  const headers = { ...authHeaders(), ...opts.headers };
  if (body && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal: opts.signal,
  });
  if (res.status === 401) {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || JSON.stringify(err));
  }
  if (opts.raw) return res;
  return res.json();
}

const get = (p, o) => request("GET", p, null, o);
const post = (p, b, o) => request("POST", p, b, o);
const put = (p, b, o) => request("PUT", p, b, o);
const del = (p, o) => request("DELETE", p, null, o);

const api = {
  // auth
  bootstrapStatus: () => get("/api/auth/bootstrap-status"),
  bootstrapAdmin: (d) => post("/api/auth/bootstrap-admin", d),
  register: (d) => post("/api/auth/register", d),
  login: (d) => post("/api/auth/login", d),
  adminLogin: (d) => post("/api/auth/admin-login", d),
  me: () => get("/api/auth/me"),

  // market
  marketOverview: () => get("/api/market-overview"),
  stockQuery: (d) => post("/api/stock-query", d),

  // market sentiment
  marketSentiment: (market) => get(`/api/market-sentiment/${market}`),

  // recommendations (legacy)
  todayRecs: () => get("/api/recommendations/today"),
  recHistory: (limit = 20) => get(`/api/recommendations/history?limit=${limit}`),
  recByDate: (date) => get(`/api/recommendations/${date}`),

  // recommendations (market-scoped: market = "us" | "hk")
  marketTodayRecs: (market) => get(`/api/recommendations/${market}/today`),
  marketRecHistory: (market, limit = 20) =>
    get(`/api/recommendations/${market}/history?limit=${limit}`),
  marketRecByDate: (market, date) =>
    get(`/api/recommendations/${market}/${date}`),

  // screening
  runScreen: (d) => post("/api/screen", d),
  latestScreen: (market = "us_stock") =>
    get(`/api/screen/latest?market=${market}`),
  screenHistory: (limit = 20) => get(`/api/screen/history?limit=${limit}`),

  // analysis
  deepAnalysis: (d) => post("/api/deep-analysis", d),
  deepAnalysisStream: (d) => post("/api/deep-analysis-stream", d, { raw: true }),

  // watchlist
  addWatchlist: (d) => post("/api/watchlist", d),
  getWatchlist: () => get("/api/watchlist"),
  removeWatchlist: (id) => del(`/api/watchlist/${id}`),
  watchlistQuotes: () => get("/api/watchlist/quotes"),

  // performance
  performanceSummary: (market = "all") =>
    get(`/api/performance/summary?market=${market}`),

  // admin
  adminUsers: () => get("/api/admin/users"),
  adminSetActive: (username, active) =>
    put(`/api/admin/users/${username}/active?active=${active}`),
  adminDeleteUser: (username) => del(`/api/admin/users/${username}`),
  adminRunRecs: (d) => post("/api/admin/recommendations/run", d),
  adminTaskStatus: () => get("/api/admin/recommendations/task-status"),
  adminPublish: (refDate, market) =>
    post(`/api/admin/recommendations/publish?ref_date=${refDate || ""}&market=${market || "us_stock"}`),
  adminBothTables: (refDate, market) =>
    get(
      `/api/admin/recommendations/both-tables${refDate ? `?ref_date=${refDate}` : ""}${market ? `${refDate ? "&" : "?"}market=${market}` : ""}`,
    ),
};

export default api;
