import { useState, useEffect, useRef } from "react";
import api from "../api";
import Card, { CardTitle } from "../components/Card";
import Spinner, { PageLoader } from "../components/Spinner";
import Badge, { MarketBadge, DirectionBadge, StrategyBadge } from "../components/Badge";
import { useToast } from "../components/Toast";
import { useConfirm } from "../components/ConfirmDialog";
import { Shield, Users, Play, Upload, RefreshCw } from "lucide-react";

function UsersSection() {
  const toast = useToast();
  const confirmDialog = useConfirm();
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
      toast({ type: "error", message: err.message });
    }
  }

  async function deleteUser(username) {
    const ok = await confirmDialog({
      title: "删除用户",
      message: `确定删除用户 ${username} ？此操作不可撤销。`,
      variant: "danger",
    });
    if (!ok) return;
    try {
      await api.adminDeleteUser(username);
      setUsers((prev) => prev.filter((u) => u.username !== username));
    } catch (err) {
      toast({ type: "error", message: err.message });
    }
  }

  if (loading) return <Spinner />;

  return (
    <Card>
      <CardTitle><Users size={14} className="mr-1 inline" /> 用户管理</CardTitle>
      <div className="space-y-2">
        {users.map((u) => (
          <div key={u.username} className="flex items-center justify-between rounded-lg bg-surface-2 px-3 py-2">
            <div>
              <span className="text-sm font-medium">{u.username}</span>
              {u.is_admin && <Badge variant="brand" className="ml-2">管理员</Badge>}
              {!u.is_active && <Badge variant="red" className="ml-2">已禁用</Badge>}
            </div>
            {!u.is_admin && (
              <div className="flex gap-2">
                <button
                  onClick={() => toggleActive(u.username, !u.is_active)}
                  className="text-xs text-secondary hover:text-brand"
                >
                  {u.is_active ? "禁用" : "启用"}
                </button>
                <button
                  onClick={() => deleteUser(u.username)}
                  className="text-xs text-secondary hover:text-red-400"
                >
                  删除
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
  const toast = useToast();
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
      toast({ type: "error", message: err.message });
      setRunning(false);
    }
  }

  async function handlePublish() {
    try {
      const result = await api.adminPublish("", market);
      toast({ type: "success", message: "已发布 " + result.count + " 条推荐 (" + market + ")" });
    } catch (err) {
      toast({ type: "error", message: err.message });
    }
  }

  return (
    <Card>
      <CardTitle><Play size={14} className="mr-1 inline" /> 推荐生成</CardTitle>
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label className="mb-1 block text-xs text-secondary">市场</label>
          <select
            value={market}
            onChange={(e) => setMarket(e.target.value)}
            className="rounded-lg border border-border bg-surface-0 px-3 py-2 text-sm"
          >
            <option value="us_stock">美股</option>
            <option value="hk_stock">港股</option>
          </select>
        </div>
        <button
          onClick={handleRun}
          disabled={running}
          className="flex items-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm text-white hover:bg-[#A04E30] disabled:opacity-50"
        >
          {running ? <Spinner size="sm" /> : <Play size={16} />}
          {running ? "运行中..." : "运行推荐"}
        </button>
        <button
          onClick={handlePublish}
          className="flex items-center gap-2 rounded-lg border border-brand px-4 py-2 text-sm text-brand hover:bg-brand/10"
        >
          <Upload size={16} /> 发布
        </button>
      </div>

      {status && status.status !== "idle" && (
        <div className="mt-4 rounded-lg bg-surface-2 p-3">
          <div className="flex items-center gap-2 text-sm">
            <Badge variant={status.status === "done" ? "green" : status.status === "failed" ? "red" : "yellow"}>
              {status.status}
            </Badge>
            {status.progress != null && (
              <span className="text-xs text-secondary">{status.progress}%</span>
            )}
          </div>
          {status.message && (
            <p className="mt-1 text-xs text-secondary">{status.message}</p>
          )}
        </div>
      )}
    </Card>
  );
}

function BothTablesView() {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  async function loadTables() {
    setLoading(true);
    try {
      const d = await api.adminBothTables("");
      setData(d);
    } catch (err) {
      toast({ type: "error", message: err.message });
    }
    setLoading(false);
  }

  const tableLabel = { admin: "管理端", published: "已发布" };

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <CardTitle className="!mb-0">管理端 vs 已发布</CardTitle>
        <button
          onClick={loadTables}
          disabled={loading}
          className="flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-xs text-secondary hover:bg-surface-2"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          加载
        </button>
      </div>

      {data && (
        <div className="grid gap-4 lg:grid-cols-2">
          {["admin", "published"].map((key) => (
            <div key={key}>
              <p className="mb-2 text-xs font-semibold text-secondary uppercase">{tableLabel[key]}</p>
              {data[key]?.items?.length > 0 ? (
                <div className="space-y-1">
                  {data[key].items.map((item, i) => (
                    <div key={i} className="rounded bg-surface-2 px-2 py-1.5 text-xs">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-semibold">{item.ticker}</span>
                          <MarketBadge market={item.market} />
                          <DirectionBadge direction={item.direction} />
                          <StrategyBadge strategy={item.strategy} />
                        </div>
                        <span className="font-semibold text-brand">{item.score?.toFixed(1)}</span>
                      </div>
                      <div className="mt-1 flex items-center gap-3 text-[10px] text-tertiary">
                        {item.entry_price != null && (
                          <span>入场: {Number(item.entry_price).toFixed(2)}</span>
                        )}
                        {item.stop_loss != null && (
                          <span className="text-down/70">止损: {Number(item.stop_loss).toFixed(2)}</span>
                        )}
                        {item.take_profit != null && (
                          <span className="text-up/70">止盈: {Number(item.take_profit).toFixed(2)}</span>
                        )}
                        {(item.confidence || item.combined_score) != null && (
                          <span className="text-[#D97706]/70">置信: {Math.round(item.confidence || item.combined_score)}%</span>
                        )}
                        {item.risk_flags && (() => {
                          let flags = Array.isArray(item.risk_flags) ? item.risk_flags : [];
                          if (typeof item.risk_flags === "string") {
                            try { flags = JSON.parse(item.risk_flags); } catch { flags = []; }
                          }
                          flags = flags.filter(f => f && f !== "[]" && f !== "null");
                          return flags.length > 0 ? (
                            <span className="text-down/70">风险: {flags.length}项</span>
                          ) : null;
                        })()}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-tertiary">暂无数据</p>
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
      <h1 className="text-xl font-bold text-primary">
        <Shield size={20} className="mr-2 inline text-brand" />
        管理后台
      </h1>
      <UsersSection />
      <RecommendationRunner />
      <BothTablesView />
    </div>
  );
}
