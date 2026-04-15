import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import ErrorBoundary from "./ErrorBoundary";
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
  BookOpen,
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
  { to: "/help", icon: BookOpen, label: "使用指南" },
];

function SideLink({ to, icon: Icon, label, onClick }) {
  return (
    <NavLink
      to={to}
      onClick={onClick}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-xl px-4 py-3 text-[15px] font-medium transition-all duration-150 ${
          isActive
            ? "bg-white text-primary shadow-sm"
            : "text-secondary hover:text-primary hover:bg-surface-3"
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
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand to-[#A04E30] text-sm font-bold text-white shadow-lg shadow-brand/20">
          AV
        </div>
        <div>
          <span className="text-base font-semibold text-primary">
            Alpha<span className="text-brand">Vault</span>
          </span>
          <p className="flex items-center gap-1 text-[10px] text-secondary">
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

      <div className="border-t border-border px-3 py-4">
        <div className="mb-2 flex items-center gap-2.5 px-1">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-surface-3 text-xs font-bold text-secondary">
            {user?.username?.charAt(0).toUpperCase()}
          </div>
          <div>
            <p className="text-sm text-primary">{user?.username}</p>
            {user?.is_admin && (
              <span className="text-xs text-brand">管理员</span>
            )}
          </div>
        </div>
        <button
          onClick={logout}
          className="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-sm text-secondary transition-colors hover:text-down hover:bg-down/5"
        >
          <LogOut size={14} />
          退出登录
        </button>
      </div>
    </nav>
  );

  return (
    <div className="flex h-screen bg-surface-0">
      <aside className="hidden w-56 shrink-0 border-r border-border bg-surface-2 lg:block">
        {sidebar}
      </aside>

      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-primary/30 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-56 border-r border-border bg-surface-2 transition-transform lg:hidden ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {sidebar}
      </aside>

      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex h-14 items-center gap-3 border-b border-border bg-surface-2 px-4 lg:hidden">
          <button onClick={() => setSidebarOpen(true)} className="text-secondary">
            {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
          <span className="text-base font-semibold text-primary">
            Alpha<span className="text-brand">Vault</span>
          </span>
        </header>
        <main className="flex-1 overflow-y-auto p-8 scrollbar-thin">
          <ErrorBoundary><Outlet /></ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
