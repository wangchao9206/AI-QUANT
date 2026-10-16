# Global Instrument Navigation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a global searchable futures selector plus a persistent sidebar instrument list, synchronized through Pinia and the URL.

**Architecture:** Keep the instrument catalog and selected symbol in the existing market store. Add one reusable Vue picker in the application shell, persist only recent successful symbols, and use the `symbol` route query as the refresh/share boundary. Existing views continue to consume `useDashboard` and never receive generated fallback data.

**Tech Stack:** Vue 3, Pinia, Vue Router, TypeScript, Vitest, Docker/Nginx.

---

### Task 1: Workspace instrument state

**Files:**
- Modify: `frontend/src/stores/market.ts`
- Modify: `frontend/src/stores/market.spec.ts`

1. Add tests for deduplicated recent-symbol persistence after successful loads.
2. Add safe local-storage parsing and a five-item recent-symbol limit.
3. Add catalog-backed helpers for resolving product labels and sidebar symbols.
4. Run `npm --prefix frontend test -- frontend/src/stores/market.spec.ts`.

### Task 2: Searchable global picker

**Files:**
- Create: `frontend/src/components/InstrumentPicker.vue`
- Create: `frontend/src/components/InstrumentPicker.spec.ts`

1. Add a failing test with a two-exchange catalog and verify name/symbol search.
2. Implement accessible popover/bottom-sheet behavior and exact-symbol entry.
3. Route selection through `router.replace` and the existing store loader.
4. Verify selection updates the URL and closes the picker.

### Task 3: Shell and route integration

**Files:**
- Modify: `frontend/src/layouts/AppShell.vue`
- Modify: `frontend/src/layouts/AppShell.spec.ts`
- Modify: `frontend/src/composables/useDashboard.ts`
- Modify: `frontend/src/views/MarketView.vue`

1. Place the picker in the top bar and current/recent instruments in the desktop sidebar.
2. Preserve the symbol query in all navigation links.
3. Hydrate data loads from a valid direct-link query and remove the duplicate market-page form.
4. Test desktop/mobile navigation and URL persistence.

### Task 4: Acceptance and deployment

**Files:**
- Modify: `docs/operations.md`
- Modify: `docs/verification.md`

1. Run the full frontend test suite and production build.
2. Rebuild only the frontend Docker image and verify container health.
3. Smoke-test the HTML entry and representative all-market APIs.
4. Record the verified global-selection behavior and current request baseline.
5. Commit and push the completed batch.
