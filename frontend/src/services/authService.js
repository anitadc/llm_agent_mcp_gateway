import Keycloak from "keycloak-js";

const KEYCLOAK_URL = import.meta.env.VITE_KEYCLOAK_URL;
const KEYCLOAK_REALM = import.meta.env.VITE_KEYCLOAK_REALM;
const KEYCLOAK_CLIENT_ID = import.meta.env.VITE_KEYCLOAK_CLIENT_ID;

export const isKeycloakConfigured = Boolean(KEYCLOAK_URL && KEYCLOAK_REALM && KEYCLOAK_CLIENT_ID);

const LOCAL_TOKEN_KEY = "llm_gateway_token";

let keycloak = null;
let initPromise = null;

function parseJwt(token) {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = parts[1];
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    return json;
  } catch {
    return null;
  }
}

function _localGetToken() {
  return localStorage.getItem(LOCAL_TOKEN_KEY);
}

function _localSetToken(token) {
  if (token) localStorage.setItem(LOCAL_TOKEN_KEY, token);
  else localStorage.removeItem(LOCAL_TOKEN_KEY);
}

function init() {
  if (isKeycloakConfigured) {
    if (!keycloak) {
      keycloak = new Keycloak({ url: KEYCLOAK_URL, realm: KEYCLOAK_REALM, clientId: KEYCLOAK_CLIENT_ID });
    }
    if (!initPromise) {
      initPromise = keycloak.init({
        onLoad: "check-sso",
        pkceMethod: "S256",
        silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
      });
    }
    return initPromise;
  }

  return new Promise((resolve) => {
    const token = _localGetToken();
    if (!token) return resolve(false);

    const parsed = parseJwt(token);
    if (!parsed || !parsed.exp) return resolve(false);

    const now = Math.floor(Date.now() / 1000);
    resolve(parsed.exp > now);
  });
}

function login() {
  if (isKeycloakConfigured) return keycloak.login();
  return null;
}

function logout() {
  if (isKeycloakConfigured) return keycloak.logout({ redirectUri: window.location.origin });
  _localSetToken(null);
  return null;
}

async function getToken() {
  if (isKeycloakConfigured) {
    if (!keycloak?.token) return null;
    try {
      await keycloak.updateToken(30);
    } catch {
      await logout();
      return null;
    }
    return keycloak.token;
  }

  return _localGetToken();
}

async function issueLocalToken({ user_id, email, tenant_id = null, roles = [], groups = [], expires_seconds = 3600 }) {
  const res = await fetch("/v1/auth/local/issue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id, email, tenant_id, roles, groups, expires_seconds }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Local token issuance failed: ${res.status} ${text}`);
  }

  const json = await res.json();
  _localSetToken(json.token);

  let session = null;
  try {
    session = await getSession();
  } catch (error) {
    console.warn("Local token exchange failed", error);
  }

  return { token: json.token, session };
}

async function getSession() {
  const token = _localGetToken();
  if (!token) throw new Error("No token available");

  const res = await fetch("/v1/auth/token/exchange", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Session exchange failed: ${res.status} ${text}`);
  }

  return res.json();
}

function getRoles() {
  if (isKeycloakConfigured) return keycloak.tokenParsed?.realm_access?.roles ?? [];

  const token = _localGetToken();
  const parsed = token ? parseJwt(token) : null;
  return parsed?.roles ?? [];
}

function getEmail() {
  if (isKeycloakConfigured) return keycloak.tokenParsed?.email ?? null;

  const token = _localGetToken();
  const parsed = token ? parseJwt(token) : null;
  return parsed?.email ?? null;
}

function isAuthenticated() {
  if (isKeycloakConfigured) return Boolean(keycloak?.authenticated);

  const token = _localGetToken();
  const parsed = token ? parseJwt(token) : null;
  if (!parsed || !parsed.exp) return false;

  const now = Math.floor(Date.now() / 1000);
  return parsed.exp > now;
}

export const authService = {
  init,
  login,
  logout,
  getToken,
  getRoles,
  getEmail,
  isAuthenticated,
  issueLocalToken,
  getSession,
  isKeycloakConfigured,
};
