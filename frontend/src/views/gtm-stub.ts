/* GTM view stub — committed to repo so production builds succeed.
   The real gtm.ts is gitignored (private admin tool).
   Uses string concat to prevent Rollup from resolving the optional module. */

import type { View } from "../types";

let realGtm: View | null = null;

// String concat prevents Rollup from statically analyzing the import path
const gtmPath = "./gt" + "m";

export const gtmView: View = {
  render(container, params) {
    if (realGtm) {
      realGtm.render(container, params ?? {});
      return;
    }
    import(/* @vite-ignore */ gtmPath)
      .then((m: { gtmView: View }) => {
        realGtm = m.gtmView;
        realGtm.render(container, params ?? {});
      })
      .catch(() => {
        container.innerHTML = `<p style="padding:40px;text-align:center;color:#5c6578;">GTM module not available in this build.</p>`;
      });
  },
  destroy() {
    if (realGtm) realGtm.destroy();
  },
};
