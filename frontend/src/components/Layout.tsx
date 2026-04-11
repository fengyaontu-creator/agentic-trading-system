import { useState } from "react";
import {
  BarChart3,
  ChevronLeft,
  ChevronRight,
  Clock,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  Settings,
  TrendingUp,
  X,
} from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { localTimeForET } from "../utils/time";

const nav = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/signals",   label: "Signals",   icon: TrendingUp },
  { to: "/history",   label: "History",   icon: History },
  { to: "/settings",  label: "Settings",  icon: Settings },
];

export default function Layout() {
  const navigate = useNavigate();
  const username = localStorage.getItem("username") ?? "User";
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const analysisLocal = localTimeForET(7, 30);

  function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    navigate("/login", { replace: true });
  }

  function SidebarContent({ isMobile = false }: { isMobile?: boolean }) {
    const iconOnly = collapsed && !isMobile;
    return (
      <>
        {/* Logo row */}
        <div className={`flex items-center py-5 px-3 ${iconOnly ? "justify-center" : "justify-between"}`}>
          <div className={`flex items-center gap-2 ${iconOnly ? "" : ""}`}>
            <BarChart3 className="h-6 w-6 flex-shrink-0 text-indigo-400" />
            {!iconOnly && (
              <span className="text-sm font-semibold tracking-wide text-gray-100">
                AI Trader
              </span>
            )}
          </div>
          {/* Desktop toggle */}
          {!isMobile && (
            <button
              onClick={() => setCollapsed(!collapsed)}
              className="rounded-md p-1 text-gray-400 hover:bg-gray-800 hover:text-gray-100 transition-colors"
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {collapsed
                ? <ChevronRight className="h-4 w-4" />
                : <ChevronLeft className="h-4 w-4" />}
            </button>
          )}
          {/* Mobile close */}
          {isMobile && (
            <button
              onClick={() => setMobileOpen(false)}
              className="rounded-md p-1 text-gray-400 hover:bg-gray-800 hover:text-gray-100 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Nav links */}
        <nav className="flex-1 space-y-1 px-2">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => isMobile && setMobileOpen(false)}
              title={iconOnly ? label : undefined}
              className={({ isActive }) =>
                `flex items-center rounded-lg px-3 py-2.5 text-sm transition-colors ${
                  iconOnly ? "justify-center" : "gap-3"
                } ${
                  isActive
                    ? "bg-indigo-600 text-white"
                    : "text-gray-400 hover:bg-gray-800 hover:text-gray-100"
                }`
              }
            >
              <Icon className="h-4 w-4 flex-shrink-0" />
              {!iconOnly && label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="border-t border-gray-800 px-3 py-4">
          {iconOnly ? (
            <div className="mb-3 flex justify-center">
              <div
                className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold uppercase text-white"
                title={username}
              >
                {username[0]}
              </div>
            </div>
          ) : (
            <>
              <div className="mb-3 flex items-center gap-2">
                <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold uppercase text-white">
                  {username[0]}
                </div>
                <span className="truncate text-sm text-gray-300">{username}</span>
              </div>
              <div className="mb-2 flex items-center gap-1.5 text-xs text-gray-500">
                <Clock className="h-3 w-3 flex-shrink-0" />
                <span>{`Analysis 07:30 ET (${analysisLocal} local)`}</span>
              </div>
            </>
          )}
          <button
            onClick={logout}
            title={iconOnly ? "Logout" : undefined}
            className={`flex w-full items-center rounded-lg px-3 py-2 text-sm text-gray-400 hover:bg-gray-800 hover:text-red-400 transition-colors ${
              iconOnly ? "justify-center" : "gap-2"
            }`}
          >
            <LogOut className="h-4 w-4 flex-shrink-0" />
            {!iconOnly && "Logout"}
          </button>
        </div>
      </>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/50 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Desktop sidebar */}
      <aside
        className={`hidden lg:flex flex-col border-r border-gray-800 bg-gray-900 transition-all duration-200 ${
          collapsed ? "w-14" : "w-56"
        }`}
      >
        <SidebarContent isMobile={false} />
      </aside>

      {/* Mobile sidebar (slide-in overlay) */}
      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-56 flex-col border-r border-gray-800 bg-gray-900 transition-transform duration-200 lg:hidden ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <SidebarContent isMobile={true} />
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto bg-gray-950">
        {/* Mobile top bar */}
        <div className="flex items-center gap-3 border-b border-gray-800 px-4 py-3 lg:hidden">
          <button
            onClick={() => setMobileOpen(true)}
            className="rounded-md p-1.5 text-gray-400 hover:bg-gray-800 hover:text-gray-100 transition-colors"
          >
            <Menu className="h-5 w-5" />
          </button>
          <BarChart3 className="h-5 w-5 text-indigo-400" />
          <span className="text-sm font-semibold text-gray-100">AI Trader</span>
        </div>
        <div className="p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
