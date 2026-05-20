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
import Settings from "./routes/Settings";
import Login from "./routes/Login";

const NAV = [
  { to: "/", label: "Dashboard" },
  { to: "/catalog", label: "Catalog" },
  { to: "/rips", label: "RIPs" },
  { to: "/closeouts", label: "Closeouts" },
  { to: "/combos", label: "Combos" },
  { to: "/specials", label: "Specials" },
  { to: "/watchlist", label: "Order List" },
  { to: "/alerts", label: "Alerts" },
];

function Shell({ children }: { children: React.ReactNode }) {
  const { isAuthed } = useAuth();
  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-14 items-center justify-between">
            <div className="flex items-center gap-8">
              <NavLink to="/" className="font-semibold tracking-tight">
                CELR Liquor Price Book
              </NavLink>
              {isAuthed ? (
                <nav className="hidden md:flex items-center gap-1">
                  {NAV.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === "/"}
                      className={({ isActive }) =>
                        [
                          "px-3 py-1.5 rounded-md text-sm",
                          isActive
                            ? "bg-zinc-900 text-white"
                            : "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100",
                        ].join(" ")
                      }
                    >
                      {item.label}
                    </NavLink>
                  ))}
                </nav>
              ) : null}
            </div>
            {isAuthed ? (
              <NavLink
                to="/settings"
                className="text-sm text-zinc-600 hover:text-zinc-900"
              >
                Settings
              </NavLink>
            ) : null}
          </div>
        </div>
      </header>

      <main className="flex-1">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8">{children}</div>
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
        <Route path="/watchlist" element={protect(<Watchlist />)} />
        <Route path="/alerts" element={protect(<Alerts />)} />
        <Route path="/admin/ingest" element={protect(<AdminIngest />)} />
        <Route path="/settings" element={protect(<Settings />)} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}
