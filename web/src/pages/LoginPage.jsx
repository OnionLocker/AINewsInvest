import { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import api from "../api";
import Spinner from "../components/Spinner";
import { Activity } from "lucide-react";

export default function LoginPage() {
  const { login, register, bootstrapAdmin } = useAuth();
  const [mode, setMode] = useState("login");
  const [needBootstrap, setNeedBootstrap] = useState(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.bootstrapStatus().then((d) => {
      if (!d.admin_exists) {
        setNeedBootstrap(true);
        setMode("bootstrap");
      } else {
        setNeedBootstrap(false);
      }
    });
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "bootstrap") {
        await bootstrapAdmin(username, password);
      } else if (mode === "register") {
        await register(username, password);
      } else {
        await login(username, password);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const titles = {
    bootstrap: "初始化管理员",
    login: "登录",
    register: "注册账号",
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 px-4">
      <div className="w-full max-w-xs">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-brand to-[#A04E30] text-sm font-bold text-white shadow-lg shadow-brand/20">
            AV
          </div>
          <h1 className="text-2xl font-light text-primary">
            Alpha<span className="font-semibold text-brand">Vault</span>
          </h1>
          <p className="mt-1 flex items-center justify-center gap-1.5 text-sm text-secondary">
            <Activity size={10} /> 港美股 AI 投研系统
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-border bg-white p-6 shadow-lg"
        >
          <h2 className="mb-4 text-base font-semibold text-primary">{titles[mode]}</h2>

          {mode === "bootstrap" && (
            <p className="mb-3 rounded-lg bg-[#D97706]/10 border border-[#D97706]/20 p-2.5 text-[11px] text-[#D97706]">
              尚未创建管理员账户，请创建第一个管理员
            </p>
          )}

          <label className="mb-1 block text-xs text-secondary">用户名</label>
          <input
            className="mb-3 w-full rounded-lg border border-border bg-surface-0 px-3 py-2 text-[15px] text-primary outline-none transition-colors focus:border-brand placeholder:text-tertiary"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
          />

          <label className="mb-1 block text-xs text-secondary">密码</label>
          <input
            type="password"
            className="mb-4 w-full rounded-lg border border-border bg-surface-0 px-3 py-2 text-[15px] text-primary outline-none transition-colors focus:border-brand placeholder:text-tertiary"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          {error && (
            <p className="mb-3 rounded-lg bg-down/10 border border-down/20 p-2 text-[11px] text-down">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy || !username || !password}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand px-4 py-3 text-sm font-medium text-white transition-colors hover:bg-[#A04E30] disabled:opacity-40 shadow-md shadow-brand/15"
          >
            {busy && <Spinner size="sm" />}
            {titles[mode]}
          </button>

          {needBootstrap === false && (
            <div className="mt-3 text-center text-[11px] text-secondary">
              {mode === "login" ? (
                <button
                  type="button"
                  onClick={() => setMode("register")}
                  className="text-brand hover:underline"
                >
                  没有账号？注册
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setMode("login")}
                  className="text-brand hover:underline"
                >
                  已有账号？去登录
                </button>
              )}
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
