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
    <div className="flex min-h-screen items-center justify-center bg-[#131722] px-4">
      <div className="w-full max-w-xs">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-brand-500 text-sm font-bold text-white">
            AV
          </div>
          <h1 className="text-xl font-semibold text-[#d1d4dc]">Alpha Vault</h1>
          <p className="mt-1 text-xs text-[#787b86]">港美股 AI 投研系统</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-lg border border-[#2a2e39] bg-[#1e222d] p-5"
        >
          <h2 className="mb-4 text-sm font-semibold text-[#d1d4dc]">{titles[mode]}</h2>

          {mode === "bootstrap" && (
            <p className="mb-3 rounded bg-[#fb8c00]/10 p-2.5 text-[11px] text-[#fb8c00]">
              尚未创建管理员账户，请创建第一个管理员。
            </p>
          )}

          <label className="mb-1 block text-[11px] text-[#787b86]">用户名</label>
          <input
            className="mb-3 w-full rounded border border-[#2a2e39] bg-[#131722] px-3 py-2 text-sm text-[#d1d4dc] outline-none transition-colors focus:border-brand-500"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
          />

          <label className="mb-1 block text-[11px] text-[#787b86]">密码</label>
          <input
            type="password"
            className="mb-4 w-full rounded border border-[#2a2e39] bg-[#131722] px-3 py-2 text-sm text-[#d1d4dc] outline-none transition-colors focus:border-brand-500"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          {error && (
            <p className="mb-3 rounded bg-[#f23645]/10 p-2 text-[11px] text-[#f23645]">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy || !username || !password}
            className="flex w-full items-center justify-center gap-2 rounded bg-brand-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-600 disabled:opacity-40"
          >
            {busy && <Spinner size="sm" />}
            {titles[mode]}
          </button>

          {needBootstrap === false && (
            <div className="mt-3 text-center text-[11px] text-[#787b86]">
              {mode === "login" ? (
                <button
                  type="button"
                  onClick={() => setMode("register")}
                  className="text-brand-500 hover:underline"
                >
                  没有账号？注册
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setMode("login")}
                  className="text-brand-500 hover:underline"
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
