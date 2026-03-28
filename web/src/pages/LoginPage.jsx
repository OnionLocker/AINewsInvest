import { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import api from "../api";
import Spinner from "../components/Spinner";

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
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600 text-lg font-bold">
            AV
          </div>
          <h1 className="text-2xl font-bold">Alpha Vault</h1>
          <p className="mt-1 text-sm text-gray-500">港美股 AI 投研系统</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-xl border border-surface-3 bg-surface-1 p-6"
        >
          <h2 className="mb-5 text-lg font-semibold">{titles[mode]}</h2>

          {mode === "bootstrap" && (
            <p className="mb-4 rounded-lg bg-yellow-500/10 p-3 text-xs text-yellow-400">
              尚未创建管理员账户，请创建第一个管理员。
            </p>
          )}

          <label className="mb-1 block text-xs text-gray-400">用户名</label>
          <input
            className="mb-4 w-full rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand-500"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
          />

          <label className="mb-1 block text-xs text-gray-400">密码</label>
          <input
            type="password"
            className="mb-5 w-full rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand-500"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          {error && (
            <p className="mb-3 rounded-lg bg-red-500/10 p-2 text-xs text-red-400">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy || !username || !password}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-brand-700 disabled:opacity-50"
          >
            {busy && <Spinner size="sm" />}
            {titles[mode]}
          </button>

          {needBootstrap === false && (
            <div className="mt-4 text-center text-xs text-gray-500">
              {mode === "login" ? (
                <button
                  type="button"
                  onClick={() => setMode("register")}
                  className="text-brand-400 hover:underline"
                >
                  没有账号？注册
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setMode("login")}
                  className="text-brand-400 hover:underline"
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
