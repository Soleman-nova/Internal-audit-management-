import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import LoginPage from './pages/auth/LoginPage';
import AppLayout from './components/layout/AppLayout';
import DashboardPage from './pages/dashboard/DashboardPage';
import PlanningPage from './pages/planning/PlanningPage';
import ExecutionPage from './pages/execution/ExecutionPage';
import FindingsPage from './pages/findings/FindingsPage';
import FindingDetailPage from './pages/findings/FindingDetailPage';
import RiskAssessmentPage from './pages/risk/RiskAssessmentPage';
import FollowUpPage from './pages/followup/FollowUpPage';
import CapaDetailPage from './pages/followup/CapaDetailPage';
import ReportsPage from './pages/reports/ReportsPage';
import UsersPage from './pages/admin/UsersPage';
import AuditTrailPage from './pages/admin/AuditTrailPage';
import { hasCapability, getCurrentUser, CAPABILITIES } from './hooks/usePermissions';

// Authenticated Route Guard
const ProtectedRoute = ({ children }) => {
  const token = localStorage.getItem('accessToken');
  if (!token) {
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
    </BrowserRouter>
  );
}

export default App;
