import { useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useHandleSignInCallback, useLogto } from '@logto/react';
import { useAuth } from '../../context/AuthContext';
import Spinner from '../../components/ui/Spinner';

/**
 * The redirect target Logto sends the browser back to after sign-in.
 *
 * Two things happen here in sequence: the SDK redeems the authorization code for
 * tokens (that is `useHandleSignInCallback`), and then we hand the resulting ID
 * token to our own backend, which verifies it and returns the SimpleJWT pair the
 * rest of the app expects. Only after that exchange does a session exist — a Logto
 * sign-in on its own grants no access to this system.
 *
 * This page must stay outside `ProtectedRoute`. Its whole job is to *create* a
 * session, so guarding it on already having one would redirect away before the
 * exchange could run.
 */
const LogtoCallbackPage = () => {
  const navigate = useNavigate();
  const { loginWithLogto } = useAuth();
  const { getIdToken, getIdTokenClaims } = useLogto();
  const [exchangeError, setExchangeError] = useState(null);

  // What this page load was handed by Logto, read synchronously from the URL.
  //
  // Read here rather than from the hook because the hook works it out
  // asynchronously (`isSignInRedirected` is a promise), and there is a render in
  // between where its `isLoading` is false for a genuine sign-in and false for a
  // stray visit alike — indistinguishable, so acting on it would either break real
  // sign-ins or strand this page on a spinner forever.
  const authResponse = useMemo(() => {
    const params = new URLSearchParams(window.location.search);
    return {
      // Only together do these mean "there is a code to redeem". `state` is the
      // CSRF check the exchange depends on; one without the other is not a
      // response we can do anything with.
      hasCode: params.has('code') && params.has('state'),
      error: params.get('error'),
      errorDescription: params.get('error_description'),
    };
  }, []);

  // Guards against a second run of the callback below.
  //
  // React StrictMode double-invokes effects in development, and the exchange is not
  // free to repeat: it mints a token pair and writes a LOGIN entry to the audit
  // trail, so an unguarded double-fire puts two sign-ins in the trail for one
  // sign-in. A ref rather than state because it must flip synchronously — the
  // second invocation runs before any re-render.
  const started = useRef(false);

  const { error } = useHandleSignInCallback(() => {
    // `useHandleSignInCallback` types this callback as `() => void` and does not
    // await it, so the exchange is driven explicitly here rather than returned.
    if (started.current) return;
    started.current = true;

    void (async () => {
      try {
        const idToken = await getIdToken();
        if (!idToken) {
          throw new Error('Logto completed the sign-in but returned no ID token.');
        }

        // ── TEMPORARY debug logging — remove once you have seen what you need ──
        //
        // The claims are what the backend matches an identity on, in this order:
        // `custom_data.EEUID`, then `username`, then `email`. If the exchange below
        // answers 403, the reason is on one of these lines — an account created
        // automatically is keyed on `custom_data.EEUID` alone, so a token that is
        // missing it can still sign in as an existing user but can never create
        // one. `sub` is the stable Logto identifier to search the Console with.
        //
        // Logged before the exchange rather than after, so it is still on screen
        // when the exchange is the thing that fails.
        //
        // React StrictMode double-invokes effects in development, so expect these
        // twice.
        const claims = await getIdTokenClaims();
        console.log('[logto] id_token_claims', claims);
        console.log('[logto] custom_data.EEUID', claims?.custom_data?.EEUID);
        console.log('[logto] username        ', claims?.username);
        console.log('[logto] email           ', claims?.email);
        console.log('[logto] custom_data     ', claims?.custom_data);
        console.log('[logto] sub             ', claims?.sub);
        // ────────────────────────────────────────────────────────────────────────

        const data = await loginWithLogto(idToken);

        // Same temporary block: the exchange result, which is this system's own
        // SimpleJWT pair plus the user row the identity resolved to. `data.user.role`
        // and `data.user.employee_id` are the ones worth checking — they come from
        // Django and are what the capability checks read.
        console.log('[logto] exchange response', data);
        // ────────────────────────────────────────────────────────────────────────

        // `replace` so Back does not land on /callback, which would try to redeem an
        // authorization code that has already been spent.
        navigate('/dashboard', { replace: true });
      } catch (err) {
        setExchangeError(err);
      }
    })();
  });

  // Three ways a sign-in fails, most specific first: the SDK's own error, our
  // backend call, then an OAuth failure Logto put in the query string.
  //
  // That third one matters for the commonest setup mistake by far — an origin that
  // was never registered in Logto Console comes back as `?error=invalid_redirect_uri`.
  // When a sign-in session is present the SDK surfaces it through `error` above, but
  // when the URL is reached without one (bookmarked, hand-edited, or a stale tab) the
  // SDK ignores it entirely and the page would otherwise spin forever. Reporting it
  // is also just more useful than a generic failure: the code names the problem.
  const failure =
    error ??
    exchangeError ??
    (authResponse.error
      ? new Error(
          authResponse.errorDescription
            ? `${authResponse.error}: ${authResponse.errorDescription}`
            : authResponse.error
        )
      : null);

  if (failure) {
    // The backend deliberately gives one flat message for a bad token and a
    // specific one for an unlinked account; showing whichever it sent is the
    // difference between a user knowing to call an administrator and them just
    // seeing "sign-in failed".
    const detail =
      failure.response?.data?.detail ||
      failure.message ||
      'Sign-in could not be completed.';

    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50 px-4">
        <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-lg">
          <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-600" role="alert">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2.2" className="shrink-0 mt-0.5">
              <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{detail}</span>
          </div>
          <Link
            to="/login"
            className="mt-4 flex h-[46px] w-full items-center justify-center rounded-[10px] bg-[#1b2f52] text-[14px] font-semibold text-white no-underline transition-colors hover:bg-[#24406e]"
          >
            Back to sign in
          </Link>
        </div>
      </div>
    );
  }

  // Nothing was started and nothing came back, so there is nothing to complete:
  // the URL was typed, or the page was reloaded after the authorization code was
  // already spent.
  //
  // Rendered in place rather than redirected to /login. A redirect here looked
  // identical to a crash while debugging — the page changed under you and anything
  // logged during the attempt was gone with a reload — so this states what
  // happened and leaves the choice to the user.
  if (!authResponse.hasCode && !authResponse.error) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50 px-4">
        <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-lg">
          <h2 className="text-[18px] font-bold text-[#14213d]">Nothing to complete</h2>
          <p className="mt-2 text-[13px] text-slate-600">
            This page finishes a Logto sign-in, and there is no sign-in in progress.
            That usually means it was reloaded after the sign-in already completed.
          </p>
          <Link
            to="/login"
            className="mt-4 flex h-[46px] w-full items-center justify-center rounded-[10px] bg-[#1b2f52] text-[14px] font-semibold text-white no-underline transition-colors hover:bg-[#24406e]"
          >
            Back to sign in
          </Link>
        </div>
      </div>
    );
  }

  // Covers both halves of the wait: the SDK redeeming the code, and our exchange
  // with the backend. `isLoading` only tracks the former, and the redirect to the
  // dashboard happens while this is still on screen.
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-slate-50">
      <Spinner size="lg" />
      <p className="text-[13px] text-slate-500">Completing sign-in…</p>
    </div>
  );
};

export default LogtoCallbackPage;
