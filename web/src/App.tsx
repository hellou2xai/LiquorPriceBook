import { useState } from "react";
import { Routes, Route, NavLink, Navigate } from "react-router-dom";

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
  { to: "/", label: "Dashboard" },
  { to: "/catalog", label: "Catalog" },
  { to: "/rips", label: "RIPs" },
  { to: "/closeouts", label: "Closeouts" },
  { to: "/combos", label: "Combos" },
  { to: "/specials", label: "Specials" },
  { to: "/orders", label: "Orders" },
  { to: "/watchlist", label: "Tracked" },
  { to: "/analytics", label: "Analytics" },
  { to: "/alerts", label: "Alerts" },
];

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  [
    "px-3 py-1.5 rounded-md text-sm",
    isActive
      ? "bg-zinc-900 text-white"
      : "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100",
  ].join(" ");

function Shell({ children }: { children: React.ReactNode }) {
  const { isAuthed } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  // Close mobile menu on navigation
  const closeMobile = () => setMobileOpen(false);

  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-zinc-200 bg-white sticky top-0 z-40">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-14 items-center justify-between">
            <div className="flex items-center gap-4 md:gap-8">
              <NavLink to="/" className="font-semibold tracking-tight text-sm sm:text-base whitespace-nowrap">
                CELR Liquor Price Book
              </NavLink>
              {isAuthed && (
                <nav className="hidden md:flex items-center gap-1">
                  {NAV.map((item) => (
                    <NavLink key={item.to} to={item.to} end={item.to === "/"} className={navLinkClass}>
                      {item.label}
                    </NavLink>
                  ))}
                </nav>
              )}
            </div>
            <div className="flex items-center gap-3">
              {isAuthed && (
                <NavLink to="/settings" className="text-sm text-zinc-600 hover:text-zinc-900 hidden sm:block">
                  Settings
                </NavLink>
              )}
              {/* Mobile hamburger */}
              {isAuthed && (
                <button
                  onClick={() => setMobileOpen(!mobileOpen)}
                  className="md:hidden p-2 -mr-2 rounded-md text-zinc-600 hover:bg-zinc-100"
                  aria-label="Toggle menu"
                >
                  {mobileOpen ? (
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  ) : (
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
                    </svg>
                  )}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Mobile nav drawer */}
        {isAuthed && mobileOpen && (
          <nav className="md:hidden border-t border-zinc-100 bg-white px-4 pb-4 pt-2 space-y-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                onClick={closeMobile}
                className={({ isActive }) =>
                  `block px-3 py-2 rounded-md text-sm font-medium ${
                    isActive ? "bg-zinc-900 text-white" : "text-zinc-600 hover:bg-zinc-100"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
            <NavLink
              to="/settings"
              onClick={closeMobile}
              className={({ isActive }) =>
                `block px-3 py-2 rounded-md text-sm font-medium ${
                  isActive ? "bg-zinc-900 text-white" : "text-zinc-600 hover:bg-zinc-100"
                }`
              }
            >
              Settings
            </NavLink>
          </nav>
        )}
      </header>

      <main className="flex-1">
        <div className="mx-auto max-w-7xl px-3 sm:px-6 lg:px-8 py-4 sm:py-8">{children}</div>
      </main>

      <footer className="border-t border-zinc-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-4 text-xs text-zinc-500">
          CELR Liquor Price Book · for NJ liquor retailers · v0.1
        </div>
      </footer>
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
