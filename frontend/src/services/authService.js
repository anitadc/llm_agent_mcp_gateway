import Keycloak from "keycloak-js";

const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL,
  realm: import.meta.env.VITE_KEYCLOAK_REALM,
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID,
});

let initPromise = null;

function init() {
  if (!initPromise) {
    initPromise = keycloak.init({
      onLoad: "check-sso",
      pkceMethod: "S256",
      silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
    });
  }
  return initPromise;
}

function login() {
  return keycloak.login();
}

function logout() {
  return keycloak.logout({ redirectUri: window.location.origin });
}

async function getToken() {
  if (!keycloak.token) return null;
  try {
    await keycloak.updateToken(30);
  } catch {
    await logout();
    return null;
  }
  return keycloak.token;
}

function getRoles() {
  return keycloak.tokenParsed?.realm_access?.roles ?? [];
}

function getEmail() {
  return keycloak.tokenParsed?.email ?? null;
}

function isAuthenticated() {
  return Boolean(keycloak.authenticated);
}

export const authService = { init, login, logout, getToken, getRoles, getEmail, isAuthenticated };
