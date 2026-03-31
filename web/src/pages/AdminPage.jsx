import { useState, useEffect, useRef } from "react";
import api from "../api";
import Card, { CardTitle } from "../components/Card";
import Spinner, { PageLoader } from "../components/Spinner";
import Badge, { MarketBadge, DirectionBadge, StrategyBadge } from "../components/Badge";
import { Shield, Users, Play, Upload, RefreshCw } from "lucide-react";

function UsersSection() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.adminUsers().then(setUsers).catch(() => {}).finally(() => setLoading(false));
  }, []);

  async function toggleActive(username, active) {
    try {
      await api.adminSetActive(username, active);
      setUsers((prev) =>
        prev.map((u) => (u.username === username ? { ...u, is_active: active } : u))
      );
    } catch (err) {
      alert(err.message);
    }
  }

  async function deleteUser(username) {
    if (!confirm("绾喖鐣鹃崚鐘绘珟閻€劍鍩� " + username + " ?")) return;
    try {
      await api.adminDeleteUser(username);
      setUsers((prev) => prev.filter((u) => u.username !== username));
    } catch (err) {
      alert(err.message);
    }
  }

  if (loading) return <Spinner />;

  return (
    <Card>
      <CardTitle><Users size={14} className="mr-1 inline" /> 閻€劍鍩涚粻锛勬倄1�7</CardTitle>
      <div className="space-y-2">
        {users.map((u) => (
          <div key={u.username} className="flex items-center justify-between rounded-xl border border-slate-800/60 bg-slate-950/50 px-3 py-2">
            <div>
              <span className="text-sm font-medium">{u.username}</span>
              {u.is_admin && <Badge variant="brand" className="ml-2">缁狅紕鎮婇崨锟�</Badge>}
              {!u.is_active && <Badge variant="red" className="ml-2">瀹歌尙顩﹂悽锟�</Badge>}
            </div>
            {!u.is_admin && (
              <div className="flex gap-2">
                <button
                  onClick={() => toggleActive(u.username, !u.is_active)}
                  className="text-xs text-slate-400 hover:text-indigo-400"
                >
                  {u.is_active ? "缁備胶鏁ￄ1�7" : "閸氼垳鏁ￄ1�7"}
                </button>
                <button
                  onClick={() => deleteUser(u.username)}
                  className="text-xs text-slate-400 hover:text-rose-400"
                >
                  閸掔娢�娅�
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

function RecommendationRunner() {
  const [market, setMarket] = useState("us_stock");
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState(null);
  const intervalRef = useRef(null);

  function startPolling() {
    intervalRef.current = setInterval(async () => {
      try {
        const s = await api.adminTaskStatus();
        setStatus(s);
        if (s.status === "done" || s.status === "failed" || s.status === "idle") {
          clearInterval(intervalRef.current);
          setRunning(false);
        }
      } catch {
        clearInterval(intervalRef.current);
        setRunning(false);
      }
    }, 2000);
  }

  useEffect(() => {
    api.adminTaskStatus().then(setStatus).catch(() => {});
    return () => clearInterval(intervalRef.current);
  }, []);

  async function handleRun() {
    setRunning(true);
    setStatus(null);
    try {
      await api.adminRunRecs({ market, force: false, note: "" });
      startPolling();
    } catch (err) {
      alert(err.message);
      setRunning(false);
    }
  }

  async function handlePublish() {
    try {
      const result = await api.adminPublish("", market);
      alert("瀹告彃褰傜敮锟� " + result.count + " 閺夆剝甯归懡锟� (" + market + ")");
    } catch (err) {
      alert(err.message);
    }
  }

  return (
    <Card>
      <CardTitle><Play size={14} className="mr-1 inline" /> 閹恒劏宕橢�悽鐔稿灇</CardTitle>
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label className="mb-1 block text-xs text-slate-400">鐢倸婧₄1�7</label>
          <select
            value={market}
            onChange={(e) => setMarket(e.target.value)}
            className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:border-indigo-500"
          >
            <option value="us_stock">缂囧氦鍋ￄ1�7</option>
            <option value="hk_stock">濞擃垵鍋ￄ1�7</option>
          </select>
        </div>
        <button
          onClick={handleRun}
          disabled={running}
          className="flex items-center gap-2 rounded-lg bg-indigo-500 px-4 py-2 text-sm text-white shadow-lg shadow-indigo-500/20 hover:bg-indigo-600 disabled:opacity-50"
        >
          {running ? <Spinner size="sm" /> : <Play size={16} />}
          {running ? "鏉╂劘顢戞稉锟�..." : "鏉╂劘顢戦幒銊ㄥ礄1�7"}
        </button>
        <button
          onClick={handlePublish}
          className="flex items-center gap-2 rounded-lg border border-indigo-500 px-4 py-2 text-sm text-indigo-400 hover:bg-indigo-500/10"
        >
          <Upload size={16} /> 閸欐垵绔ￄ1�7
        </button>
      </div>

      {status && status.status !== "idle" && (
        <div className="mt-4 rounded-xl border border-slate-800/60 bg-slate-950/50 p-3">
          <div className="flex items-center gap-2 text-sm">
            <Badge variant={status.status === "done" ? "green" : status.status === "failed" ? "red" : "yellow"}>
              {status.status}
            </Badge>
            {status.progress != null && (
              <span className="text-xs text-slate-400">{status.progress}%</span>
            )}
          </div>
          {status.message && (
            <p className="mt-1 text-xs text-slate-400">{status.message}</p>
          )}
        </div>
      )}
    </Card>
  );
}

function BothTablesView() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  async function loadTables() {
    setLoading(true);
    try {
      const d = await api.adminBothTables("");
      setData(d);
    } catch (err) {
      alert(err.message);
    }
    setLoading(false);
  }

  const tableLabel = { admin: "缁狅紕鎮婄粩锟�", published: "瀹告彃褰傜敮锟�" };

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <CardTitle className="!mb-0">缁狅紕鎮婄粩锟� vs 瀹告彃褰傜敮锟�</CardTitle>
        <button
          onClick={loadTables}
          disabled={loading}
          className="flex items-center gap-1 rounded-lg border border-slate-800 px-3 py-1.5 text-xs text-slate-400 hover:bg-slate-800/50"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          閸旂姾娴ￄ1�7
        </button>
      </div>

      {data && (
        <div className="grid gap-4 lg:grid-cols-2">
          {["admin", "published"].map((key) => (
            <div key={key}>
              <p className="mb-2 text-xs font-semibold text-slate-400 uppercase">{tableLabel[key]}</p>
              {data[key]?.items?.length > 0 ? (
                <div className="space-y-1">
                  {data[key].items.map((item, i) => (
                    <div key={i} className="flex items-center justify-between rounded-xl border border-slate-800/60 bg-slate-950/50 px-2 py-1.5 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-semibold">{item.ticker}</span>
                        <MarketBadge market={item.market} />
                        <DirectionBadge direction={item.direction} />
                        <StrategyBadge strategy={item.strategy} />
                      </div>
                      <span className="text-slate-500">{item.score?.toFixed(1)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-600">閺嗗倹妫ら弫鐗堝祄1�7</p>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export default function AdminPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-medium text-white">
        <Shield size={20} className="mr-2 inline text-indigo-400" />
        缁狅紕鎮婇崥搴��酱
      </h1>
      <UsersSection />
      <RecommendationRunner />
      <BothTablesView />
    </div>
  );
}
