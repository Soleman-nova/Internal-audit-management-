import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import {
  User, Lock, Eye, EyeOff, LogIn, Zap, ChevronRight,
  ShieldCheck, Shield, BarChart2, Users,
} from 'lucide-react';

/* ─── Demo Roles ─────────────────────────────────────────────────────── */
const DEMO_ROLES = [
  { label: 'System Admin', employeeId: 'EEU-10001', password: 'admin123', color: '#8b5cf6', desc: 'Full system access' },
  { label: 'Audit Manager', employeeId: 'EEU-10002', password: 'S@12345678', color: '#24406e', desc: 'Plan & approve audits' },
  { label: 'Supervisor', employeeId: 'EEU-10003', password: 'user123', color: '#0891b2', desc: 'Review fieldwork' },
  { label: 'Lead Auditor', employeeId: 'EEU-10004', password: 'user123', color: '#059669', desc: 'Execute procedures' },
  { label: 'Auditee', employeeId: 'EEU-10005', password: 'user123', color: '#d97706', desc: 'Respond to CAPAs' },
];

/* ======================================================================
   DEMO BUTTON Component
====================================================================== */
function DemoButton({ role, loading, active, onClick }) {
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
          {active ? '⟳ Signing in…' : role.label}
        </strong>
        <span className="text-[11px] text-slate-400 leading-tight">{role.desc}</span>
      </span>
      <ChevronRight size={13} className="text-slate-400" />
    </button>
  );
}

