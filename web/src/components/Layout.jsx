import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {
  LayoutDashboard,
  DollarSign,
  TrendingUp,
  Search,
  BarChart3,
  Heart,
  Shield,
  LogOut,
  Menu,
  X,
  Trophy,
  Activity,
} from "lucide-react";
import { useState } from "react";

const navItems = [
  { to: "/dashboard", icon: LayoutDashboard, label: "仪表盘" },
  { to: "/recommendations/us", icon: DollarSign, label: "美股推荐" },
  { to: "/recommendations/hk", icon: TrendingUp, label: "港股推荐" },
  { to: "/win-rate", icon: Trophy, label: "胜率统计" },
  { to: "/screening", icon: Search, label: "选股筛选" },
  { to: "/analysis", icon: BarChart3, label: "深度分析" },
  { to: "/watchlist", icon: Heart, label: "自选股" },
];

function SideLink({ to, icon: Icon, label, onClick }) {
  return (
    <NavLink
      to={to}
      onClick={onClick}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150 ${
          isActive
            ? "bg-indigo-500/10 text-indigo-400 shadow-sm"
            : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
        }`
      }
    >
      <Icon size={16} strokeWidth={1.6} />
      {label}
    </NavLink>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const sidebar = (
    <nav className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-4 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-indigo-600 text-sm font-bold text-white shadow-lg shadow-indigo-500/20">
          AV
        </div>
        <div>
          <span className="text-sm font-semibold text-slate-200">
            Alpha<span className="text-indigo-400">Vault</span>
          </span>
          <p className="flex items-center gap-1 text-[10px] text-slate-500">
            <Activity size={8} /> AI 投研系统
          </p>
        </div>
      </div>

      <div className="flex-1 space-y-0.5 px-2 overflow-y-auto scrollbar-thin">
        {navItems.map((item) => (
          <SideLink key={item.to} {...item} onClick={() => setSidebarOpen(false)} />
        ))}
        {user?.is_admin && (
          <SideLink
            to="/admin"
            icon={Shield}
            label="管理后台"
            onClick={() => setSidebarOpen(false)}
          />
        )}
      </div>

      <div className="border-t border-slate-800/60 px-3 py-3">
        <div className="mb-2 flex items-center gap-2 px-1">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-slate-800 text-[10px] font-bold text-slate-400">
            {user?.username?.charAt(0).toUpperCase()}
          </div>
          <div>
            <p className="text-xs text-slate-300">{user?.username}</p>
            {user?.is_admin && (
              <span className="text-[10px] text-indigo-400">管理员</span>
            )}
          </div>
        </div>
        <button
          onClick={logout}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-500 transition-colors hover:text-rose-400 hover:bg-rose-400/5"
        >
          <LogOut size={14} />
          退出登录
        </button>
      </div>
    </nav>
  );

  return (
    <div className="flex h-screen bg-surface-0">
      <aside className="hidden w-52 shrink-0 border-r border-slate-800/60 bg-surface-1 lg:block">
        {sidebar}
      </aside>

      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-52 border-r border-slate-800/60 bg-surface-1 transition-transform lg:hidden ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {sidebar}
      </aside>

      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex h-12 items-center gap-3 border-b border-slate-800/60 bg-surface-1 px-4 lg:hidden">
          <button onClick={() => setSidebarOpen(true)} className="text-slate-400">
            {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
          <span className="text-sm font-semibold text-slate-200">
            Alpha<span className="text-indigo-400">Vault</span>
          </span>
        </header>
        <main className="flex-1 overflow-y-auto p-6 scrollbar-thin">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
