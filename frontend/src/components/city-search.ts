/* ══════════════════════════════════════════════
   Reusable city search / picker component
   ══════════════════════════════════════════════ */

import { searchCities } from "../api";
import type { CityListItem } from "../types";
import { escapeHtml } from "../utils";

export interface CitySearchOptions {
  /** Called when user selects a city from the dropdown */
  onSelect: (city: CityListItem) => void;
  /** Placeholder text for the search input */
  placeholder?: string;
  /** Optional jurisdiction type filter ("city" or "county") */
  type?: string;
}

interface CitySearchState {
  timeout: ReturnType<typeof setTimeout> | null;
  highlightIndex: number;
  results: CityListItem[];
}

/**
 * Render a city search component into the given container.
 * Returns a cleanup function that removes event listeners.
 */
export function renderCitySearch(
  container: HTMLElement,
  options: CitySearchOptions,
): () => void {
  const state: CitySearchState = {
    timeout: null,
    highlightIndex: -1,
    results: [],
  };

  container.innerHTML = `
    <div class="city-picker">
      <input
        class="city-search-input"
        type="text"
        placeholder="${options.placeholder ?? "Search cities or counties..."}"
        autocomplete="off"
        aria-label="Search cities"
        role="combobox"
        aria-expanded="false"
        aria-autocomplete="list"
        aria-controls="city-dropdown-list"
      />
      <ul
        id="city-dropdown-list"
        class="city-dropdown"
        role="listbox"
        aria-label="City search results"
      ></ul>
    </div>
  `;

  const input = container.querySelector<HTMLInputElement>(".city-search-input")!;
  const dropdown = container.querySelector<HTMLUListElement>(".city-dropdown")!;

  function openDropdown(): void {
    dropdown.classList.add("is-open");
    input.setAttribute("aria-expanded", "true");
  }

  function closeDropdown(): void {
    dropdown.classList.remove("is-open");
    dropdown.innerHTML = "";
    input.setAttribute("aria-expanded", "false");
    state.highlightIndex = -1;
    state.results = [];
  }

  function updateHighlight(): void {
    const items = dropdown.querySelectorAll<HTMLLIElement>(".city-dropdown-item");
    items.forEach((item, i) => {
      const active = i === state.highlightIndex;
      item.classList.toggle("is-focused", active);
      if (active) item.scrollIntoView({ block: "nearest" });
    });
  }

  function selectCity(city: CityListItem): void {
    input.value = city.name;
    closeDropdown();
    options.onSelect(city);
  }

  function renderResults(cities: CityListItem[]): void {
    state.results = cities;
    state.highlightIndex = -1;

    if (!cities.length) {
      dropdown.innerHTML =
        '<li class="city-dropdown-empty">No cities found.</li>';
      openDropdown();
      return;
    }

    dropdown.innerHTML = cities
      .map(
        (city, index) => `
          <li
            class="city-dropdown-item"
            role="option"
            tabindex="-1"
            data-index="${index}"
            data-copo="${escapeHtml(city.copo)}"
            data-name="${escapeHtml(city.name)}"
          >
            <span class="city-dropdown-name">${escapeHtml(city.name)}</span>
            <span class="city-dropdown-meta">
              ${city.county_name ? escapeHtml(city.county_name) + " County" : ""}${city.has_ledger_data ? "" : " (no data)"}
            </span>
          </li>
        `,
      )
      .join("");

    openDropdown();

    /* Click handlers on each item */
    dropdown.querySelectorAll<HTMLLIElement>(".city-dropdown-item").forEach((item) => {
      item.addEventListener("click", () => {
        const idx = Number(item.dataset.index);
        const city = state.results[idx];
        if (city) selectCity(city);
      });
    });
  }

  /* Debounced input handler */
  function onInput(): void {
    const query = input.value.trim();

    if (state.timeout) clearTimeout(state.timeout);

    if (query.length < 2) {
      closeDropdown();
      return;
    }

    state.timeout = setTimeout(async () => {
      try {
        const response = await searchCities(query, options.type, 50);
        renderResults(response.items);
      } catch {
        dropdown.innerHTML =
          '<li class="city-dropdown-empty">Search failed. Try again.</li>';
        openDropdown();
      }
    }, 250);
  }

  /* Keyboard navigation */
  function onKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape") {
      closeDropdown();
      return;
    }

    if (!dropdown.classList.contains("is-open")) return;

    const total = state.results.length;
    if (total === 0) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      state.highlightIndex = Math.min(state.highlightIndex + 1, total - 1);
      updateHighlight();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      state.highlightIndex = Math.max(state.highlightIndex - 1, 0);
      updateHighlight();
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (state.highlightIndex >= 0 && state.highlightIndex < total) {
        selectCity(state.results[state.highlightIndex]);
      }
    }
  }

  /* Outside click */
  function onDocumentClick(event: MouseEvent): void {
    const target = event.target as HTMLElement;
    if (!target.closest(".city-picker")) {
      closeDropdown();
    }
  }

  /* Attach listeners */
  input.addEventListener("input", onInput);
  input.addEventListener("keydown", onKeydown);
  document.addEventListener("click", onDocumentClick);

  /* Cleanup function */
  return () => {
    if (state.timeout) clearTimeout(state.timeout);
    input.removeEventListener("input", onInput);
    input.removeEventListener("keydown", onKeydown);
    document.removeEventListener("click", onDocumentClick);
  };
}

/**
 * Set the value of the search input programmatically.
 */
export function setCitySearchValue(container: HTMLElement, value: string): void {
  const input = container.querySelector<HTMLInputElement>(".city-search-input");
  if (input) input.value = value;
}
