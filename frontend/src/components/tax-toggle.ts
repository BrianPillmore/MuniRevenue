/* ══════════════════════════════════════════════
   Tax type toggle component
   ══════════════════════════════════════════════ */

import { escapeHtml } from "../utils";

/**
 * Render a row of toggle buttons for tax types.
 *
 * @param container  Element to render into
 * @param types      Array of tax type strings (e.g. ["sales", "use", "lodging"])
 * @param active     Currently active tax type
 * @param onChange   Callback when user selects a different type
 */
export function renderTaxToggle(
  container: HTMLElement,
  types: string[],
  active: string,
  onChange: (type: string) => void,
): void {
  if (types.length <= 1) {
    container.innerHTML = "";
    return;
  }

  const buttonsHtml = types
    .map((type) => {
      const isActive = type === active;
      const label = type.charAt(0).toUpperCase() + type.slice(1);
      return `
        <button
          class="tax-toggle-btn${isActive ? " is-active" : ""}"
          data-tax-type="${escapeHtml(type)}"
          aria-pressed="${isActive}"
        >
          ${escapeHtml(label)}
        </button>
      `;
    })
    .join("");

  container.innerHTML = `
    <div class="tax-type-toggle">
      <div class="tax-toggle-row" role="group" aria-label="Tax type">${buttonsHtml}</div>
    </div>
  `;

  /* Attach click handlers */
  container.querySelectorAll<HTMLButtonElement>(".tax-toggle-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const taxType = btn.dataset.taxType;
      if (!taxType || taxType === active) return;

      /* Update visual state */
      container.querySelectorAll(".tax-toggle-btn").forEach((b) => {
        b.classList.remove("is-active");
        b.setAttribute("aria-pressed", "false");
      });
      btn.classList.add("is-active");
      btn.setAttribute("aria-pressed", "true");

      onChange(taxType);
    });
  });
}
