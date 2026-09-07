import { createContext, useEffect, useState } from "react";

import { authService } from "../services/authService";

export const AuthContext = createContext(null);

const INIT_TIMEOUT_MS = 8000;

export function AuthProvider({ children }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [initError, setInitError] = useState(null);

  useEffect(() => {
    let settled = false;

    const timeoutId = setTimeout(() => {
      if (!settled && authService.isKeycloakConfigured) {
        settled = true;
        console.error("Keycloak init did not resolve within timeout — check that Keycloak is reachable and third-party cookies/iframes aren't being blocked.");
        setInitError("Could not reach the login server in time.");
        setReady(true);
      }
    }, INIT_TIMEOUT_MS);

    authService
      .init()
      .then((isAuthenticated) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeoutId);
        setAuthenticated(Boolean(isAuthenticated));
        setReady(true);
      })
      .catch((error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeoutId);
        console.error("Auth init failed:", error);
        setInitError("Failed to initialize login. See browser console for details.");
        setReady(true);
      });

    return () => clearTimeout(timeoutId);
  }, []);

  const value = {
    ready,
    authenticated,
    initError,
    roles: authenticated ? authService.getRoles() : [],
    email: authenticated ? authService.getEmail() : null,
    login: authService.login,
    logout: authService.logout,
    issueLocalToken: authService.issueLocalToken,
    isKeycloakConfigured: authService.isKeycloakConfigured,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
