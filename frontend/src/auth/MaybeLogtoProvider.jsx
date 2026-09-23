import { LogtoProvider } from '@logto/react';
import { isLogtoConfigured, logtoConfig } from './logtoConfig';

/**
 * Mounts `LogtoProvider` only when Logto is configured.
 *
 * A deployment without Logto credentials (CI, a fresh clone, an offline demo) then
 * renders exactly the tree it did before this integration — the SDK is not
 * initialised with an empty endpoint, and `useLogto()` is never called with no
 * provider above it.
 *
 * Position matters: this belongs at the very top of the tree in `main.jsx`, outside
 * `AuthProvider`. `AuthContext` reads Logto's `signOut` through a bridge component
 * to end the SSO session on logout, and a bridge above its own provider throws
 * "Must be used inside <LogtoProvider> context" — which unmounts the entire app,
 * login page included, rather than failing quietly.
 */
const MaybeLogtoProvider = ({ children }) =>
  isLogtoConfigured ? <LogtoProvider config={logtoConfig}>{children}</LogtoProvider> : children;

export default MaybeLogtoProvider;
