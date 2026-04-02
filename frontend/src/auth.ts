import { getAuthSession, logoutAuth } from "./api";
import { loginPath } from "./paths";
import type { AuthSessionResponse } from "./types";

let sessionState: AuthSessionResponse = {
  authenticated: false,
  user: null,
};

let sessionPromise: Promise<AuthSessionResponse> | null = null;
let sessionInitialized = false;

function emitAuthChanged(): void {
  window.dispatchEvent(new CustomEvent<AuthSessionResponse>("munirev:auth-changed", {
    detail: sessionState,
  }));
}

function redirectTo(path: string): void {
  history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function getSessionState(): AuthSessionResponse {
  return sessionState;
}

export async function refreshSession(force = false): Promise<AuthSessionResponse> {
  if (!force && sessionInitialized) {
    return sessionState;
  }

  if (!force && sessionPromise) {
    return sessionPromise;
  }

  sessionPromise = getAuthSession()
    .then((response) => {
      sessionState = response;
      sessionInitialized = true;
      emitAuthChanged();
      return response;
    })
    .catch(() => {
      sessionState = { authenticated: false, user: null };
      sessionInitialized = true;
      emitAuthChanged();
      return sessionState;
    })
    .finally(() => {
      sessionPromise = null;
    });

  return sessionPromise;
}

export async function ensureSignedIn(nextPath: string): Promise<boolean> {
  const session = await refreshSession();
  if (session.authenticated) {
    return true;
  }
  redirectTo(loginPath(nextPath));
  return false;
}

export async function logoutAndRedirect(): Promise<void> {
  try {
    await logoutAuth();
  } finally {
    sessionState = { authenticated: false, user: null };
    sessionInitialized = true;
    emitAuthChanged();
    redirectTo(loginPath());
  }
}
