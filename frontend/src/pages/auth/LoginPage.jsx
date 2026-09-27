import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLogto } from '@logto/react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import { isLogtoConfigured, redirectUri } from '../../auth/logtoConfig';
import {
  User, Lock, Eye, EyeOff, LogIn, Zap, ChevronRight,
  ShieldCheck, BarChart2, Users,
} from 'lucide-react';

/* ======================================================================
   BACKGROUND VIDEO

   Served straight from `public/`, so it is referenced by literal path rather
   than imported — Vite only fingerprints and rewrites files that are imported.
   Drop the file at `frontend/public/login-background.mp4`.

   Nothing here is load-bearing. If the file is absent the browser fires `error`
   and the still image underneath simply stays; if the format is unsupported the
   same happens, because `poster` and the background image are both already
   `/audit background.jpg`.
====================================================================== */
const VIDEO_BACKGROUND = '/login-background.mp4';

/* ======================================================================
   REDUCED MOTION

   A looping video behind a sign-in form is exactly the kind of thing the OS
   "reduce motion" setting exists to suppress — it is decorative, it never stops,
   and on a low-end machine it competes with the page the user is trying to read.
   Reported as state so the still image can take over instead.
====================================================================== */
function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  );

  useEffect(() => {
    const query = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!query) return undefined;
    const onChange = (event) => setReduced(event.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  return reduced;
}

/* ======================================================================
   Demo Roles
====================================================================== */
const DEMO_ROLES = [
  { label: 'System Admin', employeeId: 'EEU-10001', password: 'admin123', color: '#8b5cf6', desc: 'Full system access' },
  { label: 'Audit Manager', employeeId: 'EEU-10002', password: 'user123', color: '#24406e', desc: 'Plan & approve audits' },
  { label: 'Supervisor', employeeId: 'EEU-10003', password: 'user123', color: '#0891b2', desc: 'Review fieldwork' },
  { label: 'Lead Auditor', employeeId: 'EEU-10004', password: 'user123', color: '#059669', desc: 'Execute procedures' },
  { label: 'Auditee', employeeId: 'EEU-10005', password: 'user123', color: '#d97706', desc: 'Respond to CAPAs' },
];

/* ======================================================================
   DEMO BUTTON Component
====================================================================== */
function DemoButton({ role, loading, active, onClick}) {
  const { t } = useI18n();
  const [hov, setHov] = useState(false);
  return (
    <button
      id={`demo-${role.label.toLowerCase().replace(/\s+/g, '-')}`}
      type="button"
      onClick={onClick}
      disabled={loading}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      className="flex items-center gap-2.5 w-full text-left rounded-[9px] px-3 py-2 border transition-all duration-150 font-[inherit] cursor-pointer disabled:cursor-not-allowed"
      style={{
        background: hov ? '#f0f5ff' : '#f8fafc',
        borderTopColor: hov ? '#bfdbfe' : '#e5e7eb',
        borderRightColor: hov ? '#bfdbfe' : '#e5e7eb',
        borderBottomColor: hov ? '#bfdbfe' : '#e5e7eb',
        borderLeftColor: role.color,
        borderLeftWidth: 3.5,
        opacity: loading && !active ? 0.55 : 1,
        boxShadow: hov ? '0 2px 10px rgba(30,64,175,0.1)' : 'none',
        transform: hov ? 'translateX(2px)' : 'none',
      }}
    >
      <span className="w-2.5 h-2.5 rounded-full shrink-0"
        style={{ background: role.color, boxShadow: `0 0 6px ${role.color}88` }} />
      <span className="flex-1 flex flex-col gap-0">
        <strong className="text-[12px] font-bold text-slate-800 leading-tight">
          {active ? t('loginSigningIn') : role.label}
        </strong>
        <span className="text-[11px] text-slate-400 leading-tight">{role.desc}</span>
      </span>
      <ChevronRight size={13} className="text-slate-400" />
    </button>
  );
}

/* ======================================================================
   LOGTO SSO BUTTON

   Its own component rather than a useLogto() call inside LoginPage: that hook
   throws when there is no <LogtoProvider> above it, and LoginPage renders
   whether or not Logto is configured. Rendering this only under
   `isLogtoConfigured` means the hook is never called without a provider.
====================================================================== */

/**
 * How long to wait for Logto to start the redirect before giving up on it.
 *
 * `signIn()` fetches Logto's OIDC discovery document before it can send the browser
 * anywhere, and that fetch carries no timeout of its own. Against an unreachable
 * Logto it never settles — the button stays disabled on "Redirecting…" with nothing
 * said, and the only way out is a page reload. A working instance redirects in well
 * under a second, so this is generous.
 */
const SIGN_IN_TIMEOUT_MS = 15000;

function LogtoSignInButton({ onError }) {
  const { t } = useI18n();
  const { signIn } = useLogto();
  const [hov, setHov] = useState(false);
  const [busy, setBusy] = useState(false);

  const handleClick = async () => {
    setBusy(true);

    // Set by the timer below, and read in `catch` so a promise that rejects only
    // once we have already given up does not overwrite the message with a worse one.
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      setBusy(false);
      onError?.(t('loginLogtoTimeout'));
    }, SIGN_IN_TIMEOUT_MS);

    try {
      // The derived redirect URI, never a literal — the SDK keeps the PKCE
      // verifier in the initiating origin's storage, so a hardcoded origin
      // breaks the exchange whenever the app is opened from anywhere else.
      await signIn(redirectUri);
      // Reached only when signIn returned without navigating away, which the
      // successful path does not do — it leaves the page.
    } catch (err) {
      if (!timedOut) {
        onError?.(err.response?.data?.detail || err.message || t('loginLogtoUnreachable'));
      }
    } finally {
      clearTimeout(timer);
      setBusy(false);
    }
  };

  return (
    <button
      id="logto-signin-btn"
      type="button"
      onClick={handleClick}
      disabled={busy}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      className="w-full h-[50px] rounded-[10px] text-[14px] flex items-center justify-center gap-2.5 transition-all duration-150 font-[inherit] cursor-pointer disabled:cursor-not-allowed"
      style={{
        background: hov ? '#eef4ff' : '#ffffff',
        border: `1.5px solid ${hov ? '#24406e' : '#cbd5e1'}`,
        color: '#1b2f52',
        fontWeight: 600,
        boxShadow: hov ? '0 2px 10px rgba(30,64,175,0.12)' : 'none',
      }}
    >
      <ShieldCheck size={18} strokeWidth={2} />
      <span>{busy ? t('loginRedirecting') : t('loginSignInWithLogto')}</span>
    </button>
  );
}

