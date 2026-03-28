import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {
  DollarSign,
  TrendingUp,
  Search,
  BarChart3,
  Heart,
  Shield,
  LogOut,
  Menu,
  X,
} from "lucide-react";
import { useState } from "react";

const navItems = [
  { to: "/recommendations/us", icon: DollarSign, label: "美股推荐" },
  { to: "/recommendations/hk", icon: TrendingUp, label: "港股推荐" },
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
        `flex items-center gap-3 rounded-lg px-5 py-3.5 text-lg font-medium transition-colors ${
          isActive
            ? "bg-brand-600/20 text-brand-400"
            : "text-gray-400 hover:bg-surface-2 hover:text-gray-200"
        }`
      }
    >
      <Icon size={22} />
      {label}
    </NavLink>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const sidebar = (
    <nav className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-4 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold">
          AV
        </div>
        <span className="text-lg font-semibold tracking-tight">Alpha Vault</span>
      </div>

      <div className="flex-1 space-y-1.5 px-3 overflow-y-auto scrollbar-thin">
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

      <div className="border-t border-surface-3 px-3 py-4">
        <div className="mb-2 px-3 text-xs text-gray-500">
          {user?.username}
          {user?.is_admin && (
            <span className="ml-1 rounded bg-brand-600/30 px-1.5 py-0.5 text-[10px] text-brand-400">
              管理员
            </span>
          )}
        </div>
        <button
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-gray-400 transition-colors hover:bg-surface-2 hover:text-red-400"
        >
          <LogOut size={18} />
          退出登录
        </button>
      </div>
    </nav>
  );

  return (
    <div className="flex h-screen bg-surface-0">
      <aside className="hidden w-64 shrink-0 border-r border-surface-3 bg-surface-1 lg:block">
        {sidebar}
      </aside>

      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 bg-surface-1 transition-transform lg:hidden ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {sidebar}
      </aside>

      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex h-14 items-center gap-3 border-b border-surface-3 bg-surface-1 px-4 lg:hidden">
          <button onClick={() => setSidebarOpen(true)} className="text-gray-400">
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <span className="font-semibold">Alpha Vault</span>
        </header>
        <main className="flex-1 overflow-y-auto p-4 md:p-6 scrollbar-thin">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
