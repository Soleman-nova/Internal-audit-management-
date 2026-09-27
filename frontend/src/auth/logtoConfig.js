import { UserScope } from '@logto/react';

/**
 * Logto SSO configuration for the audit system.
 *
 * Ported from the `simple signin/` reference app's `src/auth/config.ts`, minus the
 * two plain-HTTP workarounds it needed and we deliberately do not have:
 * `cryptoSubtlePolyfill.ts` (a JS SHA-256 for PKCE) and `disableIdTokenVerification.ts`
 * (which made the SDK accept a token without checking who signed it).
 *
 * That reference app is **not part of this repository** — it was a separate git
 * checkout that the parent only ever recorded as a bare submodule pointer, and it
 * has since been untracked (`.gitignore`). The comparison is kept because it
 * explains why these two workarounds are absent; the path will not resolve on a
 * fresh clone.
 *
 * Both exist there because the reference runs on `http://<LAN-IP>:5173`, which is an
 * insecure context — `crypto.subtle` is `undefined`, so PKCE cannot be computed and
 * ES384 signatures cannot be verified. Running on `http://localhost:5173` instead
 * makes the browser treat the origin as trustworthy, the real `crypto.subtle` is
 * present, and the SDK's default `DefaultJwtVerifier` verifies signatures properly.
 *
 * The cost of that choice is that the app will not work on a bare LAN IP. That is
 * accepted, not accidental — see the README note in the plan.
 */

/**
 * Where Logto sends the browser back to after sign-in, and after sign-out.
 *
 * Derived from the origin the app is actually served from rather than hardcoded.
 * This is load-bearing, not tidiness: the SDK keeps the PKCE `code_verifier` and
 * `state` in the *initiating origin's* localStorage, so a sign-in started on one
 * origin and finished on another can never be completed — the callback cannot see
 * the verifier it needs to exchange the code.
 *
 * Both must be registered in Logto Console → Applications with an exact match
 * (scheme, host, port and path all count), and must point at this Vite app — never
 * at Logto's own port, which serves the Console and cannot complete a sign-in.
 */
export const redirectUri = `${window.location.origin}/callback`;
export const postSignOutRedirectUri = `${window.location.origin}/login`;

/**
 * Whether Logto is configured for this build.
 *
 * Vite inlines `import.meta.env` at build time, so this is a constant. It lets the
 * whole feature degrade to a no-op — no provider mounted, no button rendered — for
 * anyone running without Logto credentials (CI, a fresh clone, an offline demo).
 * Nothing else in the app needs to know Logto exists.
 */
export const isLogtoConfigured = Boolean(
  import.meta.env.VITE_LOGTO_ENDPOINT && import.meta.env.VITE_LOGTO_APP_ID
);

export const logtoConfig = {
  endpoint: import.meta.env.VITE_LOGTO_ENDPOINT,
  appId: import.meta.env.VITE_LOGTO_APP_ID,

  /**
   * Deliberately the small set this app actually consumes.
   *
   * The reference app also requested Roles, Organizations, OrganizationRoles,
   * Identities and Phone, because it displays them. Here Django is the authority on
   * roles and organization scoping, so those claims would be fetched and ignored —
   * and requesting a scope the Logto instance has not been set up to grant fails the
   * whole authorization request rather than being harmlessly dropped.
   *
   *   Profile    -> `username` and `name`, the primary identity claims we match on
   *   Email      -> `email`, the fallback identity claim
   *   CustomData -> `custom_data`, where an EEU employee ID may have been stashed
   *
   * `username` is what `apps/accounts/logto.py` matches against `User.employee_id`.
   *
   * Note there is no `resources`/`apiResource` entry. No API resource is registered
   * in this Logto instance, and sending an unregistered resource indicator fails
   * every sign-in with `invalid_target`.
   */
  scopes: [UserScope.Profile, UserScope.Email, UserScope.CustomData],
};
