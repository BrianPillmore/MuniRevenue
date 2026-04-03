import { requestMagicLink } from "../api";
import { refreshSession } from "../auth";
import { accountPath } from "../paths";
import { navigateTo } from "../router";
import { setPageMetadata } from "../seo";
import type { View } from "../types";

function currentNextPath(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get("next") || accountPath();
}

function initialLoginMessage(): string {
  const params = new URLSearchParams(window.location.search);
  if (params.get("verified") === "1") {
    return "Email verified. Request a sign-in link to continue.";
  }
  if (params.get("error") === "invalid-link") {
    return "That link is invalid or has expired. Request a new email.";
  }
  if (params.get("disabled") === "1") {
    return "Login is currently unavailable.";
  }
  return "";
}

export const loginView: View = {
  render(container: HTMLElement): void {
    setPageMetadata({
      title: "Login",
      description: "Sign in to MuniRevenue with a one-time magic link sent to your email.",
      path: window.location.pathname + window.location.search,
    });
    container.className = "view-login";
    container.innerHTML = `
      <div class="panel" style="padding:30px;max-width:720px;margin:0 auto;">
        <div class="section-heading">
          <p class="eyebrow">Account</p>
          <h2>Login</h2>
        </div>
        <p class="body-copy" style="max-width:54ch;margin-bottom:18px;">
          Enter your work email and MuniRevenue will send you the next email you need. First-time users verify their email first, then request a separate sign-in link. Forecasts, anomalies, and missed-filings require login.
        </p>
        <form id="login-form" style="display:grid;gap:14px;max-width:460px;">
          <label style="display:grid;gap:6px;">
            <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Email</span>
            <input id="login-email" type="email" required placeholder="you@city.gov"
              style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;" />
          </label>
          <button id="login-submit" type="submit" class="button" style="width:max-content;min-height:40px;padding:0 18px;">
            Email link
          </button>
        </form>
        <p id="login-message" class="body-copy" style="margin-top:16px;color:#5c6578;">${initialLoginMessage()}</p>
      </div>
    `;

    void refreshSession().then((session) => {
      if (session.authenticated) {
        navigateTo(currentNextPath(), { replace: true });
      }
    });

    const form = container.querySelector<HTMLFormElement>("#login-form");
    const emailInput = container.querySelector<HTMLInputElement>("#login-email");
    const messageEl = container.querySelector<HTMLElement>("#login-message");
    const submitButton = container.querySelector<HTMLButtonElement>("#login-submit");

    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const email = emailInput?.value.trim() ?? "";
      if (!email) return;

      if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = "Sending...";
      }
      if (messageEl) {
        messageEl.textContent = "";
      }

      try {
        const response = await requestMagicLink(email, currentNextPath());
        if (messageEl) {
          messageEl.textContent = response.message;
        }
      } catch (error) {
        if (messageEl) {
          messageEl.textContent = error instanceof Error
            ? error.message
            : "Unable to send a sign-in link right now.";
        }
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = "Email link";
        }
      }
    });
  },

  destroy(): void {
    /* no-op */
  },
};
