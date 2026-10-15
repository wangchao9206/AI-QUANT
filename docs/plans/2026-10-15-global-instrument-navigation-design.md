# Global Instrument Navigation Design

## Intent

Make the selected futures instrument a workspace-level context instead of a
market-page-only form value. A user should be able to switch products from any
screen, keep that selection while navigating, refresh the page without losing
it, and share the exact view by URL.

## Interaction model

The top bar gains a compact instrument control showing the selected symbol and
observed product name. Activating it opens a restrained search surface grouped
by exchange. Search matches product name, root symbol, main symbol, exchange,
and individual listed contracts. Keyboard Enter accepts an exact valid symbol;
Escape closes the surface. On narrow screens the same surface becomes a bottom
sheet rather than a small desktop popover.

The dark sidebar gains a persistent market strip below navigation. It shows the
current instrument and up to five recently successful selections. Before any
history exists it uses a small cross-exchange starter set, but only displays
entries that exist in the live catalog. This is navigation metadata, never a
price or generated market observation.

## State and URL

Pinia remains the single owner of the selected symbol and recently visited
symbols. Recent symbols are persisted locally only after a complete successful
load. The router query `?symbol=...` is the durable navigation representation.
All primary navigation links preserve it; direct URL loads hydrate the store.
An invalid query is ignored and replaced with the current valid symbol.

## Failure behavior and accessibility

Catalog failure does not block manual symbol entry or existing business data.
The picker reports catalog loading/failure inline, maintains labelled controls,
supports focus-visible states and exposes dialog/listbox semantics. Selecting a
symbol uses the existing real-data loading and explicit `503` warm-up behavior;
no demonstration fallback is introduced.

## Verification

Unit tests cover recent-symbol persistence, search matching, selection, and URL
preservation. Existing frontend tests and the production build must pass. The
Docker frontend is rebuilt, then direct navigation, cross-page selection and
representative real-data APIs are smoke-tested.
