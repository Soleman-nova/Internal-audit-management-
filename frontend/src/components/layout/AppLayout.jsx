import { useState, useEffect, useCallback, useRef } from 'react';

import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { authApi, notificationApi, resolveApiBaseUrl, setApiBaseUrl } from '../../api/apiClient';
import { hasCapability, CAPABILITIES } from '../../hooks/usePermissions';
import useAsyncData from '../../hooks/useAsyncData';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import Modal from '../ui/Modal';
import {
  LayoutDashboard,
  Calendar,
  ListTodo,
  AlertTriangle,
  TrendingUp,
  CheckCircle,
  BarChart3,
  Users,
  LogOut,
  Bell,
  User as UserIcon,
  Menu,
  X,
  Activity,
  Settings,
  HelpCircle,
  Globe,
  Moon,
  Sun,
  Server,
  Lock,
  Eye,
  EyeOff,
  Save,
  Loader2,
  UsersRound,
  GitBranch,
  ListChecks,
  Mail,
  CircleCheck,
  AlertCircle,
  SlidersHorizontal
} from 'lucide-react';

function AppLayout() {
  const auth = useAuth();
  const { setLanguage, setTheme } = auth;
  const toast = useToast();
  const user = auth.user || { email: '', role: 'auditor', first_name: 'Auditor' };
  // Below 900px the sidebar is a drawer over the content, so it must start
  // closed — defaulting to open put a 260px panel across a phone on first paint.
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth > 900);
  const [showNotifications, setShowNotifications] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const notifContainerRef = useRef(null);
  const [apiServer, setApiServer] = useState(resolveApiBaseUrl);
  const themeMode = auth.theme || 'light';
  const language = auth.language === 'am' ? 'AM' : 'EN';
  const [saveSuccess, setSaveSuccess] = useState(false);

  // One dictionary for the whole app. The layout used to carry its own inline
  // TRANSLATIONS object duplicating ~30 keys, so a term fixed in I18nContext
  // stayed wrong in the sidebar and settings modal.
  const { t } = useI18n();
  const [settingsTab, setSettingsTab] = useState('general');
  const [helpTab, setHelpTab] = useState('overview');
  const [helpRole, setHelpRole] = useState('admin');

  // Password change state
  const [pwCurrent, setPwCurrent] = useState('');
  const [pwNew, setPwNew] = useState('');
  const [pwConfirm, setPwConfirm] = useState('');
  const [pwError, setPwError] = useState('');
  const [pwSuccess, setPwSuccess] = useState(false);
  const [pwLoading, setPwLoading] = useState(false);
  const [showPwCurrent, setShowPwCurrent] = useState(false);
  const [showPwNew, setShowPwNew] = useState(false);
  const [showPwConfirm, setShowPwConfirm] = useState(false);

  // Profile edit state. The two name fields are a *draft over* the account rather
  // than a copy of it: `null` means "untouched — show whatever the account says".
  // That is what lets the fields fill themselves in when `auth.user` arrives
  // without an effect writing props into state, and — because the fallback `user`
  // object above is rebuilt on every render when there is no account yet — without
  // an effect that would re-run on every single render.
  const [profileFirstNameDraft, setProfileFirstNameDraft] = useState(null);
  const [profileLastNameDraft, setProfileLastNameDraft] = useState(null);
  const profileFirstName = profileFirstNameDraft ?? (user.first_name || '');
  const profileLastName = profileLastNameDraft ?? (user.last_name || '');
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSuccess, setProfileSuccess] = useState(false);
  const [profileError, setProfileError] = useState('');

  const [checkedTasks, setCheckedTasks] = useState(() => {
    try {
      const saved = localStorage.getItem('checkedWorkflowTasks');
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  });

  const toggleTask = (taskId) => {
    setCheckedTasks(prev => {
      const updated = { ...prev, [taskId]: !prev[taskId] };
      localStorage.setItem('checkedWorkflowTasks', JSON.stringify(updated));
      return updated;
    });
  };

  // Apply theme to <body> immediately whenever themeMode changes
  useEffect(() => {
    document.body.setAttribute('data-theme', themeMode);
  }, [themeMode]);

  // Apply lang to <html> immediately whenever language changes
  useEffect(() => {
    document.documentElement.setAttribute('lang', language === 'AM' ? 'am' : 'en');
  }, [language]);

  // Close notifications popover on outside click
  useEffect(() => {
    if (!showNotifications) return;
    const handleOutside = (e) => {
      if (notifContainerRef.current && !notifContainerRef.current.contains(e.target)) {
        setShowNotifications(false);
      }
    };
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, [showNotifications]);

  // Close the notifications popover on Escape. Settings and Help are <Modal>s
  // now and handle their own Escape, focus trap and scroll lock — the popover is
  // not a modal, so it still needs this.
  useEffect(() => {
    if (!showNotifications) return undefined;
    const handleEscape = (e) => {
      if (e.key === 'Escape') setShowNotifications(false);
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [showNotifications]);

  const handleSaveSettings = (e) => {
    e.preventDefault();
    // Retargets the live axios instance as well as persisting the choice, so
    // the next request goes to the new host — previously the toast said
    // "saved" while every call kept hitting the old endpoint until a reload.
    const applied = setApiBaseUrl(apiServer);
    setApiServer(applied);
    toast.success(t('layoutSettingsSavedToast'));
    setShowSettings(false);
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setPwError('');
    if (pwNew !== pwConfirm) {
      setPwError(t('layoutPasswordsDoNotMatch'));
      toast.error(t('layoutPasswordsDoNotMatch'));
      return;
    }
    if (pwNew.length < 8) {
      setPwError(t('layoutPasswordMinLength'));
      toast.error(t('layoutPasswordMinLength'));
      return;
    }
    setPwLoading(true);
    try {
      await authApi.changePassword(pwCurrent, pwNew);
      setPwSuccess(true);
      toast.success(t('layoutPasswordChangedToast'));
      setPwCurrent('');
      setPwNew('');
      setPwConfirm('');
      setTimeout(() => setPwSuccess(false), 3000);
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.current_password?.[0] ||
        err?.response?.data?.new_password?.[0] ||
        t('layoutPasswordChangeFailed');
      setPwError(msg);
      toast.error(msg);
    } finally {
      setPwLoading(false);
    }
  };

  const handleSaveProfile = async (e) => {
    e.preventDefault();
    setProfileError('');
    setProfileSaving(true);
    try {
      await auth.updateUser({ first_name: profileFirstName, last_name: profileLastName });
      // Drop the drafts so the fields fall back to what the account now says.
      // This is the saved record's own sync, rather than the old effect's blanket
      // "any change to `user` overwrites whatever is in the inputs".
      setProfileFirstNameDraft(null);
      setProfileLastNameDraft(null);
      setProfileSuccess(true);
      toast.success(t('layoutProfileUpdatedToast'));
      setTimeout(() => setProfileSuccess(false), 3000);
    } catch (err) {
      const msg = err?.response?.data?.detail || t('layoutProfileUpdateFailed');
      setProfileError(msg);
      toast.error(msg);
    } finally {
      setProfileSaving(false);
    }
  };

  const location = useLocation();
  const navigate = useNavigate();

  

  // On a narrow viewport the drawer sits on top of the page, so tapping a nav
  // link would otherwise leave it covering the page it just opened. Checked at
  // navigation time rather than through a resize listener — and against the
  // previous path *during render* rather than from an effect, so the drawer is
  // already shut in the frame that paints the new page instead of one frame
  // later. Same documented "adjust state when a prop changes" pattern as
  // DataTable's prop mirrors.
  const [prevPathname, setPrevPathname] = useState(location.pathname);
  if (prevPathname !== location.pathname) {
    setPrevPathname(location.pathname);
    if (window.innerWidth <= 900) setSidebarOpen(false);
  }

  // Load notifications + unread count from the backend. Both come out of the one
  // pair of requests, so the loader returns them together and they are derived
  // from it below — a superseded poll response can no longer land after a newer
  // one and leave the badge counting something other than the list on screen.
  const { data: notificationsData, reload: loadNotifications } = useAsyncData(
    async () => {
      const [items, unread] = await Promise.all([
        notificationApi.list(),
        notificationApi.unreadCount(),
      ]);
      return { items: Array.isArray(items) ? items : [], unread };
    },
    [],
    // Non-fatal: a failed poll leaves the last good list and count in place.
    { onError: (err) => console.error('Failed to load notifications', err) },
  );

  const notifications = notificationsData?.items ?? [];
  const unreadCount = notificationsData?.unread ?? 0;

  // Poll periodically so new events surface without a reload. The initial fetch
  // belongs to the hook above; this effect owns only the timer, and the cleanup
  // still cancels it on unmount.
  useEffect(() => {
    const interval = setInterval(() => { loadNotifications(); }, 30000);
    return () => clearInterval(interval);
  }, [loadNotifications]);

  const handleMarkAllRead = useCallback(async () => {
    try {
      await notificationApi.markAllRead();
      toast.info(t('layoutNotificationsMarkedRead'));
    } catch (err) {
      console.error('Failed to mark all notifications read', err);
    }
    loadNotifications();
  }, [loadNotifications, toast, t]);

  const handleNotificationClick = useCallback(async (n) => {
    if (!n.is_read) {
      try {
        await notificationApi.markRead(n.id);
      } catch (err) {
        console.error('Failed to mark notification read', err);
      }
    }
    if (n.link) {
      setShowNotifications(false);
      navigate(n.link);
    }
    loadNotifications();
  }, [loadNotifications, navigate]);

  // One call, because `auth.logout()` already ends the Logto session when there is
  // one: it clears the local session and then hands off to
  // `signOut(postSignOutRedirectUri)` — see AuthContext.jsx. Calling `signOut` here
  // as well would run it twice, and for a *local* login it would drag someone
  // through Logto's redirect on the way out of a service they never signed into.
  //
  // It lives in AuthContext rather than here because `useLogto()` throws when no
  // <LogtoProvider> is mounted, and this layout renders in both configurations.
  // The provider is conditional; this component is not.
  const handleLogout = () => {
    auth.logout();
  };

  const navItems = [
    { path: '/dashboard', label: t('dashboard'), icon: <LayoutDashboard size={20} /> },
    { path: '/planning', label: t('auditPlanning'), icon: <Calendar size={20} /> },
    { path: '/execution', label: t('auditExecution'), icon: <ListTodo size={20} /> },
    { path: '/findings', label: t('findingsRegistry'), icon: <AlertTriangle size={20} /> },
    { path: '/risk', label: t('riskAssessment'), icon: <TrendingUp size={20} /> },
    { path: '/capa', label: t('correctiveActions'), icon: <CheckCircle size={20} /> },
    { path: '/reports', label: t('reportsAnalytics'), icon: <BarChart3 size={20} /> },
  ];

  // Nav visibility follows the capability matrix (see hooks/usePermissions.js).
  // User Management requires manage_users (admin); Audit Trail requires
  // view_audit_trail (admin, audit_manager, supervisor).
  if (hasCapability(user, CAPABILITIES.MANAGE_USERS)) {
    navItems.push({ path: '/users', label: t('userManagement'), icon: <Users size={20} /> });
  }
  if (hasCapability(user, CAPABILITIES.VIEW_AUDIT_TRAIL)) {
    navItems.push({ path: '/audit-trail', label: t('auditTrail'), icon: <Activity size={20} /> });
  }

  const activeNavItem = navItems.find(item => location.pathname === item.path) || { label: t('layoutAppNameFallback') };

  const closeSettingsModal = () => {
    setShowSettings(false);
    setSaveSuccess(false);
    setPwError('');
    setPwSuccess(false);
    setProfileError('');
    setProfileSuccess(false);
  };

  const settingsTabs = [
    { id: 'general', icon: SlidersHorizontal, label: t('general'), desc: t('layoutSettingsGeneralDesc') },
    { id: 'password', icon: Lock, label: t('changePassword'), desc: t('layoutSettingsPasswordDesc') },
    { id: 'profile', icon: UserIcon, label: t('profile'), desc: t('layoutSettingsProfileDesc') },
  ];

  const helpTabs = [
    { id: 'overview', icon: UsersRound, label: t('layoutHelpTabRoles') },
    { id: 'stages', icon: GitBranch, label: t('layoutHelpTabStages') },
    { id: 'checklist', icon: ListChecks, label: t('layoutHelpTabChecklist') },
  ];

  const pwStrength = pwNew.length >= 12 ? 'strong' : pwNew.length >= 10 ? 'good' : pwNew.length >= 8 ? 'fair' : pwNew.length > 0 ? 'weak' : '';
  const pwStrengthLevel = pwNew.length >= 12 ? 4 : pwNew.length >= 10 ? 3 : pwNew.length >= 8 ? 2 : pwNew.length > 0 ? 1 : 0;

  return (
    <div className="app-container">
      {/* The sidebar puts 7–11 links ahead of the content on every page, so a
          keyboard user needs a way past them. Off-screen until focused. */}
      <a href="#main-content" className="skip-link">{t('skipToContent')}</a>

      {/* Sidebar */}
      <aside className={`app-sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-header">
          <Link to="/dashboard" className="sidebar-brand" style={{ textDecoration: 'none' }}>
            <img src="/eeu-logo.png" alt={t('brandLogoAlt')} className="brand-logo" />
            <span>{t('layoutBrandName')}</span>
          </Link>
          <button className="sidebar-close-btn" onClick={() => setSidebarOpen(false)}>
            <X size={20} />
          </button>
        </div>

        <div className="sidebar-user">
          <div className="user-avatar-placeholder">
            {user.first_name ? user.first_name[0] : 'U'}
          </div>
          <div className="user-info">
            <h4 className="user-name">{user.first_name} {user.last_name}</h4>
            <span className="user-role">{user.role?.replace('_', ' ').toUpperCase()}</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`nav-item ${location.pathname === item.path ? 'active' : ''}`}
            >
              <span className="nav-item-icon">{item.icon}</span>
              <span className="nav-item-label">{item.label}</span>
            </Link>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button className="nav-item logout-btn" onClick={handleLogout}>
            <span className="nav-item-icon"><LogOut size={20} /></span>
            <span className="nav-item-label">{t('signOut')}</span>
          </button>
        </div>
      </aside>

      {/* Drawer backdrop — CSS hides it above 900px, where the sidebar is a
          permanent rail rather than an overlay. */}
      {sidebarOpen && (
        <button
          type="button"
          className="sidebar-backdrop"
          onClick={() => setSidebarOpen(false)}
          aria-label={t('closeNavigation')}
        />
      )}

      {/* Main Content Area */}
      <div className={`main-wrapper ${sidebarOpen ? 'sidebar-open' : 'sidebar-closed'}`}>
        {/* Top Header */}
        <header className="app-header">
          <div className="header-left">
            <button
              className="sidebar-toggle-btn"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              aria-label={t('toggleSidebar')}
              aria-expanded={sidebarOpen}
            >
              <Menu size={22} />
            </button>
            <h2 className="header-title">{activeNavItem.label}</h2>
          </div>

          <div className="header-right">
            {/* Notifications Dropdown */}
            <div className="notification-container" ref={notifContainerRef}>
              <button
                className="header-action-btn relative"
                onClick={() => setShowNotifications(!showNotifications)}
                aria-haspopup="true"
                aria-expanded={showNotifications}
                aria-label={t('notifications')}
              >
                <Bell size={20} />
                {unreadCount > 0 && (
                  <span className="notification-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>
                )}
              </button>

              {showNotifications && (
                <div
                  className="notifications-dropdown"
                  role="dialog"
                  aria-label={t('notifications')}
                >
                  <div className="dropdown-header">
                    <h3>{t('notifications')}</h3>
                    <button className="text-btn" onClick={handleMarkAllRead}>
                      {t('markAllRead')}
                    </button>
                  </div>
                  <div className="dropdown-body">
                    {notifications.length === 0 ? (
                      <p className="no-notifications">{t('noNotifications')}</p>
                    ) : (
                      notifications.map(n => (
                        <div
                          key={n.id}
                          className={`notification-item ${n.is_read ? 'read' : 'unread'}`}
                          onClick={() => handleNotificationClick(n)}
                          style={{ cursor: n.link ? 'pointer' : 'default' }}
                        >
                          <h4>{n.title}</h4>
                          <p>{n.message}</p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Help Button.
                `data-testid` because these two are opened by the E2E language test
                *while the interface is in Amharic* — `title` and `aria-label` are
                both translated now, so neither can identify the button. A test
                locator must not be user-facing text. */}
            <button
              className="header-action-btn"
              data-testid="header-help-btn"
              onClick={() => setShowHelp(true)}
              title={t('help')}
              aria-label={t('layoutHelpAria')}
            >
              <HelpCircle size={20} />
            </button>

            {/* Settings Button */}
            <button
              className="header-action-btn"
              data-testid="header-settings-btn"
              onClick={() => setShowSettings(true)}
              title={t('systemSettings')}
              aria-label={t('systemSettings')}
            >
              <Settings size={20} />
            </button>

            {/* Profile Menu Info */}
            <div className="header-profile">
              <div className="header-profile-avatar">
                <UserIcon size={18} />
              </div>
              <span className="header-profile-name" title={user.email}>
                {user.first_name || user.last_name
                  ? `${user.first_name || ''} ${user.last_name || ''}`.trim()
                  : user.email}
              </span>
            </div>
          </div>
        </header>

        {/* Dynamic Route Content */}
        <main className="content-container" id="main-content">
          <Outlet />
        </main>
      </div>

      {/* Settings Modal */}
      <Modal
        isOpen={showSettings}
        onClose={closeSettingsModal}
        title={(
          <span className="flex items-center gap-2">
            <Settings size={18} /> {t('systemSettings')}
          </span>
        )}
        subtitle={t('layoutSettingsSubtitle')}
        size="lg"
      >
        {/* Modal pads its body with p-6, but this layout is a full-bleed nav
            rail beside a content pane and supplies its own padding — cancel the
            gutter so the rail still meets the dialog edge. */}
        <div className="-m-6">
          <div className="app-modal-layout">
              <nav className="app-modal-nav" aria-label={t('layoutSettingsSectionsAria')}>
                {settingsTabs.map((tab) => {
                  const TabIcon = tab.icon;
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => {
                        setSettingsTab(tab.id);
                        setPwError('');
                        setPwSuccess(false);
                        setProfileError('');
                        setProfileSuccess(false);
                      }}
                      className={`app-modal-nav-btn ${settingsTab === tab.id ? 'active' : ''}`}
                    >
                      <span className="app-modal-nav-icon"><TabIcon size={16} /></span>
                      <span>{tab.label}</span>
                    </button>
                  );
                })}
              </nav>

              <div className="app-modal-content">
                {settingsTab === 'general' && (
                  <form onSubmit={handleSaveSettings}>
                    <p className="app-modal-section-title">{t('layoutPreferences')}</p>

                    {saveSuccess && (
                      <div className="app-modal-alert success">
                        <CircleCheck size={18} style={{ flexShrink: 0, marginTop: 1 }} />
                        <span>{t('settingsSaved')}</span>
                      </div>
                    )}

                    <div className="app-modal-field">
                      <label><Server size={14} /> {t('apiEndpoint')}</label>
                      <input
                        type="text"
                        value={apiServer}
                        onChange={(e) => setApiServer(e.target.value)}
                        placeholder="http://localhost:8000/api"
                        className="font-mono"
                        required
                      />
                      <p className="app-modal-field-hint">{t('layoutApiEndpointHint')}</p>
                    </div>

                    <div className="app-modal-field">
                      <label><Globe size={14} /> {t('systemLanguage')}</label>
                      <div className="app-modal-lang-grid">
                        {[
                          { val: 'EN', flag: '🇬🇧', name: t('layoutLanguageEnglish'), sub: t('layoutLanguageDefault') },
                          { val: 'AM', flag: '🇪🇹', name: t('layoutLanguageAmharic'), sub: 'አማርኛ' },
                        ].map((lang) => (
                          <label
                            key={lang.val}
                            className={`app-modal-lang-card ${language === lang.val ? 'selected' : ''}`}
                          >
                            <input
                              type="radio"
                              name="language"
                              value={lang.val}
                              checked={language === lang.val}
                              onChange={() => setLanguage(lang.val === 'AM' ? 'am' : 'en')}
                              className="sr-only"
                            />
                            <span className="app-modal-lang-flag">{lang.flag}</span>
                            <div className="app-modal-lang-text">
                              <strong>{lang.name}</strong>
                              <span>{lang.sub}</span>
                            </div>
                          </label>
                        ))}
                      </div>
                    </div>

                    <div className="app-modal-field">
                      <label><Sun size={14} /> {t('themePreference')}</label>
                      <div className="app-modal-theme-grid">
                        {[
                          { val: 'dark', label: t('darkMode'), sub: t('darkModeSub'), preview: 'dark-preview', icon: Moon },
                          { val: 'light', label: t('lightMode'), sub: t('lightModeSub'), preview: 'light-preview', icon: Sun },
                        ].map((th) => {
                          const ThemeIcon = th.icon;
                          return (
                            <label
                              key={th.val}
                              className={`app-modal-theme-card ${themeMode === th.val ? 'selected' : ''}`}
                            >
                              <input
                                type="radio"
                                name="themeMode"
                                value={th.val}
                                checked={themeMode === th.val}
                                onChange={() => setTheme(th.val)}
                                className="sr-only"
                              />
                              <div className={`app-modal-theme-preview ${th.preview}`}>
                                <div className="preview-bar" />
                                <div className="preview-body">
                                  <div className="preview-sidebar" />
                                  <div className="preview-main" />
                                </div>
                              </div>
                              <div className="app-modal-theme-label">
                                <ThemeIcon size={14} />
                                {th.label.replace(/^[^\s]+\s/, '')}
                              </div>
                              <span className="app-modal-theme-sub">{th.sub}</span>
                            </label>
                          );
                        })}
                      </div>
                    </div>

                    <div className="app-modal-actions">
                      <button type="button" className="app-modal-btn app-modal-btn-secondary" onClick={closeSettingsModal}>
                        {t('cancel')}
                      </button>
                      <button type="submit" className="app-modal-btn app-modal-btn-primary">
                        <Save size={16} />
                        {t('saveChanges')}
                      </button>
                    </div>
                  </form>
                )}

                {settingsTab === 'password' && (
                  <form onSubmit={handleChangePassword}>
                    <p className="app-modal-section-title">{t('layoutSecurity')}</p>

                    <div className="app-modal-alert info">
                      <Lock size={16} style={{ flexShrink: 0, marginTop: 1 }} />
                      <span>
                        {t('layoutPasswordPolicyBefore')} <strong>{t('layoutPasswordPolicyBold')}</strong> {t('layoutPasswordPolicyAfter')}
                      </span>
                    </div>

                    {pwError && (
                      <div className="app-modal-alert error">
                        <AlertCircle size={18} style={{ flexShrink: 0, marginTop: 1 }} />
                        <span>{pwError}</span>
                      </div>
                    )}
                    {pwSuccess && (
                      <div className="app-modal-alert success">
                        <CircleCheck size={18} style={{ flexShrink: 0, marginTop: 1 }} />
                        <span>{t('layoutPasswordChangedSuccess')}</span>
                      </div>
                    )}

                    {[
                      { id: 'pwCurrent', label: t('layoutCurrentPassword'), val: pwCurrent, setter: setPwCurrent, show: showPwCurrent, toggle: setShowPwCurrent, placeholder: t('layoutCurrentPasswordPlaceholder') },
                      { id: 'pwNew', label: t('layoutNewPassword'), val: pwNew, setter: setPwNew, show: showPwNew, toggle: setShowPwNew, placeholder: t('layoutNewPasswordPlaceholder') },
                      { id: 'pwConfirm', label: t('layoutConfirmNewPassword'), val: pwConfirm, setter: setPwConfirm, show: showPwConfirm, toggle: setShowPwConfirm, placeholder: t('layoutConfirmPasswordPlaceholder') },
                    ].map((field) => (
                      <div key={field.id} className="app-modal-field">
                        <label>{field.label}</label>
                        <div className="app-modal-pw-wrap">
                          <input
                            type={field.show ? 'text' : 'password'}
                            value={field.val}
                            onChange={(e) => field.setter(e.target.value)}
                            placeholder={field.placeholder}
                            required
                            autoComplete="new-password"
                          />
                          <button
                            type="button"
                            onClick={() => field.toggle((v) => !v)}
                            className="app-modal-pw-toggle"
                            tabIndex={-1}
                            aria-label={field.show ? t('layoutHidePassword') : t('layoutShowPassword')}
                          >
                            {field.show ? <EyeOff size={16} /> : <Eye size={16} />}
                          </button>
                        </div>
                        {field.id === 'pwNew' && pwNew && (
                          <div className="app-modal-strength">
                            {[1, 2, 3, 4].map((i) => (
                              <div
                                key={i}
                                className={`app-modal-strength-bar ${i <= pwStrengthLevel ? `filled ${pwStrength}` : ''}`}
                              />
                            ))}
                            <span className="app-modal-strength-label">
                              {pwStrength ? pwStrength.charAt(0).toUpperCase() + pwStrength.slice(1) : ''}
                            </span>
                          </div>
                        )}
                      </div>
                    ))}

                    <div className="app-modal-actions">
                      <button
                        type="button"
                        className="app-modal-btn app-modal-btn-secondary"
                        onClick={() => { setPwCurrent(''); setPwNew(''); setPwConfirm(''); setPwError(''); }}
                      >
                        {t('layoutClear')}
                      </button>
                      <button type="submit" disabled={pwLoading} className="app-modal-btn app-modal-btn-primary">
                        {pwLoading ? <Loader2 size={16} className="animate-spin" /> : <Lock size={16} />}
                        {pwLoading ? t('layoutChanging') : t('changePassword')}
                      </button>
                    </div>
                  </form>
                )}

                {settingsTab === 'profile' && (
                  <div>
                    <p className="app-modal-section-title">{t('layoutYourAccount')}</p>

                    <div className="app-modal-profile-card">
                      <div className="app-modal-avatar">
                        {(user.first_name?.[0] || user.email?.[0] || '?').toUpperCase()}
                      </div>
                      <div>
                        <p className="app-modal-profile-name">
                          {user.first_name || user.last_name
                            ? `${user.first_name || ''} ${user.last_name || ''}`.trim()
                            : user.email || t('layoutUnknownUser')}
                        </p>
                        <p className="app-modal-profile-email">{user.email}</p>
                        <span className="app-modal-role-badge">
                          {(user.role || 'auditor').replace(/_/g, ' ')}
                        </span>
                      </div>
                    </div>

                    <div className="app-modal-info-grid">
                      {[
                        { label: t('employeeId'), val: user.employee_id || user.id || '—' },
                        { label: t('department'), val: user.department || '—' },
                        { label: t('role'), val: (user.role || 'auditor').replace(/_/g, ' ') },
                        { label: t('status'), val: user.is_active === false ? t('inactive') : t('active') },
                      ].map((f) => (
                        <div key={f.label} className="app-modal-info-item">
                          <label>{f.label}</label>
                          <div>{f.val}</div>
                        </div>
                      ))}
                    </div>

                    <form onSubmit={handleSaveProfile}>
                      <p className="app-modal-section-title">{t('layoutEditName')}</p>
                      <div className="app-modal-info-grid">
                        <div className="app-modal-field" style={{ marginBottom: 0 }}>
                          <label>{t('firstName')}</label>
                          <input
                            type="text"
                            value={profileFirstName}
                            onChange={(e) => setProfileFirstNameDraft(e.target.value)}
                            placeholder={t('layoutFirstNamePlaceholder')}
                          />
                        </div>
                        <div className="app-modal-field" style={{ marginBottom: 0 }}>
                          <label>{t('lastName')}</label>
                          <input
                            type="text"
                            value={profileLastName}
                            onChange={(e) => setProfileLastNameDraft(e.target.value)}
                            placeholder={t('layoutLastNamePlaceholder')}
                          />
                        </div>
                      </div>

                      {profileError && (
                        <div className="app-modal-alert error" style={{ marginTop: 16 }}>
                          <AlertCircle size={18} style={{ flexShrink: 0, marginTop: 1 }} />
                          <span>{profileError}</span>
                        </div>
                      )}
                      {profileSuccess && (
                        <div className="app-modal-alert success" style={{ marginTop: 16 }}>
                          <CircleCheck size={18} style={{ flexShrink: 0, marginTop: 1 }} />
                          <span>{t('layoutProfileUpdated')}</span>
                        </div>
                      )}

                      <div className="app-modal-actions">
                        <button type="submit" disabled={profileSaving} className="app-modal-btn app-modal-btn-primary">
                          {profileSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                          {profileSaving ? t('layoutSaving') : t('layoutSaveProfile')}
                        </button>
                      </div>
                    </form>
                  </div>
                )}
              </div>
            </div>
          </div>
      </Modal>

      {/* Help Modal */}
      <Modal
        isOpen={showHelp}
        onClose={() => setShowHelp(false)}
        title={(
          <span className="flex items-center gap-2">
            <HelpCircle size={18} /> {t('layoutHelpTitle')}
          </span>
        )}
        subtitle={t('layoutHelpSubtitle')}
        size="xl"
        footer={(
          /* Modal's footer is justify-end; this one wants the support line on
             the left, so it takes the full width and spaces itself. */
          <div className="flex flex-1 items-center justify-between gap-3">
            <div className="app-modal-footer-support">
              <Mail size={14} />
              <span>{t('layoutItHelpDesk')} <strong>audit.support@eeu.gov.et</strong></span>
            </div>
            <button type="button" className="app-modal-btn app-modal-btn-secondary" onClick={() => setShowHelp(false)}>
              {t('layoutCloseGuide')}
            </button>
          </div>
        )}
      >
        <div className="-m-6">
          <div className="app-modal-layout">
              <nav className="app-modal-nav" aria-label={t('layoutHelpSectionsAria')}>
                {helpTabs.map((tab) => {
                  const TabIcon = tab.icon;
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setHelpTab(tab.id)}
                      className={`app-modal-nav-btn ${helpTab === tab.id ? 'active' : ''}`}
                    >
                      <span className="app-modal-nav-icon"><TabIcon size={16} /></span>
                      <span>{tab.label}</span>
                    </button>
                  );
                })}
              </nav>

              <div className="app-modal-content">
                {helpTab === 'overview' && (
                  <div>
                    <div className="app-modal-help-card">
                      <h4>{t('layoutHelpAboutTitle')}</h4>
                      <p>
                        {t('layoutHelpAboutText')}
                      </p>
                    </div>

                    <p className="app-modal-section-title">{t('layoutHelpSystemRoles')}</p>
                    {[
                      { role: t('layoutHelpRoleSuperAdmin'), desc: t('layoutHelpRoleSuperAdminDesc') },
                      { role: t('layoutHelpRoleManager'), desc: t('layoutHelpRoleManagerDesc') },
                      { role: t('layoutHelpRoleSupervisor'), desc: t('layoutHelpRoleSupervisorDesc') },
                      { role: t('layoutHelpRoleAuditor'), desc: t('layoutHelpRoleAuditorDesc') },
                      { role: t('layoutHelpRoleAuditee'), desc: t('layoutHelpRoleAuditeeDesc') },
                    ].map((r, idx) => (
                      <div key={idx} className="app-modal-role-item">
                        <span className="app-modal-role-dot" />
                        <div>
                          <strong>{r.role}</strong>
                          <span>{r.desc}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {helpTab === 'stages' && (
                  <div>
                    <p className="app-modal-section-title">{t('layoutHelpLifecycle')}</p>
                    <div className="app-modal-timeline">
                      {[
                        { title: t('layoutHelpStage1Title'), actor: t('layoutHelpStage1Actor'), text: t('layoutHelpStage1Text') },
                        { title: t('layoutHelpStage2Title'), actor: t('layoutHelpStage2Actor'), text: t('layoutHelpStage2Text') },
                        { title: t('layoutHelpStage3Title'), actor: t('layoutHelpStage3Actor'), text: t('layoutHelpStage3Text') },
                        { title: t('layoutHelpStage4Title'), actor: t('layoutHelpStage4Actor'), text: t('layoutHelpStage4Text') },
                        { title: t('layoutHelpStage5Title'), actor: t('layoutHelpStage5Actor'), text: t('layoutHelpStage5Text') },
                        { title: t('layoutHelpStage6Title'), actor: t('layoutHelpStage6Actor'), text: t('layoutHelpStage6Text') },
                        { title: t('layoutHelpStage7Title'), actor: t('layoutHelpStage7Actor'), text: t('layoutHelpStage7Text') },
                      ].map((s, idx) => (
                        <div key={idx} className="app-modal-timeline-item">
                          <div className="stage-header">
                            <span className="stage-title">{s.title}</span>
                            <span className="stage-actor">{s.actor}</span>
                          </div>
                          <p>{s.text}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {helpTab === 'checklist' && (
                  <div>
                    <p className="app-modal-section-title">{t('layoutHelpRoleTasks')}</p>
                    <div className="app-modal-role-pills">
                      {[
                        { id: 'admin', label: t('layoutHelpPillAdmin') },
                        { id: 'manager', label: t('layoutHelpPillManager') },
                        { id: 'supervisor', label: t('layoutHelpPillSupervisor') },
                        { id: 'auditor', label: t('layoutHelpPillAuditor') },
                        { id: 'auditee', label: t('layoutHelpPillAuditee') },
                      ].map((role) => (
                        <button
                          key={role.id}
                          type="button"
                          onClick={() => setHelpRole(role.id)}
                          className={`app-modal-role-pill ${helpRole === role.id ? 'active' : ''}`}
                        >
                          {role.label}
                        </button>
                      ))}
                    </div>

                    <div>
                      {helpRole === 'admin' && [
                        { id: 'a1', label: t('layoutHelpTaskA1') },
                        { id: 'a2', label: t('layoutHelpTaskA2') },
                        { id: 'a3', label: t('layoutHelpTaskA3') },
                        { id: 'a4', label: t('layoutHelpTaskA4') },
                      ].map((task) => (
                        <label key={task.id} className={`app-modal-checklist-item ${checkedTasks[task.id] ? 'checked' : ''}`}>
                          <input type="checkbox" checked={!!checkedTasks[task.id]} onChange={() => toggleTask(task.id)} />
                          <span>{task.label}</span>
                        </label>
                      ))}

                      {helpRole === 'manager' && [
                        { id: 'm1', label: t('layoutHelpTaskM1') },
                        { id: 'm2', label: t('layoutHelpTaskM2') },
                        { id: 'm3', label: t('layoutHelpTaskM3') },
                        { id: 'm4', label: t('layoutHelpTaskM4') },
                        { id: 'm5', label: t('layoutHelpTaskM5') },
                        { id: 'm6', label: t('layoutHelpTaskM6') },
                        { id: 'm7', label: t('layoutHelpTaskM7') },
                      ].map((task) => (
                        <label key={task.id} className={`app-modal-checklist-item ${checkedTasks[task.id] ? 'checked' : ''}`}>
                          <input type="checkbox" checked={!!checkedTasks[task.id]} onChange={() => toggleTask(task.id)} />
                          <span>{task.label}</span>
                        </label>
                      ))}

                      {helpRole === 'supervisor' && [
                        { id: 's1', label: t('layoutHelpTaskS1') },
                        { id: 's2', label: t('layoutHelpTaskS2') },
                        { id: 's3', label: t('layoutHelpTaskS3') },
                        { id: 's4', label: t('layoutHelpTaskS4') },
                        { id: 's5', label: t('layoutHelpTaskS5') },
                      ].map((task) => (
                        <label key={task.id} className={`app-modal-checklist-item ${checkedTasks[task.id] ? 'checked' : ''}`}>
                          <input type="checkbox" checked={!!checkedTasks[task.id]} onChange={() => toggleTask(task.id)} />
                          <span>{task.label}</span>
                        </label>
                      ))}

                      {helpRole === 'auditor' && [
                        { id: 'au1', label: t('layoutHelpTaskAu1') },
                        { id: 'au2', label: t('layoutHelpTaskAu2') },
                        { id: 'au3', label: t('layoutHelpTaskAu3') },
                        { id: 'au4', label: t('layoutHelpTaskAu4') },
                        { id: 'au5', label: t('layoutHelpTaskAu5') },
                        { id: 'au6', label: t('layoutHelpTaskAu6') },
                        { id: 'au7', label: t('layoutHelpTaskAu7') },
                        { id: 'au8', label: t('layoutHelpTaskAu8') },
                      ].map((task) => (
                        <label key={task.id} className={`app-modal-checklist-item ${checkedTasks[task.id] ? 'checked' : ''}`}>
                          <input type="checkbox" checked={!!checkedTasks[task.id]} onChange={() => toggleTask(task.id)} />
                          <span>{task.label}</span>
                        </label>
                      ))}

                      {helpRole === 'auditee' && [
                        { id: 'aud1', label: t('layoutHelpTaskAud1') },
                        { id: 'aud2', label: t('layoutHelpTaskAud2') },
                        { id: 'aud3', label: t('layoutHelpTaskAud3') },
                        { id: 'aud4', label: t('layoutHelpTaskAud4') },
                      ].map((task) => (
                        <label key={task.id} className={`app-modal-checklist-item ${checkedTasks[task.id] ? 'checked' : ''}`}>
                          <input type="checkbox" checked={!!checkedTasks[task.id]} onChange={() => toggleTask(task.id)} />
                          <span>{task.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
      </Modal>
    </div>
  );
}

export default AppLayout;
