import { Outlet } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { Sidebar } from "./Sidebar";

export function Layout() {
  const { email, logout } = useAuth();

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
        <h1 className="text-lg font-semibold">TCS AI Governance Plane</h1>
        <div className="flex items-center gap-4 text-sm text-gray-600">
          <span>{email}</span>
          <button onClick={logout} className="rounded bg-gray-100 px-3 py-1 hover:bg-gray-200">
            Log out
          </button>
        </div>
      </header>
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
