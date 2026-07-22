import React, { useState, useEffect } from 'react';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { authApi } from '../../api/apiClient';
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
  BookOpen,
  Settings,
  HelpCircle
} from 'lucide-react';

function AppLayout() {
  const [user, setUser] = useState({ email: '', role: 'auditor', first_name: 'Auditor' });
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [notifications, setNotifications] = useState([
    { id: 1, title: 'New Audit Assigned', text: 'You have been assigned to ENG-2026-003', read: false },
    { id: 2, title: 'CAPA Overdue', text: 'Corrective action CAPA-001 is overdue', read: false }
  ]);
  const [showNotifications, setShowNotifications] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [apiServer, setApiServer] = useState(localStorage.getItem('apiBaseUrl') || 'http://localhost:8000/api');
  const [themeMode, setThemeMode] = useState(localStorage.getItem('themeMode') || 'dark');
  const [language, setLanguage] = useState(localStorage.getItem('lang') || 'EN');
  const [saveSuccess, setSaveSuccess] = useState(false);

  const handleSaveSettings = (e) => {
    e.preventDefault();
    localStorage.setItem('apiBaseUrl', apiServer);
    localStorage.setItem('themeMode', themeMode);
    localStorage.setItem('lang', language);
    setSaveSuccess(true);
    setTimeout(() => {
      setSaveSuccess(false);
      setShowSettings(false);
      window.location.reload();
    }, 1200);
  };

  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const currentUser = authApi.getCurrentUser();
    if (currentUser) {
      setUser(currentUser);
    }
  }, []);

  const handleLogout = () => {
    authApi.logout();
  };

  const navItems = [
    { path: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard size={20} /> },
    { path: '/planning', label: 'Audit Planning', icon: <Calendar size={20} /> },
    { path: '/execution', label: 'Audit Execution', icon: <ListTodo size={20} /> },
    { path: '/findings', label: 'Findings Registry', icon: <AlertTriangle size={20} /> },
    { path: '/risk', label: 'Risk Assessment', icon: <TrendingUp size={20} /> },
    { path: '/capa', label: 'Corrective Actions', icon: <CheckCircle size={20} /> },
    { path: '/reports', label: 'Reports & Analytics', icon: <BarChart3 size={20} /> },
  ];

  // Admins and audit managers can see User Management & Audit Trail
  if (user.role === 'admin' || user.role === 'audit_manager') {
    navItems.push({ path: '/users', label: 'User Management', icon: <Users size={20} /> });
    navItems.push({ path: '/audit-trail', label: 'Audit Trail', icon: <Activity size={20} /> });
  }

  const activeNavItem = navItems.find(item => location.pathname === item.path) || { label: 'Audit Management System' };

  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className={`app-sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <img src="/eeu-logo.png" alt="EEU Logo" className="brand-logo" />
            <span>EEU Internal Audit</span>
          </div>
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
            <span className="nav-item-label">Sign Out</span>
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
            <div className="notification-container">
              <button
                className="header-action-btn relative"
                onClick={() => setShowNotifications(!showNotifications)}
              >
                <Bell size={20} />
                {notifications.some(n => !n.read) && (
                  <span className="notification-badge"></span>
                )}
              </button>

              {showNotifications && (
                <div className="notifications-dropdown">
                  <div className="dropdown-header">
                    <h3>Notifications</h3>
                    <button className="text-btn" onClick={() => setNotifications(notifications.map(n => ({ ...n, read: true })))}>
                      Mark all read
                    </button>
                  </div>
                  <div className="dropdown-body">
                    {notifications.length === 0 ? (
                      <p className="no-notifications">No new notifications</p>
                    ) : (
                      notifications.map(n => (
                        <div key={n.id} className={`notification-item ${n.read ? 'read' : 'unread'}`}>
                          <h4>{n.title}</h4>
                          <p>{n.text}</p>
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
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-[#111827] border border-slate-800 rounded-2xl p-6 w-[450px] shadow-2xl relative">
            <button
              onClick={() => setShowSettings(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white transition-colors"
            >
              <X size={20} />
            </button>
            <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
              <Settings className="text-amber-400" size={22} />
              System Settings
            </h3>

            {saveSuccess && (
              <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 p-3 rounded-lg text-sm mb-4">
                ✓ Settings saved successfully! Reloading...
              </div>
            )}

            <form onSubmit={handleSaveSettings} className="space-y-4 text-left">
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">
                  API Endpoint Server URL
                </label>
                <input
                  type="text"
                  value={apiServer}
                  onChange={(e) => setApiServer(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg h-10 px-3 text-slate-200 text-sm focus:border-amber-400 outline-none"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">
                  System Language
                </label>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg h-10 px-2 text-slate-200 text-sm focus:border-amber-400 outline-none"
                >
                  <option value="EN">English (EN)</option>
                  <option value="AM">Amharic (AM)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">
                  Theme Preference
                </label>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 text-slate-300 text-sm cursor-pointer select-none">
                    <input
                      type="radio"
                      name="themeMode"
                      value="dark"
                      checked={themeMode === 'dark'}
                      onChange={() => setThemeMode('dark')}
                      className="accent-amber-400"
                    />
                    Dark Mode (Default)
                  </label>
                  <label className="flex items-center gap-2 text-slate-300 text-sm cursor-pointer select-none">
                    <input
                      type="radio"
                      name="themeMode"
                      value="light"
                      checked={themeMode === 'light'}
                      onChange={() => setThemeMode('light')}
                      className="accent-amber-400"
                    />
                    Light Mode
                  </label>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowSettings(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-sm transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold rounded-lg text-sm transition-colors cursor-pointer"
                >
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Help Modal */}
      {showHelp && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-[#111827] border border-slate-800 rounded-2xl p-6 w-[500px] shadow-2xl relative text-left">
            <button
              onClick={() => setShowHelp(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white transition-colors"
            >
              <X size={20} />
            </button>
            <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
              <HelpCircle className="text-amber-400" size={22} />
              Help Center & Support
            </h3>

            <div className="space-y-4 max-h-[350px] overflow-y-auto pr-2 scrollbar-thin">
              <div className="bg-slate-950 border border-slate-800 rounded-lg p-3">
                <h4 className="font-bold text-amber-300 text-sm mb-1.5">🔑 First-time Config / Setup</h4>
                <p className="text-xs text-slate-300 leading-relaxed">
                  If the application cannot fetch data from the server, check your configured API Endpoint Server URL in the <strong>Settings</strong> panel (cog icon). Default is <code>http://localhost:8000/api</code>.
                </p>
              </div>

              <div className="bg-slate-950 border border-slate-800 rounded-lg p-3">
                <h4 className="font-bold text-amber-300 text-sm mb-1.5">💼 Internal Audit FAQs</h4>
                <div className="space-y-2 text-xs text-slate-300">
                  <div>
                    <strong className="text-white block">Q: How do I plan a new Audit?</strong>
                    <span>Navigate to the "Audit Planning" tab from the sidebar menu to draft new audit schedules and select team members.</span>
                  </div>
                  <div>
                    <strong className="text-white block">Q: How do I assign CAPAs (Corrective Actions)?</strong>
                    <span>Go to the "Corrective Actions" page, click on "Add CAPA", choose the related audit findings and set the auditee department in charge.</span>
                  </div>
                </div>
              </div>

              <div className="bg-slate-950 border border-slate-800 rounded-lg p-3">
                <h4 className="font-bold text-amber-300 text-sm mb-1.5">📞 Contact EEU IT Help Desk</h4>
                <ul className="text-xs text-slate-300 space-y-1.5">
                  <li className="flex items-center gap-2">
                    <span className="text-amber-400">📞 Phone:</span> +251 11-123-4567 (Ext: 4402)
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="text-amber-400">✉️ Email:</span> audit.support@eeu.gov.et
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="text-amber-400">🏢 Office:</span> EEU Headquarters, Internal Audit Division, 4th Floor.
                  </li>
                </ul>
              </div>
            </div>

            <div className="flex justify-end pt-4 border-t border-slate-800 mt-4">
              <button
                type="button"
                onClick={() => setShowHelp(false)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-sm transition-colors cursor-pointer"
              >
                Close Support
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AppLayout;
