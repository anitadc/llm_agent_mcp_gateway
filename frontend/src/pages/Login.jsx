import { Navigate, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";

import { useAuth } from "../hooks/useAuth";
import { authService } from "../services/authService";

export function Login() {
  const { ready, authenticated, initError, login } = useAuth();
  const [providerInfo, setProviderInfo] = useState(null);
  const [userId, setUserId] = useState("");
  const [email, setEmail] = useState("");
  const [roles, setRoles] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const navigate = useNavigate();

  // useEffect(() => {
  //   let mounted = true;
  //   const baseURL = import.meta.env.VITE_API_BASE;
  //   fetch(`${baseURL}/v1/auth/provider`)
  //     .then((r) => r.json())
  //     .then((j) => mounted && setProviderInfo(j))
  //     .catch(() => mounted && setProviderInfo(null));
  //   // console.log("providerInfo", providerInfo);
  //   // console.log("authService.isKeycloakConfigured", authService.isKeycloakConfigured);
  //   return () => {
  //     mounted = false;
  //   };
  // }, []);

  useEffect(() => {
  let mounted = true;
  const baseURL = import.meta.env.VITE_API_BASE;

  const fetchProvider = async () => {
    try {
      const response = await fetch(`${baseURL}/v1/auth/provider`);
      if (!response.ok) throw new Error("Network response failed");
      
      const data = await response.json();
      console.log("Fetched provider info:", data);

      if (mounted) {
        setProviderInfo(data);

        if(data.identity_provider == 'local') {
          console.log("Local provider detected. You can issue a local token.");
           authService.isKeycloakConfigured = false; // Set the flag to false for local provider
        }
        
        // 👉 Run the rest of your logic here, guaranteed to have the fresh data:
        console.log("providerInfo", data);
        console.log("authService.isKeycloakConfigured", authService.isKeycloakConfigured);
        // Call any other dependent functions here...
      }
    } catch (error) {
      if (mounted) {
        setProviderInfo(null);
        console.error("Failed to load provider info:", error);
      }
    }
  };

  fetchProvider();

  return () => {
    mounted = false;
  };
}, []);

  const effectiveProvider = providerInfo?.identity_provider ?? (authService.isKeycloakConfigured ? "keycloak" : null);
  const showKeycloakLogin = effectiveProvider === "keycloak";
  const showLocalTokenForm = effectiveProvider === "local" || (!showKeycloakLogin && !authService.isKeycloakConfigured);

  if (!ready) return <div className="p-8 text-center text-gray-500">Loading...</div>;
  if (authenticated) return <Navigate to="/" replace />;

  const submitLocal = async (event) => {
    event.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const result = await authService.issueLocalToken({
        user_id: userId || "dev-user",
        email: email || "dev@example.com",
        roles: roles ? roles.split(",").map((role) => role.trim()) : [],
      });

      if (result?.session) {
        setSuccess(result.session);
      } else {
        setSuccess({ message: "Token issued and ready to continue." });
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm rounded-lg border border-gray-200 bg-white p-8 text-center shadow-sm">
        <h1 className="mb-2 text-xl font-semibold">TCS AI Governance Plane</h1>
        <p className="mb-6 text-sm text-gray-500">Sign in with your organization account to continue.</p>
        {initError && (
          <p className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{initError}</p>
        )}

        {showKeycloakLogin ? (
          <button
            onClick={login}
            className="w-full rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            Log in with Keycloak
          </button>
        ) : null}

        {showLocalTokenForm ? (
          <form onSubmit={submitLocal} className="space-y-3">
            <div className="text-left">
              <label className="block text-xs font-medium text-gray-600">User ID</label>
              <input value={userId} onChange={(e) => setUserId(e.target.value)} className="mt-1 w-full rounded border px-2 py-1" />
            </div>
            <div className="text-left">
              <label className="block text-xs font-medium text-gray-600">Email</label>
              <input value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 w-full rounded border px-2 py-1" />
            </div>
            <div className="text-left">
              <label className="block text-xs font-medium text-gray-600">Roles (comma-separated)</label>
              <input value={roles} onChange={(e) => setRoles(e.target.value)} className="mt-1 w-full rounded border px-2 py-1" />
            </div>

            {error && <p className="text-xs text-red-600">{error}</p>}
            {success ? (
              <div className="space-y-3">
                <p className="text-sm text-green-600">Token issued and session established.</p>
                <button type="button" onClick={() => navigate("/")} className="w-full rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">
                  Continue
                </button>
              </div>
            ) : (
              <button type="submit" disabled={loading} className="w-full rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">
                {loading ? "Issuing token…" : "Issue dev token"}
              </button>
            )}
          </form>
        ) : null}

        {!showKeycloakLogin && !showLocalTokenForm && (
          <p className="text-sm text-gray-500">No external identity provider configured.</p>
        )}
      </div>
    </div>
  );
}
