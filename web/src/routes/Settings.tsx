import { useNavigate } from "react-router-dom";

import PageStub from "../components/PageStub";
import { useAuth } from "../lib/auth";

export default function Settings() {
  const { username, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <PageStub title="Settings" subtitle="Account, tenant, and distributor preferences.">
      <div className="space-y-3">
        <div className="text-zinc-700">
          Signed in as <span className="font-medium">{username ?? "—"}</span>
        </div>
        <button
          type="button"
          onClick={() => {
            logout();
            navigate("/login", { replace: true });
          }}
          className="inline-flex items-center rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
        >
          Sign out
        </button>
      </div>
    </PageStub>
  );
}
