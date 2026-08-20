import { Navigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

export function Login() {
  const { ready, authenticated, initError, login } = useAuth();

  if (!ready) return <div className="p-8 text-center text-gray-500">Loading...</div>;
  if (authenticated) return <Navigate to="/" replace />;

  return (
    <div className="flex h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm rounded-lg border border-gray-200 bg-white p-8 text-center shadow-sm">
        <h1 className="mb-2 text-xl font-semibold">TCS AI Governance Plane</h1>
        <p className="mb-6 text-sm text-gray-500">Sign in with your organization account to continue.</p>
        {initError && (
          <p className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{initError}</p>
        )}
        <button
          onClick={login}
          className="w-full rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Log in with Keycloak
        </button>
      </div>
    </div>
  );
}
