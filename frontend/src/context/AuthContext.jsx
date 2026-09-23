import React, { createContext, useContext, useState, useEffect } from 'react';
import { useLogto } from '@logto/react';
import { authApi, clearSession } from '../api/apiClient';
import { isLogtoConfigured, postSignOutRedirectUri } from '../auth/logtoConfig';

const AuthContext = createContext(null);

/** Carries Logto's `signOut` down to AuthInner. */
const LogtoSignOutContext = createContext(null);

/**
 * Publishes Logto's `signOut` to the auth context, when Logto is configured.
 *
 * A component rather than a `useLogto()` call inside AuthProvider because that hook
 * throws outside `<LogtoProvider>`, and AuthProvider has to work in both worlds —
 * with Logto configured and without. Mounted only when it *is* configured, so the
 * hook is never called with no provider above it, which is what the rules of hooks
 * require.
 */
const LogtoSignOutBridge = ({ children }) => {
  const { signOut } = useLogto();
  return (
    <LogtoSignOutContext.Provider value={signOut}>{children}</LogtoSignOutContext.Provider>
  );
};

const AuthInner = ({ children }) => {
  // Null whenever Logto is not configured, or above the bridge — `useContext` is
  // safe here in a way `useLogto` would not be, since this context has a default.
  const logtoSignOut = useContext(LogtoSignOutContext);

  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem('user');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });

  const [theme, setThemeState] = useState(() => {
    return localStorage.getItem('theme') || 'light';
  });

  const [language, setLanguageState] = useState(() => {
    return localStorage.getItem('language') || 'en';
  });

  // Apply theme class to document root element
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
      root.setAttribute('data-theme', 'dark');
    } else {
      root.classList.remove('dark');
      root.setAttribute('data-theme', 'light');
    }
    localStorage.setItem('theme', theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem('language', language);
  }, [language]);

  const login = async (employeeId, password) => {
    const data = await authApi.login(employeeId, password);
    const currentUser = authApi.getCurrentUser();
    setUser(currentUser);
    return data;
  };

  /** Finish a Logto sign-in by trading its ID token for our own session.
   *
   * The hard redirect out to Logto and back happens in the SDK; this is only the
   * last step, called from the `/callback` page. What lands in storage afterwards is
   * identical to what `login` stores, so nothing downstream needs to know which
   * route the user took.
   */
  const loginWithLogto = async (idToken) => {
    const data = await authApi.logtoExchange(idToken);
    setUser(authApi.getCurrentUser());
    return data;
  };

  const { signIn, signOut, isAuthenticated, getIdTokenClaims } = useLogto(); 

  const logout = () => {
    // A Logto session outlives ours: Logto keeps its own session cookie, so
    // dropping only our tokens would leave the next "Sign in with Logto" completing
    // silently, with no credential prompt. signOut ends that session too and lands
    // back on /login via postSignOutRedirectUri.
    //
    // Only for sessions that came from Logto — someone who signed in with an
    // employee ID has no Logto session to end, and sending them through Logto's
    // redirect would be a pointless round trip through a service they never used.
    if (logtoSignOut && authApi.getAuthMethod() === 'logto') {
      // Clear our session *first*, and exactly once, in both outcomes.
      //
      // `signOut` leaves the page — it redirects to Logto's end-session endpoint
      // and back to /login — and the navigation is a full load, not a route
      // change. AuthProvider re-seeds `user` from localStorage on the way back, so
      // without this the tokens survive the round trip and the "signed out" user
      // is silently signed straight back in.
      //
      // Clearing before the redirect also means a Logto that is unreachable, or an
      // end-session call that never returns, still leaves the user signed out here
      // rather than stranded in a live session. The SSO cookie is the only thing
      // that goes un-ended, and there is nothing useful to do about that from a
      // browser that cannot reach Logto.
      clearSession();
      setUser(null);
      // logtoSignOut(postSignOutRedirectUri);
      signOut("http://localhost:5173");
      return;
    }
    authApi.logout();
    setUser(null);
  };

  const updateUser = async (profileData) => {
    const updated = await authApi.updateProfile(profileData);
    setUser(updated);
    return updated;
  };

  const setTheme = (newTheme) => {
    setThemeState(newTheme);
  };

  const setLanguage = (newLang) => {
    setLanguageState(newLang);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        setUser,
        theme,
        setTheme,
        language,
        setLanguage,
        login,
        loginWithLogto,
        logout,
        updateUser,
        isAuthenticated: !!user && !!localStorage.getItem('accessToken'),
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

/**
 * Mounts the Logto sign-out bridge only when Logto is configured, so the tree is
 * identical to the pre-Logto one for anyone running without it.
 *
 * `isLogtoConfigured` is a build-time constant (Vite inlines `import.meta.env`), so
 * this branch never changes at runtime and AuthInner is never remounted by it.
 */
export const AuthProvider = ({ children }) =>
  isLogtoConfigured ? (
    <LogtoSignOutBridge>
      <AuthInner>{children}</AuthInner>
    </LogtoSignOutBridge>
  ) : (
    <AuthInner>{children}</AuthInner>
  );

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export default AuthContext;
