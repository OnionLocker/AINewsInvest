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
  Trophy,
} from "lucide-react";
import { useState } from "react";

const navItems = [
  { to: "/recommendations/us", icon: DollarSign, label: "\u7F8E\u80A1\u63A8\u8350" },
  { to: "/recommendations/hk", icon: TrendingUp, label: "\u6E2F\u80A1\u63A8\u8350" },
  { to: "/win-rate", icon: Trophy, label: "\u80DC\u7387\u7EDF\u8BA1" },
  { to: "/screening", icon: Search, label: "\u9009\u80A1\u7B5B\u9009" },
  { to: "/analysis", icon: BarChart3, label: "\u6DF1\u5EA6\u5206\u6790" },
  { to: "/watchlist", icon: Heart, label: "\u81EA\u9009\u80A1" },
];

function SideLink({ to, icon: Icon, label, onClick }) {
  return (
    <NavLink
      to={to}
      onClick={onClick}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-md px-3 py-2 text-[18px] font-medium transition-colors duration-100 ${
          isActive
            ? "bg-brand-500/10 text-brand-500"
            : "text-[#787b86] hover:text-[#d1d4dc]"
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
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500 text-sm font-bold text-white">
          AV
        </div>
        <div>
          <span className="text-sm font-semibold text-[#d1d4dc]">Alpha Vault</span>
          <p className="text-[10px] text-[#787b86]">AI Investment Research</p>
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
            label={"\u7BA1\u7406\u540E\u53F0"}
            onClick={() => setSidebarOpen(false)}
          />
        )}
      </div>

      <div className="border-t border-[#2a2e39] px-3 py-3">
        <div className="mb-2 flex items-center gap-2 px-1">
          <div className="flex h-6 w-6 items-center justify-center rounded bg-[#2a2e39] text-[10px] font-bold text-[#787b86]">
            {user?.username?.charAt(0).toUpperCase()}
          </div>
          <div>
            <p className="text-xs text-[#d1d4dc]">{user?.username}</p>
            {user?.is_admin && (
              <span className="text-[10px] text-brand-500">{"\u7BA1\u7406\u5458"}</span>
            )}
          </div>
        </div>
        <button
          onClick={logout}
          className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-xs text-[#787b86] transition-colors hover:text-[#f23645]"
        >
          <LogOut size={14} />
          {"\u9000\u51FA\u767B\u5F55"}
        </button>
      </div>
    </nav>
  );

  return (
    <div className="flex h-screen bg-surface-0">
      <aside className="hidden w-52 shrink-0 border-r border-[#2a2e39] bg-surface-1 lg:block">
        {sidebar}
      </aside>

      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-52 border-r border-[#2a2e39] bg-surface-1 transition-transform lg:hidden ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {sidebar}
      </aside>

      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex h-12 items-center gap-3 border-b border-[#2a2e39] bg-surface-1 px-4 lg:hidden">
          <button onClick={() => setSidebarOpen(true)} className="text-[#787b86]">
            {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
          <span className="text-sm font-semibold text-[#d1d4dc]">Alpha Vault</span>
        </header>
        <main className="flex-1 overflow-y-auto p-6 scrollbar-thin">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
