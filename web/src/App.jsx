import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import Layout from "./components/Layout";
import PrivateRoute from "./components/PrivateRoute";
import ErrorBoundary from "./components/ErrorBoundary";
import LoginPage from "./pages/LoginPage";
import RecommendationsPage from "./pages/RecommendationsPage";
import ScreeningPage from "./pages/ScreeningPage";
import AnalysisPage from "./pages/AnalysisPage";
import WatchlistPage from "./pages/WatchlistPage";
import AdminPage from "./pages/AdminPage";
import WinRatePage from "./pages/WinRatePage";
import DashboardPage from "./pages/DashboardPage";
import HelpPage from "./pages/HelpPage";

export default function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface-0">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <ErrorBoundary>
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" /> : <LoginPage />} />
      <Route element={<PrivateRoute />}>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="recommendations/us" element={<RecommendationsPage market="us" />} />
          <Route path="recommendations/hk" element={<RecommendationsPage market="hk" />} />
          <Route path="screening" element={<ScreeningPage />} />
          <Route path="analysis" element={<AnalysisPage />} />
          <Route path="watchlist" element={<WatchlistPage />} />
          <Route path="win-rate" element={<WinRatePage />} />
          <Route path="help" element={<HelpPage />} />
          {user?.is_admin && <Route path="admin" element={<AdminPage />} />}
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" />} />
    </Routes>
    </ErrorBoundary>
  );
}