/* ======================================================================
   MAIN COMPONENT
====================================================================== */
function LoginPage() {
  const auth = useAuth();
  const toast = useToast();
  const [employeeId, setEmployeeId] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeRole, setActiveRole] = useState(null);
  const [btnHov, setBtnHov] = useState(false);
  const [userFocus, setUserFocus] = useState(false);
  const [passFocus, setPassFocus] = useState(false);
  const navigate = useNavigate();

  const doLogin = async (id, pwd) => {
    setError('');
    setLoading(true);
    try {
      await auth.login(id, pwd);
      toast.success('Signed in successfully');
      navigate('/dashboard');
    } catch (err) {
      const data = err.response?.data;
      let errMsg = 'Invalid Employee ID or password. Please try again.';
      if (data?.detail) errMsg = data.detail;
      else if (data?.non_field_errors) errMsg = data.non_field_errors.join(' ');
      else if (typeof data === 'object') errMsg = Object.values(data).flat().join(' ');
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
      className="relative min-h-screen w-full flex flex-col items-center justify-center py-4 px-4"
      style={{
        background: "#14213d url('/audit background.jpg') no-repeat center center / cover",
        fontFamily: "'Inter','Segoe UI','Helvetica Neue',sans-serif",
      }}
    >
      {/* Semi-transparent overlay for readability — subtle enough not to obscure text */}
      <div className="absolute inset-0 bg-slate-900/30 pointer-events-none" />

      {/* ============================================================ HEADER (logo + title) — sits above card */}
      <div className="relative z-10 flex flex-col items-center gap-2 mb-6 mt-2">
        <div className="w-[72px] h-[72px] rounded-full bg-[#1b2f52] p-[3px] flex items-center justify-center"
          style={{
            boxShadow: '0 0 0 3px #f2a93b,0 0 0 5px #1b2f52,0 0 0 7px rgba(20,33,61,0.6),0 6px 24px rgba(0,0,0,0.35)',
          }}>
          <img src="/eeu-logo.png" alt="EEU Logo" className="w-full h-full rounded-full object-cover block" />
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
          Internal Audit Management System
        </div>
      </div>

      {/* ============================================================ LOGIN CARD */}
      <div
        className="relative z-10 shrink-0 rounded-[20px] bg-white/[0.96]"
        style={{
          width: 430,
          padding: '32px 40px 24px',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3),0 8px 24px rgba(0,0,0,0.2),0 2px 6px rgba(0,0,0,0.1)',
        }}
      >
        <h2 className="text-[24px] font-extrabold text-[#14213d] text-center mb-1 -tracking-[0.01em]">
          Welcome Back!
        </h2>
        <p className="text-sm text-gray-500 text-center mb-5 font-normal">
          Please sign in to your account
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

        <form onSubmit={handleLogin} className="mt-1">
          {/* Username */}
          <div className="mb-4">
            <label className="block text-[13px] font-semibold text-[#14213d] mb-1.5 text-left" htmlFor="login-employee-id">
              User
            </label>
            <div className="relative flex items-center">
              <span className={`absolute left-3 flex items-center pointer-events-none transition-colors duration-200 ${userFocus ? 'text-[#24406e]' : 'text-gray-400'}`}>
                <User size={17} strokeWidth={1.9} />
              </span>
              <input
                id="login-employee-id"
                type="text"
                placeholder="Please enter your User ID"
                value={employeeId}
                onChange={e => setEmployeeId(e.target.value)}
                autoComplete="username"
                required
                onFocus={() => setUserFocus(true)}
                onBlur={() => setUserFocus(false)}
                className="w-full h-[50px] rounded-[10px] bg-gray-50 text-[14px] text-slate-800 outline-none transition-all duration-200 font-[inherit]"
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
              Password
            </label>
            <div className="relative flex items-center">
              <span className={`absolute left-3 flex items-center pointer-events-none transition-colors duration-200 ${passFocus ? 'text-[#24406e]' : 'text-gray-400'}`}>
                <Lock size={17} strokeWidth={1.9} />
              </span>
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                placeholder="Please enter your password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                onFocus={() => setPassFocus(true)}
                onBlur={() => setPassFocus(false)}
                className="w-full h-[50px] rounded-[10px] bg-gray-50 text-[14px] text-slate-800 outline-none transition-all duration-200 font-[inherit]"
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
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff size={17} strokeWidth={1.9} /> : <Eye size={17} strokeWidth={1.9} />}
              </button>
            </div>
          </div>

          {/* Remember + Forgot */}
          <div className="flex justify-between items-center mt-3 mb-4">
            <label className="flex items-center gap-1.5 text-[13px] text-slate-600 cursor-pointer select-none" htmlFor="remember-me">
              <input
                id="remember-me"
                type="checkbox"
                checked={rememberMe}
                onChange={e => setRememberMe(e.target.checked)}
                className="w-[15px] h-[15px] cursor-pointer accent-[#1b2f52]"
              />
              Remember me
            </label>
            <a href="#forgot" className="text-[13px] text-blue-600 font-semibold no-underline hover:underline">
              Forgot Password?
            </a>
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
              {loading ? 'SIGNING IN…' : 'LOG IN'}
            </span>
          </button>
        </form>

        {/* Trust strip */}
        <div className="flex items-center justify-center gap-2 mt-4 text-[12px] text-gray-400">
          <div className="flex-1 h-px bg-gray-200" />
          <span>Secure</span>
          <span className="text-[#1b2f52] font-bold">•</span>
          <span className="flex items-center gap-1">
            <ShieldCheck size={15} className="text-[#1b2f52]" strokeWidth={1.8} />
            Reliable
          </span>
          <span className="text-[#1b2f52] font-bold">•</span>
          <span>Transparent</span>
          <div className="flex-1 h-px bg-gray-200" />
        </div>

        {/* Demo quick access */}
        <div className="mt-4 pt-3.5 border-t border-slate-100">
          <div className="flex items-center gap-1.5 mb-2.5">
            <Zap size={13} className="text-amber-400 fill-amber-400" />
            <span className="text-[11.5px] font-bold text-gray-500 tracking-[0.02em]">
              Quick Demo Access — one click login
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
      </div>

      {/* ============================================================ FEATURE STRIP — sits below card */}
      <div className="relative z-10 flex gap-4 justify-center flex-wrap mt-6 px-4 max-w-2xl">
        {[
          { Icon: ShieldCheck, label: 'Secure Access', iconClass: 'text-amber-300' },
          { Icon: BarChart2, label: 'Real-time Insights', iconClass: 'text-amber-300' },
          { Icon: Users, label: 'Accountability', iconClass: 'text-amber-300' },
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
    </div>
  );
}

export default LoginPage;