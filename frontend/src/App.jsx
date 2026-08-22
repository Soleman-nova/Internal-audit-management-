import React, { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import Spinner from './components/ui/Spinner';
import { hasLiveSession } from './api/apiClient';
import { hasCapability, getCurrentUser, CAPABILITIES } from './hooks/usePermissions';

// Every page is loaded on demand. Eagerly importing all thirteen produced one
// bundle, so an auditee downloaded the user-management and audit-trail screens
// they can never open — and everyone paid for the PDF/Excel machinery on the
// reports page just to see the dashboard.
//
// AppLayout is *not* lazy: it is the shell around every authenticated route, so
// splitting it would only add a round trip before anything can render.
const LoginPage = lazy(() => import('./pages/auth/LoginPage'));
const DashboardPage = lazy(() => import('./pages/dashboard/DashboardPage'));
const PlanningPage = lazy(() => import('./pages/planning/PlanningPage'));
const ExecutionPage = lazy(() => import('./pages/execution/ExecutionPage'));
const FindingsPage = lazy(() => import('./pages/findings/FindingsPage'));
const FindingDetailPage = lazy(() => import('./pages/findings/FindingDetailPage'));
const RiskAssessmentPage = lazy(() => import('./pages/risk/RiskAssessmentPage'));
const FollowUpPage = lazy(() => import('./pages/followup/FollowUpPage'));
const CapaDetailPage = lazy(() => import('./pages/followup/CapaDetailPage'));
const ReportsPage = lazy(() => import('./pages/reports/ReportsPage'));
const UsersPage = lazy(() => import('./pages/admin/UsersPage'));
const AuditTrailPage = lazy(() => import('./pages/admin/AuditTrailPage'));

// Shown while a route's chunk is in flight. On a warm cache this never paints.
const RouteFallback = () => (
  <div className="flex items-center justify-center min-h-[60vh]">
    <Spinner size="lg" />
  </div>
);

// Authenticated Route Guard
const ProtectedRoute = ({ children }) => {
  // `hasLiveSession` reads the `exp` claim instead of merely checking that a
  // token string exists. A stale token used to render the entire application,
  // fire its requests, and bounce to the login screen on the first 401 — a
  // visible flash of a dashboard the user was never signed in to. It still
  // admits an expired *access* token when the refresh token is live, since the
  // API client exchanges that silently.
  if (!hasLiveSession()) {
    return <Navigate to="/login" replace />;
  }
  return children;
};

// Capability Route Guard — blocks routes the current role may not open.
// Backend permissions remain the real enforcement; this just avoids showing
// pages a user cannot use.
const CapabilityRoute = ({ capability, children }) => {
  const user = getCurrentUser();
  if (!hasCapability(user, capability)) {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
};

function App() {
  return (
    <BrowserRouter>
      {/* One boundary around the whole tree: a nested route swapping pages
          reuses it, and the layout shell stays mounted while the chunk loads. */}
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          <Route
            path="/"
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="planning" element={<PlanningPage />} />
            <Route path="execution" element={<ExecutionPage />} />
            <Route path="findings" element={<FindingsPage />} />
            <Route path="findings/:id" element={<FindingDetailPage />} />
            <Route path="risk" element={<RiskAssessmentPage />} />
            <Route path="capa" element={<FollowUpPage />} />
            <Route path="capa/:id" element={<CapaDetailPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route
              path="users"
              element={
                <CapabilityRoute capability={CAPABILITIES.MANAGE_USERS}>
                  <UsersPage />
                </CapabilityRoute>
              }
            />
            <Route
              path="audit-trail"
              element={
                <CapabilityRoute capability={CAPABILITIES.VIEW_AUDIT_TRAIL}>
                  <AuditTrailPage />
                </CapabilityRoute>
              }
            />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
