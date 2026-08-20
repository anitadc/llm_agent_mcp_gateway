import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

export function ProtectedRoute({ roles }) {
  const { ready, authenticated, roles: userRoles } = useAuth();

  if (!ready) return <div className="p-8 text-center text-gray-500">Loading...</div>;
  if (!authenticated) return <Navigate to="/login" replace />;
  if (roles && !roles.some((r) => userRoles.includes(r))) return <Navigate to="/" replace />;

  return <Outlet />;
}
