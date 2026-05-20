import { useState, useEffect } from "react";
import { Routes, Route, NavLink, Navigate, useLocation } from "react-router-dom";

import ProtectedRoute from "./components/ProtectedRoute";
import { useAuth } from "./lib/auth";

import Dashboard from "./routes/Dashboard";
import Catalog from "./routes/Catalog";
import ProductDetail from "./routes/ProductDetail";
import Rips from "./routes/Rips";
import Closeouts from "./routes/Closeouts";
import Combos from "./routes/Combos";
import Watchlist from "./routes/Watchlist";
import Alerts from "./routes/Alerts";
import AdminIngest from "./routes/AdminIngest";
import Specials from "./routes/Specials";
import Orders from "./routes/Orders";
import OrderDetailPage from "./routes/OrderDetail";
import Analytics from "./routes/Analytics";
import Settings from "./routes/Settings";
import Login from "./routes/Login";

const NAV = [
  { to: "/", label: "Dashboard", icon: "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" },
  { to: "/catalog", label: "Catalog", icon: "M4 6h16M4 10h16M4 14h16M4 18h16" },
  { to: "/rips", label: "RIPs", icon: "M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" },
  { to: "/closeouts", label: "Closeouts", icon: "M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" },
  { to: "/combos", label: "Combos", icon: "M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" },
  { to: "/specials", label: "Specials", icon: "M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" },
  { to: "/orders", label: "Orders", icon: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" },
  { to: "/watchlist", label: "Tracked", icon: "M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" },
  { to: "/analytics", label: "Analytics", icon: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" },
  { to: "/alerts", label: "Alerts", icon: "M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" },
];

const BOTTOM_NAV = [
  { to: "/settings", label: "Settings", icon: "M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" },
];

function NavIcon({ d }: { d: string }) {
  return (
    <svg className="h-5 w-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const { isAuthed } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  // Close sidebar on route change (mobile)
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  const sidebarLinkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
      isActive
        ? "bg-zinc-900 text-white"
        : "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
    }`;

  if (!isAuthed) {
    return (
      <div className="min-h-full flex flex-col">
        <main className="flex-1">
          <div className="mx-auto max-w-7xl px-3 sm:px-6 lg:px-8 py-4 sm:py-8">{children}</div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Overlay backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-40"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Floating sidebar — overlays content on all screen sizes */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-56 bg-white border-r border-zinc-200 shadow-lg flex flex-col transition-transform duration-200 ease-in-out ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Logo + close */}
        <div className="flex items-center justify-between h-14 px-4 border-b border-zinc-200 flex-shrink-0">
          <NavLink to="/" className="font-semibold tracking-tight text-sm whitespace-nowrap">
            CELR Price Book
          </NavLink>
          <button
            onClick={() => setSidebarOpen(false)}
            className="p-1 rounded-md text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100"
            aria-label="Close menu"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Nav items */}
        <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={sidebarLinkClass}
            >
              <NavIcon d={item.icon} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Bottom nav (Settings) */}
        <div className="border-t border-zinc-200 px-3 py-3 space-y-1 flex-shrink-0">
          {BOTTOM_NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={sidebarLinkClass}
            >
              <NavIcon d={item.icon} />
              {item.label}
            </NavLink>
          ))}
        </div>
      </aside>

      {/* Main content area — full width always */}
      <div className="flex flex-col min-h-screen">
        {/* Top bar with hamburger — always visible */}
        <header className="sticky top-0 z-30 bg-white border-b border-zinc-200">
          <div className="flex items-center h-14 px-4 max-w-7xl mx-auto">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-2 -ml-2 rounded-md text-zinc-600 hover:bg-zinc-100"
              aria-label="Open menu"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <span className="ml-3 font-semibold tracking-tight text-sm">CELR Price Book</span>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1">
          <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 py-4 sm:py-6">{children}</div>
        </main>

        {/* Footer */}
        <footer className="border-t border-zinc-200 bg-white">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 text-xs text-zinc-500">
            CELR Liquor Price Book · for NJ liquor retailers · v0.1
          </div>
        </footer>
      </div>
    </div>
  );
}

const protect = (el: React.ReactNode) => <ProtectedRoute>{el}</ProtectedRoute>;

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={protect(<Dashboard />)} />
        <Route path="/catalog" element={protect(<Catalog />)} />
        <Route path="/catalog/:code" element={protect(<ProductDetail />)} />
        <Route path="/rips" element={protect(<Rips />)} />
        <Route path="/closeouts" element={protect(<Closeouts />)} />
        <Route path="/combos" element={protect(<Combos />)} />
        <Route path="/specials" element={protect(<Specials />)} />
        <Route path="/orders" element={protect(<Orders />)} />
        <Route path="/orders/:id" element={protect(<OrderDetailPage />)} />
        <Route path="/analytics" element={protect(<Analytics />)} />
        <Route path="/watchlist" element={protect(<Watchlist />)} />
        <Route path="/alerts" element={protect(<Alerts />)} />
        <Route path="/admin/ingest" element={protect(<AdminIngest />)} />
        <Route path="/settings" element={protect(<Settings />)} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}
