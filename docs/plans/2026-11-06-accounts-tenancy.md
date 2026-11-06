# Accounts and tenancy implementation plan / ADR

**Goal:** Verified SMTP email registration, password/session recovery, administrators, tenant membership and actual isolation of existing private records, with a stable integration API.

**Architecture:** Dedicated Spring Boot identity-service with PostgreSQL; opaque revocable HttpOnly sessions; Gateway online introspection and signed internal identities; PostgreSQL RLS over paper_trading and chanlun records. New users receive personal workspaces after verifying email; existing records belong to tenant `00000000-0000-0000-0000-000000000001`. Initial password is username + `123456`; password change is mandatory before business access. Shared reading catalog seed rows are read-only across tenants; other books are tenant private.

## Decisions

1. A separate identity service centralizes lifecycle and future SaaS integration. Embedding accounts in algorithm-service couples identity to market workers; deploying an external identity provider adds an unrequested external operational dependency. Keep a provider/subject mapping table for future OIDC identities and implement scoped, tenant-bound integration API keys now; do not claim an OAuth provider implementation.
2. Sessions are server-side, hashed at rest and revocable; CSRF double-submit cookie/header checks protect cookie-authenticated mutations. API keys use Authorization Bearer and explicit scopes, no browser token storage. A selected tenant is always validated against active membership; platform admin does not automatically see every tenant's private data.
3. All personal tables use FORCE RLS. HTTP processing starts a transaction with SET LOCAL ROLE to a NOLOGIN/NOBYPASSRLS role and a verified tenant setting, so even the existing privileged pooled connection cannot bypass isolation within the request. Context is transaction-local, compatible with PgBouncer transaction pooling. Existing local credentials are retained for migration/worker administration; SaaS deployments should separate migration/worker credentials as documented.
4. Composite tenant foreign keys prevent references to another tenant's parents; per-tenant default strategy identities avoid global seed ID collisions. Trusted background monitor writes preserve the parent tenant.
5. SMTP is configurable via environment; unavailable/failed delivery does not masquerade as success or reveal verification tokens. Confirmation/reset tokens are single-use, hashed, expiring and rate-limited. Passwords use BCrypt cost 12; passwords/tokens/SMTP credentials never appear in audit records.

## Implementation and verification

- Add identity-service schema, bootstrap admin, mail transport, login/register/verify/resend/forgot/reset/change/logout/sessions, tenant create/switch/member management, admin controls, audit and API keys.
- Add tenant-security shared module, Gateway filter, protected CORS/CSRF settings, private table migrations and monitor context propagation.
- Add login/register/verify/reset/forced-password and account/admin UI; route guards, CSRF-aware request handling, namespace browser notes by user and tenant; remount workspace on tenant switch.
- Update Docker build contexts, compose dependencies and SMTP/identity secrets configuration; add operations guide.
- Test credential hashing, token replay/expiry, CSRF, forced changes, session/key revocation, memberships/roles, spoofed identity headers, tenant RLS and cross-tenant references. Run existing relevant Java tests, Vue tests, type check and build. SMTP transport can be verified against a local SMTP fixture; actual external delivery requires a configured provider, which the user does not yet have.
