import React, { useState, useEffect, useCallback, useRef } from 'react';

// ── Translations ──────────────────────────────────────────────
const TRANSLATIONS = {
  EN: {
    dashboard: 'Dashboard',
    auditPlanning: 'Audit Planning',
    auditExecution: 'Audit Execution',
    findingsRegistry: 'Findings Registry',
    riskAssessment: 'Risk Assessment',
    correctiveActions: 'Corrective Actions',
    reportsAnalytics: 'Reports & Analytics',
    userManagement: 'User Management',
    auditTrail: 'Audit Trail',
    signOut: 'Sign Out',
    notifications: 'Notifications',
    markAllRead: 'Mark all read',
    noNotifications: 'No new notifications',
    systemSettings: 'System Settings',
    general: 'General',
    changePassword: 'Change Password',
    profile: 'Profile',
    apiEndpoint: 'API Endpoint Server URL',
    systemLanguage: 'System Language',
    themePreference: 'Theme Preference',
    darkMode: '🌙 Dark Mode',
    lightMode: '☀️ Light Mode',
    darkModeSub: 'Default (Recommended)',
    lightModeSub: 'High-contrast environment',
    cancel: 'Cancel',
    saveChanges: 'Save Changes',
    settingsSaved: '✓ Settings saved! Applying changes...',
    help: 'Help & Support',
  },
  AM: {
    dashboard: 'ዳሽቦርድ',
    auditPlanning: 'የኦዲት እቅድ',
    auditExecution: 'የኦዲት አፈጻጸም',
    findingsRegistry: 'ግኝቶች መዝገብ',
    riskAssessment: 'የአደጋ ግምገማ',
    correctiveActions: 'እርምት እርምጃዎች',
    reportsAnalytics: 'ሪፖርቶች እና ትንታኔ',
    userManagement: 'የተጠቃሚ አስተዳደር',
    auditTrail: 'የኦዲት ዱካ',
    signOut: 'ዘግተህ ውጣ',
    notifications: 'ማሳወቂያዎች',
    markAllRead: 'ሁሉም እንደተነበበ ምልክት ያድርጉ',
    noNotifications: 'አዲስ ማሳወቂያ የለም',
    systemSettings: 'የስርዓት ቅንብሮች',
    general: 'አጠቃላይ',
    changePassword: 'የይለፍ ቃል ቀይር',
    profile: 'መገለጫ',
    apiEndpoint: 'የ API አገልጋይ URL',
    systemLanguage: 'የስርዓት ቋንቋ',
    themePreference: 'የቴሜ ምርጫ',
    darkMode: '🌙 ጨለማ ሁነታ',
    lightMode: '☀️ ብርሃን ሁነታ',
    darkModeSub: 'ነባሪ (የሚመከር)',
    lightModeSub: 'ከፍተኛ-ኮንትራስት አካባቢ',
    cancel: 'ሰርዝ',
    saveChanges: 'ለውጦችን አስቀምጥ',
    settingsSaved: '✓ ቅንብሮች ተቀምጠዋል! ለውጦች እየተተገበሩ...',
    help: 'እርዳታ እና ድጋፍ',
  },
};
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { authApi, notificationApi } from '../../api/apiClient';
import { hasCapability, CAPABILITIES } from '../../hooks/usePermissions';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
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
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [showNotifications, setShowNotifications] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const notifContainerRef = useRef(null);
  const [apiServer, setApiServer] = useState(localStorage.getItem('apiBaseUrl') || 'http://localhost:8000/api');
  const themeMode = auth.theme || 'light';
  const language = auth.language === 'am' ? 'AM' : 'EN';
  const [saveSuccess, setSaveSuccess] = useState(false);


  // Translation helper
  const t = useCallback((key) => {
    return (TRANSLATIONS[language] || TRANSLATIONS.EN)[key] || key;
  }, [language]);
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

  // Profile edit state
  const [profileFirstName, setProfileFirstName] = useState(user.first_name || '');
  const [profileLastName, setProfileLastName] = useState(user.last_name || '');
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

  // Close Settings / Help modals on Escape key
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape') {
        if (showSettings) closeSettingsModal();
        if (showHelp) setShowHelp(false);
        if (showNotifications) setShowNotifications(false);
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [showSettings, showHelp, showNotifications]);

  const handleSaveSettings = (e) => {
    e.preventDefault();
    localStorage.setItem('apiBaseUrl', apiServer);
    toast.success('System settings saved.');
    setShowSettings(false);
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setPwError('');
    if (pwNew !== pwConfirm) {
      setPwError('New passwords do not match.');
      toast.error('New passwords do not match.');
      return;
    }
    if (pwNew.length < 8) {
      setPwError('New password must be at least 8 characters.');
      toast.error('New password must be at least 8 characters.');
      return;
    }
    setPwLoading(true);
    try {
      await authApi.changePassword(pwCurrent, pwNew);
      setPwSuccess(true);
      toast.success('Password changed successfully.');
      setPwCurrent('');
      setPwNew('');
      setPwConfirm('');
      setTimeout(() => setPwSuccess(false), 3000);
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.current_password?.[0] ||
        err?.response?.data?.new_password?.[0] ||
        'Password change failed. Please check your current password.';
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
      setProfileSuccess(true);
      toast.success('Profile updated successfully.');
      setTimeout(() => setProfileSuccess(false), 3000);
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Failed to update profile. Please try again.';
      setProfileError(msg);
      toast.error(msg);
    } finally {
      setProfileSaving(false);
    }
  };

  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    if (user) {
      setProfileFirstName(user.first_name || '');
      setProfileLastName(user.last_name || '');
    }
  }, [user]);

  // Load notifications + unread count from the backend.
  const loadNotifications = useCallback(async () => {
    try {
      const [items, unread] = await Promise.all([
        notificationApi.list(),
        notificationApi.unreadCount(),
      ]);
      setNotifications(Array.isArray(items) ? items : []);
      setUnreadCount(unread);
    } catch (err) {
      // Non-fatal: leave the current state in place if the fetch fails.
      console.error('Failed to load notifications', err);
    }
  }, []);

  // Fetch on mount and poll periodically so new events surface without a reload.
  useEffect(() => {
    loadNotifications();
    const interval = setInterval(loadNotifications, 30000);
    return () => clearInterval(interval);
  }, [loadNotifications]);

  const handleMarkAllRead = useCallback(async () => {
    try {
      await notificationApi.markAllRead();
      toast.info('All notifications marked as read.');
    } catch (err) {
      console.error('Failed to mark all notifications read', err);
    }
    loadNotifications();
  }, [loadNotifications, toast]);

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

  const activeNavItem = navItems.find(item => location.pathname === item.path) || { label: 'Audit Management System' };

  const closeSettingsModal = () => {
    setShowSettings(false);
    setSaveSuccess(false);
    setPwError('');
    setPwSuccess(false);
    setProfileError('');
    setProfileSuccess(false);
  };

  const settingsTabs = [
    { id: 'general', icon: SlidersHorizontal, label: t('general'), desc: 'Language, theme & API' },
    { id: 'password', icon: Lock, label: t('changePassword'), desc: 'Update your credentials' },
    { id: 'profile', icon: UserIcon, label: t('profile'), desc: 'Manage your account' },
  ];

  const helpTabs = [
    { id: 'overview', icon: UsersRound, label: 'Roles Overview' },
    { id: 'stages', icon: GitBranch, label: 'Workflow Stages' },
    { id: 'checklist', icon: ListChecks, label: 'Task Checklists' },
  ];

  const pwStrength = pwNew.length >= 12 ? 'strong' : pwNew.length >= 10 ? 'good' : pwNew.length >= 8 ? 'fair' : pwNew.length > 0 ? 'weak' : '';
  const pwStrengthLevel = pwNew.length >= 12 ? 4 : pwNew.length >= 10 ? 3 : pwNew.length >= 8 ? 2 : pwNew.length > 0 ? 1 : 0;

  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className={`app-sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-header">
          <Link to="/dashboard" className="sidebar-brand" style={{ textDecoration: 'none' }}>
            <img src="/eeu-logo.png" alt="EEU Logo" className="brand-logo" />
            <span>EEU Internal Audit</span>
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

      {/* Main Content Area */}
      <div className={`main-wrapper ${sidebarOpen ? 'sidebar-open' : 'sidebar-closed'}`}>
        {/* Top Header */}
        <header className="app-header">
          <div className="header-left">
            <button className="sidebar-toggle-btn" onClick={() => setSidebarOpen(!sidebarOpen)}>
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

            {/* Help Button */}
            <button
              className="header-action-btn"
              onClick={() => setShowHelp(true)}
              title="Help & Support"
            >
              <HelpCircle size={20} />
            </button>

            {/* Settings Button */}
            <button
              className="header-action-btn"
              onClick={() => setShowSettings(true)}
              title="System Settings"
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
        <main className="content-container">
          <Outlet />
        </main>
      </div>

      {/* Settings Modal */}
      {showSettings && (
        <div
          className="app-modal-overlay"
          onClick={closeSettingsModal}
          onKeyDown={(e) => { if (e.key === 'Escape') closeSettingsModal(); }}
          role="presentation"
        >
          <div
            className="app-modal app-modal-settings"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="settings-modal-title"
          >
            <div className="app-modal-hero">
              <div className="app-modal-hero-inner">
                <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start' }}>
                  <div className="app-modal-hero-icon">
                    <Settings size={22} />
                  </div>
                  <div className="app-modal-hero-text">
                    <h3 id="settings-modal-title">{t('systemSettings')}</h3>
                    <p>Customize your experience — language, appearance, security, and profile preferences.</p>
                  </div>
                </div>
                <button type="button" className="app-modal-close" onClick={closeSettingsModal} aria-label="Close settings">
                  <X size={18} />
                </button>
              </div>
            </div>

            <div className="app-modal-layout">
              <nav className="app-modal-nav" aria-label="Settings sections">
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
                    <p className="app-modal-section-title">Preferences</p>

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
                      <p className="app-modal-field-hint">The base URL of the EEU Audit backend server (no trailing slash).</p>
                    </div>

                    <div className="app-modal-field">
                      <label><Globe size={14} /> {t('systemLanguage')}</label>
                      <div className="app-modal-lang-grid">
                        {[
                          { val: 'EN', flag: '🇬🇧', name: 'English', sub: 'Default' },
                          { val: 'AM', flag: '🇪🇹', name: 'Amharic', sub: 'አማርኛ' },
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
                    <p className="app-modal-section-title">Security</p>

                    <div className="app-modal-alert info">
                      <Lock size={16} style={{ flexShrink: 0, marginTop: 1 }} />
                      <span>
                        Your password must be at least <strong>8 characters</strong> long. After a successful change, you will remain logged in.
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
                        <span>Password changed successfully!</span>
                      </div>
                    )}

                    {[
                      { id: 'pwCurrent', label: 'Current Password', val: pwCurrent, setter: setPwCurrent, show: showPwCurrent, toggle: setShowPwCurrent, placeholder: 'Enter your current password' },
                      { id: 'pwNew', label: 'New Password', val: pwNew, setter: setPwNew, show: showPwNew, toggle: setShowPwNew, placeholder: 'Enter new password (min. 8 chars)' },
                      { id: 'pwConfirm', label: 'Confirm New Password', val: pwConfirm, setter: setPwConfirm, show: showPwConfirm, toggle: setShowPwConfirm, placeholder: 'Re-enter new password' },
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
                            aria-label={field.show ? 'Hide password' : 'Show password'}
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
                        Clear
                      </button>
                      <button type="submit" disabled={pwLoading} className="app-modal-btn app-modal-btn-primary">
                        {pwLoading ? <Loader2 size={16} className="animate-spin" /> : <Lock size={16} />}
                        {pwLoading ? 'Changing...' : 'Change Password'}
                      </button>
                    </div>
                  </form>
                )}

                {settingsTab === 'profile' && (
                  <div>
                    <p className="app-modal-section-title">Your Account</p>

                    <div className="app-modal-profile-card">
                      <div className="app-modal-avatar">
                        {(user.first_name?.[0] || user.email?.[0] || '?').toUpperCase()}
                      </div>
                      <div>
                        <p className="app-modal-profile-name">
                          {user.first_name || user.last_name
                            ? `${user.first_name || ''} ${user.last_name || ''}`.trim()
                            : user.email || 'Unknown User'}
                        </p>
                        <p className="app-modal-profile-email">{user.email}</p>
                        <span className="app-modal-role-badge">
                          {(user.role || 'auditor').replace(/_/g, ' ')}
                        </span>
                      </div>
                    </div>

                    <div className="app-modal-info-grid">
                      {[
                        { label: 'Employee ID', val: user.employee_id || user.id || '—' },
                        { label: 'Department', val: user.department || '—' },
                        { label: 'Role', val: (user.role || 'auditor').replace(/_/g, ' ') },
                        { label: 'Status', val: user.is_active === false ? 'Inactive' : 'Active' },
                      ].map((f) => (
                        <div key={f.label} className="app-modal-info-item">
                          <label>{f.label}</label>
                          <div>{f.val}</div>
                        </div>
                      ))}
                    </div>

                    <form onSubmit={handleSaveProfile}>
                      <p className="app-modal-section-title">Edit Name</p>
                      <div className="app-modal-info-grid">
                        <div className="app-modal-field" style={{ marginBottom: 0 }}>
                          <label>First Name</label>
                          <input
                            type="text"
                            value={profileFirstName}
                            onChange={(e) => setProfileFirstName(e.target.value)}
                            placeholder="First name"
                          />
                        </div>
                        <div className="app-modal-field" style={{ marginBottom: 0 }}>
                          <label>Last Name</label>
                          <input
                            type="text"
                            value={profileLastName}
                            onChange={(e) => setProfileLastName(e.target.value)}
                            placeholder="Last name"
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
                          <span>Profile updated successfully!</span>
                        </div>
                      )}

                      <div className="app-modal-actions">
                        <button type="submit" disabled={profileSaving} className="app-modal-btn app-modal-btn-primary">
                          {profileSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                          {profileSaving ? 'Saving...' : 'Save Profile'}
                        </button>
                      </div>
                    </form>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Help Modal */}
      {showHelp && (
        <div
          className="app-modal-overlay"
          onClick={() => setShowHelp(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowHelp(false); }}
          role="presentation"
        >
          <div
            className="app-modal app-modal-help"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="help-modal-title"
          >
            <div className="app-modal-hero">
              <div className="app-modal-hero-inner">
                <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start' }}>
                  <div className="app-modal-hero-icon">
                    <HelpCircle size={22} />
                  </div>
                  <div className="app-modal-hero-text">
                    <h3 id="help-modal-title">Workflow & Support Center</h3>
                    <p>Guides, role responsibilities, and step-by-step checklists for the EEU Internal Audit system.</p>
                  </div>
                </div>
                <button type="button" className="app-modal-close" onClick={() => setShowHelp(false)} aria-label="Close help">
                  <X size={18} />
                </button>
              </div>
            </div>

            <div className="app-modal-layout">
              <nav className="app-modal-nav" aria-label="Help sections">
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
                      <h4>EEU Internal Audit Management System</h4>
                      <p>
                        This system automates the step-by-step annual audit cycles, scheduling, procedure execution,
                        working paper registry, findings logging, and CAPA resolution for the Ethiopian Electric Utility.
                      </p>
                    </div>

                    <p className="app-modal-section-title">System Roles</p>
                    {[
                      { role: 'Super Admin (admin)', desc: 'Responsible for user management, system configuration, access control, and auditing security logs.' },
                      { role: 'Audit Manager (audit_manager)', desc: 'Drives the annual audit cycle, manages the Audit Universe, creates and approves Annual Plans, and initiates/schedules Engagements.' },
                      { role: 'Audit Supervisor (supervisor)', desc: 'Reviews audit programs, reviews fieldwork working papers, and coordinates the execution.' },
                      { role: 'Auditor / Lead Auditor (auditor)', desc: 'Designs audit program procedures, conducts fieldwork (checklists and workpapers), logs findings, and drafts final reports.' },
                      { role: 'Auditee (auditee)', desc: 'Represents audited departments, completes risk self-assessments, and owns corrective actions (CAPA) execution and updates.' },
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
                    <p className="app-modal-section-title">Audit Lifecycle</p>
                    <div className="app-modal-timeline">
                      {[
                        { title: 'Stage 1: Risk Assessment & Universe Setup', actor: 'Auditor / Manager / Auditee', text: 'Auditors and Managers set up entities in the Audit Universe. Auditees complete risk self-assessments. Managers rank priority entities via the 5x5 Risk Heat Map.' },
                        { title: 'Stage 2: Annual Plan Creation & Submission', actor: 'Audit Manager', text: 'Managers outline annual plans (budgets, schedules, objectives), map universe nodes, and submit plans for approval.' },
                        { title: 'Stage 3: Engagement Scheduling & Staffing', actor: 'Audit Manager', text: 'Managers schedule specific audits under active plans, allocating team members (lead auditor and supervisor).' },
                        { title: 'Stage 4: Execution & Fieldwork', actor: 'Auditor / Supervisor', text: 'Auditors build the audit program and procedures. Supervisors approve the program. Auditors transition procedure status and upload evidence files (Working Papers).' },
                        { title: 'Stage 5: Findings & Recommendations', actor: 'Auditor', text: 'Auditors log deficiency, compliance, or security findings (condition, criteria, cause, effect, recommendation) for supervisor review.' },
                        { title: 'Stage 6: Corrective Action Plan (CAPA) Portal', actor: 'Auditor / Auditee', text: 'Auditors spawn CAPAs. Auditees respond with progress notes and documentation. Supervisors verify and close CAPAs.' },
                        { title: 'Stage 7: Reports & Analytics', actor: 'Auditor / Manager', text: 'Auditors and Managers create final audit reports and close the engagement.' },
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
                    <p className="app-modal-section-title">Role-based Tasks</p>
                    <div className="app-modal-role-pills">
                      {[
                        { id: 'admin', label: 'Admin' },
                        { id: 'manager', label: 'Manager' },
                        { id: 'supervisor', label: 'Supervisor' },
                        { id: 'auditor', label: 'Auditor' },
                        { id: 'auditee', label: 'Auditee' },
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
                        { id: 'a1', label: 'Step 1.1: Log in as administrator using admin@eeu.com.' },
                        { id: 'a2', label: 'Step 1.2: Access User Management in the sidebar.' },
                        { id: 'a3', label: 'Step 1.3: Add new users and activate/deactivate accounts.' },
                        { id: 'a4', label: 'Step 1.4: Check Audit Trail in the sidebar to review system access logs.' },
                      ].map((task) => (
                        <label key={task.id} className={`app-modal-checklist-item ${checkedTasks[task.id] ? 'checked' : ''}`}>
                          <input type="checkbox" checked={!!checkedTasks[task.id]} onChange={() => toggleTask(task.id)} />
                          <span>{task.label}</span>
                        </label>
                      ))}

                      {helpRole === 'manager' && [
                        { id: 'm1', label: 'Step 2.1: Log in as manager using manager@eeu.com.' },
                        { id: 'm2', label: 'Step 2.2: Manage the Audit Universe (add entities, projects, or processes).' },
                        { id: 'm3', label: 'Step 2.3: Open Risk Assessment weights and view the 5x5 Risk Heat Map.' },
                        { id: 'm4', label: 'Step 2.4: Create a new Annual Audit Plan (year, budget, dates, objectives).' },
                        { id: 'm5', label: 'Step 2.5: Submit and approve the Annual Plan (change status to Approved).' },
                        { id: 'm6', label: 'Step 2.6: Schedule individual Audit Engagements and assign team members.' },
                        { id: 'm7', label: 'Step 2.7: Open Reports and compile/review/lock final audit reports.' },
                      ].map((task) => (
                        <label key={task.id} className={`app-modal-checklist-item ${checkedTasks[task.id] ? 'checked' : ''}`}>
                          <input type="checkbox" checked={!!checkedTasks[task.id]} onChange={() => toggleTask(task.id)} />
                          <span>{task.label}</span>
                        </label>
                      ))}

                      {helpRole === 'supervisor' && [
                        { id: 's1', label: 'Step 3.1: Log in as supervisor using supervisor@eeu.com.' },
                        { id: 's2', label: 'Step 3.2: Open Audit Execution and review Objectives & Scope.' },
                        { id: 's3', label: 'Step 3.3: Approve program (transitions from draft to approved).' },
                        { id: 's4', label: 'Step 3.4: Monitor active fieldwork of assigned lead auditors.' },
                        { id: 's5', label: 'Step 3.5: Inspect uploaded working papers and post review notes.' },
                      ].map((task) => (
                        <label key={task.id} className={`app-modal-checklist-item ${checkedTasks[task.id] ? 'checked' : ''}`}>
                          <input type="checkbox" checked={!!checkedTasks[task.id]} onChange={() => toggleTask(task.id)} />
                          <span>{task.label}</span>
                        </label>
                      ))}

                      {helpRole === 'auditor' && [
                        { id: 'au1', label: 'Step 4.1: Log in as auditor using auditor@eeu.com.' },
                        { id: 'au2', label: 'Step 4.2: Navigate to Audit Execution and select active engagement.' },
                        { id: 'au3', label: 'Step 4.3: Create/define the Audit Program if missing.' },
                        { id: 'au4', label: 'Step 4.4: Add specific Fieldwork Procedures under the program.' },
                        { id: 'au5', label: 'Step 4.5: Complete procedures and upload Working Papers evidence files.' },
                        { id: 'au6', label: 'Step 4.6: Navigate to Findings Registry and Log Findings.' },
                        { id: 'au7', label: 'Step 4.7: Navigate to Corrective Actions and spawn CAPA tasks.' },
                        { id: 'au8', label: 'Step 4.8: Access Reports & Analytics to draft engagement reports.' },
                      ].map((task) => (
                        <label key={task.id} className={`app-modal-checklist-item ${checkedTasks[task.id] ? 'checked' : ''}`}>
                          <input type="checkbox" checked={!!checkedTasks[task.id]} onChange={() => toggleTask(task.id)} />
                          <span>{task.label}</span>
                        </label>
                      ))}

                      {helpRole === 'auditee' && [
                        { id: 'aud1', label: 'Step 5.1: Log in as auditee using auditee@eeu.com.' },
                        { id: 'aud2', label: 'Step 5.2: Go to Risk Assessment -> Self Assessment operational survey.' },
                        { id: 'aud3', label: 'Step 5.3: Open the Corrective Actions portal.' },
                        { id: 'aud4', label: 'Step 5.4: Locate assigned CAPAs, respond, upload evidence, and update status.' },
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

            <div className="app-modal-footer">
              <div className="app-modal-footer-support">
                <Mail size={14} />
                <span>IT Help Desk: <strong>audit.support@eeu.gov.et</strong></span>
              </div>
              <button type="button" className="app-modal-btn app-modal-btn-secondary" onClick={() => setShowHelp(false)}>
                Close Guide
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AppLayout;
