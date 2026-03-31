/* ══════════════════════════════════════════════
   Loading indicator component
   ══════════════════════════════════════════════ */

export function showLoading(container: HTMLElement): void {
  container.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:center;padding:60px;gap:12px;">
      <div class="loading-spinner"></div>
      <span style="color:var(--muted);font-size:0.9rem;">Loading data...</span>
    </div>
  `;
}
