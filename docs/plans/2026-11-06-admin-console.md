# Administration console implementation plan

**Goal:** A separate administration workspace for tenant/user lifecycle, tenant-scoped custom roles, permissions, menu configuration, grants and searchable audit/operation history.

**Architecture:** Extend identity-service and its existing PostgreSQL schema with additive migrations; preserve fixed OWNER/ADMIN authority and existing RLS. Custom role permissions override ordinary MEMBER/VIEWER business privileges and are checked online at Gateway introspection. Platform administration is never granted by an editable business permission. A tenant manager may only manage the current tenant and cannot change global account status, platform privilege or another tenant's roles. Keep menu configuration separate from API authorization.

## Decisions and alternatives

- Recommended: tenant-scoped role definitions and assignments, a fixed validated permission catalog, and one global route-safe menu catalog. This reuses existing identity, session revocation and membership boundaries.
- Per-user ad hoc permission flags would make grants hard to review; arbitrary API-route permissions would allow accidental creation of new administration privileges. Neither is needed.
- Database audit stores authorization/configuration before/after snapshots transactionally. HTTP operation history records actor, tenant, method, path, status, duration and trace ID, excluding credentials, tokens, query strings and request bodies. Log security/admin actions and business mutations; omit automatic read-only market polling.

## Steps

1. Add identity V2 tables for access roles, permissions, assignments, menus and operation logs; extend audit fields and seed existing navigation.
2. Implement administration list/search/pagination, tenant create/rename/enable, user provision/profile/status/reset, membership/role assignment, custom role lifecycle, safe menu tree editing, session/key revocation and audit queries; export the current page to CSV in the browser.
3. Enforce effective business permissions online, expose permitted navigation in /me, add operation recording at identity service and Gateway. Preserve initial password changes, CSRF, API-key scope caps and last-owner/platform-admin protections.
4. Add /admin with tenant/user/roles/menus/access/activity/history sections, explicit confirmations for revocations and privilege changes. Wire dynamic navigation and route guards, preserving existing account preferences.
5. Validate with disposable PostgreSQL, cross-tenant/delegation tests, no-secret audit tests, permission revocation tests, frontend interaction tests and build. Deploy identity/Gateway/frontend into the same ai-quant project after a new backup and verify using a temporary local fixture identity without modifying the real administrator's password or permissions.

## Completion

Implemented and deployed. See [administration behavior](../admin-console.md) and [deployment evidence](../deployment-admin-2026-11-06.md). Authenticated HTTP checks used the deployed image with an isolated disposable database; the existing live administrator had already changed their password and was preserved.