/* ======================================================================
   MAIN COMPONENT
====================================================================== */
function LoginPage() {
  const auth = useAuth();
  const toast = useToast();
  const { t } = useI18n();
  const [employeeId, setEmployeeId] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeRole, setActiveRole] = useState(null);
  const [btnHov, setBtnHov] = useState(false);
  const [userFocus, setUserFocus] = useState(false);
  const [passFocus, setPassFocus] = useState(false);
  const reducedMotion = useReducedMotion();
  const [videoFailed, setVideoFailed] = useState(false);
  const showVideo = !reducedMotion && !videoFailed;
  const navigate = useNavigate();

  const doLogin = async (id, pwd) => {
    setError('');
    setLoading(true);
    try {
      await auth.login(id, pwd);
      toast.success(t('loginSignedInSuccess'));
      navigate('/dashboard');
    } catch (err) {
      const data = err.response?.data;
      let errMsg = t('loginInvalidCredentials');
      if (data?.detail) errMsg = data.detail;
      else if (data?.non_field_errors) errMsg = data.non_field_errors.join(' ');
      else if (data && typeof data === 'object') errMsg = Object.values(data).flat().join(' ');
      setError(errMsg);
      toast.error(errMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = (e) => { e.preventDefault(); doLogin(employeeId, password); };
  const handleDemo = (role) => { setActiveRole(role.label); setEmployeeId(role.employeeId); setPassword(role.password); doLogin(role.employeeId, role.password); };

  return (
    <div
      className="relative min-h-screen w-full flex items-center justify-center lg:justify-end py-4 px-4 lg:px-16 xl:px-24 overflow-hidden"
      style={{
        // The still image stays the base layer, doing three jobs at once: it paints
        // before the video has decoded a frame, it is what shows if the file is
        // missing or the browser refuses to play it, and it is what reduced-motion
        // users get instead. The colour ahead of it covers the moment before that
        // image loads.
        background: "#14213d url('/audit background.jpg') no-repeat center center / cover",
        fontFamily: "'Inter','Segoe UI','Helvetica Neue',sans-serif",
      }}
    >
      {showVideo && (
        // Decorative only, so it is hidden from assistive tech and cannot be
        // focused. `muted` is mandatory rather than a preference: every browser
        // blocks autoplay with sound, so an unmuted video simply never starts.
        // Absolute and un-z-indexed, which puts it above the background image and
        // below the `z-10` content and the overlay that follow it.
        <video
          className="absolute inset-0 w-full h-full object-cover pointer-events-none"
          src={VIDEO_BACKGROUND}
          poster="/audit background.jpg"
          autoPlay
          muted
          loop
          playsInline
          aria-hidden="true"
          tabIndex={-1}
          onError={() => setVideoFailed(true)}
        />
      )}

      {/* Semi-transparent overlay for readability — subtle enough not to obscure text */}
      <div className="absolute inset-0 bg-slate-900/30 pointer-events-none" />

      {/* ============================================================ CONTENT PANEL
          One column holding the logo, card, feature strip and footer, pushed to
          the right on wide screens so the background video is left visible rather
          than sitting behind the card.

          `max-w` keeps the column narrower than the strip's own `max-w-2xl` would
          allow, so the strip wraps to the card's width instead of jutting out past
          its left edge. Below `lg` the outer container is still centred, so narrow
          screens get the original stacked layout — a right-aligned column on a
          phone would just push the card off the edge. */}
      <div className="relative z-10 flex w-full max-w-[480px] flex-col items-center">
        {/* ============================================================ HEADER (logo + title) — sits above card */}
        <div className="flex flex-col items-center gap-2 mb-6 mt-2">
        <div className="w-[72px] h-[72px] rounded-full bg-[#1b2f52] p-[3px] flex items-center justify-center"
          style={{
            boxShadow: '0 0 0 3px #f2a93b,0 0 0 5px #1b2f52,0 0 0 7px rgba(20,33,61,0.6),0 0 0 10px rgba(0,166,81,0.22),0 8px 28px rgba(0,0,0,0.35)',
          }}>
          <img src="/eeu-logo.png" alt={t('brandLogoAlt')} className="w-full h-full rounded-full object-cover block" />
        </div>
        <div className="text-center">
          <div className="text-[18px] font-extrabold text-white tracking-[0.02em] leading-tight drop-shadow-lg">
            የኢትዮጵያ ኤሌክትሪክ አገልግሎት
          </div>
          <div className="text-[17px] font-extrabold text-white tracking-[0.01em] leading-tight drop-shadow-lg">
            Ethiopian Electric Utility
          </div>
        </div>
        <div className="text-[11px] font-bold tracking-[0.3em] text-amber-300 uppercase drop-shadow-md">
          {t('loginSystemTitle')}
        </div>
        <div className="w-12 h-[3px] rounded-full bg-gradient-to-r from-amber-400 to-emerald-500 drop-shadow-md" />
      </div>

      {/* ============================================================ LOGIN CARD
          Translucent so the background video reads through it. The white is
          not opaque enough on its own to hold the dark text against whatever
          frame is playing behind it, so the blur is doing the legibility work:
          it averages the video into a soft wash, which keeps the contrast
          roughly constant as the footage moves. Drop the blur and text over a
          bright frame becomes unreadable.

          The hairline border is what keeps the panel from dissolving into a
          light frame — at this opacity the shadow alone is not enough to find
          the card's edge. */}
      <div
        className="relative z-10 shrink-0 rounded-[20px] border border-white/50 bg-white/[0.68]"
        style={{
          width: 430,
          padding: '32px 40px 24px',
          // Spelled out rather than left to the `backdrop-blur-*` utility: the
          // `-webkit-` copy is still required by Safari below 18, and writing
          // both here keeps them from drifting apart.
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3),0 8px 24px rgba(0,0,0,0.2),0 2px 6px rgba(0,0,0,0.1)',
        }}
      >
        <h2 className="text-[24px] font-extrabold text-[#14213d] text-center mb-1 -tracking-[0.01em]">
          {t('loginWelcomeBack')}
        </h2>
        <p className="text-sm text-gray-500 text-center mb-5 font-normal">
          {t('loginSignInSubtitle')}
        </p>

        {/* Error banner */}
        {error && (
          <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-red-600 text-[13px] mb-3.5" role="alert">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2.2" className="shrink-0 mt-0.5">
              <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        {/* SSO — additive to the form below, not a replacement. Keeping the local
            login working means a Logto outage is not a lockout, and the seeded
            demo accounts (and the Playwright suite that drives them) still work. */}
        {isLogtoConfigured && (
          <>
            <LogtoSignInButton onError={setError} />
            <div className="flex items-center gap-3 my-4">
              <div className="flex-1 h-px bg-gray-200" />
              <span className="text-[11.5px] font-semibold text-gray-400 tracking-[0.06em]">
                {t('loginOrSignInWithUserId')}
              </span>
              <div className="flex-1 h-px bg-gray-200" />
            </div>
          </>
        )}

        <form onSubmit={handleLogin} className="mt-1">
          {/* Username */}
          <div className="mb-4">
            <label className="block text-[13px] font-semibold text-[#14213d] mb-1.5 text-left" htmlFor="login-employee-id">
              {t('user')}
            </label>
            <div className="relative flex items-center">
              <span className={`absolute left-3 flex items-center pointer-events-none transition-colors duration-200 ${userFocus ? 'text-[#24406e]' : 'text-gray-400'}`}>
                <User size={17} strokeWidth={1.9} />
              </span>
              <input
                id="login-employee-id"
                type="text"
                placeholder={t('loginUserIdPlaceholder')}
                value={employeeId}
                onChange={e => setEmployeeId(e.target.value)}
                autoComplete="username"
                required
                onFocus={() => setUserFocus(true)}
                onBlur={() => setUserFocus(false)}
                className="w-full h-[50px] rounded-[10px] bg-white/60 text-[14px] text-slate-800 outline-none transition-all duration-200 font-[inherit]"
                style={{
                  paddingLeft: '42px',
                  paddingRight: '16px',
                  border: `1.5px solid ${userFocus ? '#24406e' : '#e5e7eb'}`,
                  boxShadow: userFocus ? '0 0 0 3px rgba(36,64,110,0.12)' : 'none',
                }}
              />
            </div>
          </div>

          {/* Password */}
          <div className="mb-4">
            <label className="block text-[13px] font-semibold text-[#14213d] mb-1.5 text-left" htmlFor="login-password">
              {t('password')}
            </label>
            <div className="relative flex items-center">
              <span className={`absolute left-3 flex items-center pointer-events-none transition-colors duration-200 ${passFocus ? 'text-[#24406e]' : 'text-gray-400'}`}>
                <Lock size={17} strokeWidth={1.9} />
              </span>
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                placeholder={t('loginPasswordPlaceholder')}
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                onFocus={() => setPassFocus(true)}
                onBlur={() => setPassFocus(false)}
                className="w-full h-[50px] rounded-[10px] bg-white/60 text-[14px] text-slate-800 outline-none transition-all duration-200 font-[inherit]"
                style={{
                  paddingLeft: '42px',
                  paddingRight: '46px',
                  border: `1.5px solid ${passFocus ? '#24406e' : '#e5e7eb'}`,
                  boxShadow: passFocus ? '0 0 0 3px rgba(36,64,110,0.12)' : 'none',
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 flex items-center text-gray-400 hover:text-gray-600 transition-colors"
                aria-label={showPassword ? t('loginHidePassword') : t('loginShowPassword')}
              >
                {showPassword ? <EyeOff size={17} strokeWidth={1.9} /> : <Eye size={17} strokeWidth={1.9} />}
              </button>
            </div>
          </div>

          {/* LOG IN button */}
          <button
            id="login-submit-btn"
            type="submit"
            disabled={loading}
            onMouseEnter={() => setBtnHov(true)}
            onMouseLeave={() => setBtnHov(false)}
            className="w-full h-[52px] rounded-[11px] border-none text-white text-[15px] flex items-center justify-center gap-2.5 transition-all duration-150 font-[inherit] cursor-pointer disabled:cursor-not-allowed"
            style={{
              background: btnHov
                ? 'linear-gradient(180deg,#f59032 0%,#e06f10 100%)'
                : 'linear-gradient(180deg,#f5921a 0%,#f2801f 40%,#e06f10 100%)',
              boxShadow: btnHov
                ? '0 8px 28px rgba(242,128,31,0.55),0 2px 8px rgba(224,111,16,0.4)'
                : '0 5px 20px rgba(242,128,31,0.45),0 2px 6px rgba(224,111,16,0.3)',
              transform: btnHov ? 'translateY(-1px)' : 'translateY(0)',
              opacity: loading ? 0.82 : 1,
            }}
          >
            <LogIn size={18} strokeWidth={2.2} />
            <span className="tracking-[0.12em] font-bold">
              {loading ? t('loginSigningInUppercase') : t('loginLogIn')}
            </span>
          </button>
        </form>

        {/* Trust strip */}
        <div className="flex items-center justify-center gap-2 mt-4 text-[12px] text-gray-400">
          <div className="flex-1 h-px bg-gray-200" />
          <span>{t('loginSecure')}</span>
          <span className="text-[#1b2f52] font-bold">•</span>
          <span className="flex items-center gap-1">
            <ShieldCheck size={15} className="text-[#1b2f52]" strokeWidth={1.8} />
            {t('loginReliable')}
          </span>
          <span className="text-[#1b2f52] font-bold">•</span>
          <span>{t('loginTransparent')}</span>
          <div className="flex-1 h-px bg-gray-200" />
        </div>

        {/* Demo quick access — dev/test only. Gated on `import.meta.env.DEV` so
            the plaintext demo credentials in DEMO_ROLES are tree-shaken out of a
            production build, while the Playwright suite (which runs the dev
            server) still has the #demo-* buttons to click.

            No `hidden` attribute here: the gate above is what excludes this from
            production, and carrying both made the panel render-but-invisible in
            dev, so the demo buttons could never actually be clicked. */}
        {import.meta.env.DEV && (
          <div className="mt-4 pt-3.5 border-t border-slate-100"hidden>
            <div className="flex items-center gap-1.5 mb-2.5">
              <Zap size={13} className="text-amber-400 fill-amber-400" />
              <span className="text-[11.5px] font-bold text-gray-500 tracking-[0.02em]">
                {t('loginQuickDemoAccess')}
              </span>
            </div>
            <div className="flex flex-col gap-1.5">
              {DEMO_ROLES.map(role => (
                <DemoButton
                  key={role.label}
                  role={role}
                  loading={loading}
                  active={activeRole === role.label && loading}
                  onClick={() => handleDemo(role)}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ============================================================ FEATURE STRIP — sits below card */}
      <div className="relative z-10 flex gap-4 justify-center flex-wrap mt-6 px-4 max-w-2xl">
        {[
          { Icon: ShieldCheck, label: t('loginSecureAccess'), iconClass: 'text-amber-300' },
          { Icon: BarChart2, label: t('loginRealTimeInsights'), iconClass: 'text-emerald-400' },
          { Icon: Users, label: t('loginAccountability'), iconClass: 'text-emerald-400' },
        ].map(({ Icon, label, iconClass }) => (
          <div
            key={label}
            className="flex items-center gap-2 text-white/90 drop-shadow-md"
          >
            <Icon size={18} strokeWidth={2} className={iconClass} />
            <span className="text-[13px] font-semibold">{label}</span>
          </div>
        ))}
      </div>

        {/* ============================================================ FOOTER */}
        <div className="flex flex-col items-center gap-1 mt-6 px-4 text-center">
          <div className="text-[12px] text-white/75 drop-shadow-md">
            {t('loginCopyright')}
          </div>
          <div className="text-[11.5px] font-semibold text-amber-300/90 drop-shadow-md">
            {t('loginDesignedBy')}
          </div>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;