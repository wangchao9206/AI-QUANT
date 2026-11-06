# Chinese Instrument Names Implementation Plan

**Goal:** All displayed futures/options have a Chinese primary name, with the exact symbol retained as auxiliary information; API identity and saved data stay unchanged.

**Architecture:** Central reactive name resolver seeded from the deployed observed domestic catalog and refreshed from catalog responses. Parse provider prefixes, continuous aliases, delivery codes and domestic option formats; preserve CZCE three-digit delivery codes without guessing a decade. Resolve index option roots and index underlyings explicitly. Unknown identifiers receive an honest Chinese unnamed label with the original identifier. Apply the shared resolver to contract selectors, quotes, charts, options research, monitors/history, portfolio/research and saved records.

**Tech Stack:** Vue/TypeScript, existing market/options APIs and Vitest.

1. Add the observed product-name snapshot and shared Chinese resolver, with tests for continuous/delivery/option formats, ambiguous M suffixes, index underlyings, dynamic catalog overrides and unknown identifiers.
2. Update market/options catalog registration and presentation surfaces. Preserve values, keys, routes and request symbols. Keep user-provided task names; default new task names become Chinese.
3. Run type check, relevant/full frontend tests, production build and desktop/mobile browser checks. Preserve old frontend image, deploy only frontend in ai-quant, verify static asset equality and public authentication boundaries. No database migration or account changes.

## User direction and status

Chinese presentation implemented across futures/options selectors, watch views, charts, monitors and saved records. Earlier frontend regression passed 357 tests; type checking, local build and isolated desktop/mobile Chinese-label checks completed. The user subsequently cancelled deployment, stopped Docker, and requested no further checks. Stop validation work and publish all current source changes, including the latest data modules, to the existing Git repository. Do not restart containers or deploy this update.
