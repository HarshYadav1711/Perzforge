# Task 03 — Story A1: Admin-managed accounts
# Attach: AGENTS.md · docs/PRD.md (Epic A) · docs/ARCHITECTURE.md (§7.1)
# Pre-req: A2, A3 merged

Implement story A1: the platform is invite-only; only admins create accounts.

Scope:
1. `POST /api/v1/admin/users` (get_current_admin): body email + role
   (default "user"). Generates a strong temporary password
   (secrets.token_urlsafe(12)), returns it once, sets
   must_change_password=true. 409 on duplicate email.
2. `GET /api/v1/admin/users` — paginated list (id, email, role, created_at,
   must_change_password). Never password hashes.
3. `POST /api/v1/auth/change-password` (authenticated): old + new password;
   min length 12; on success clears must_change_password and revokes all of
   the user's refresh-token families (force re-login everywhere).
4. Login behavior: while must_change_password is true, login succeeds but
   every OTHER authenticated route returns 403 with detail
   "password change required" — implement as a dependency layered into
   get_current_user, so no route can forget it.
5. `DELETE /api/v1/admin/users/{id}` — soft-disable (add `disabled` bool to
   User + migration); disabled users fail auth everywhere. Admins cannot
   disable themselves (409).
6. Tests per criterion, including: temp-password login → blocked from
   /keys until change → change → access works; disabled user's JWT AND
   API keys both dead.

Out of scope: self-registration, email sending, password reset flows.

Touches auth — flag for human review.

Commit message:
feat(A1): invite-only account lifecycle with forced credential rotation

Admins provision users with single-reveal temporary passwords; a layered
auth dependency locks all routes except password change until rotation
completes. Disabling a user severs both session and API-key access paths
atomically. Closes the account-management loop for the private beta.
