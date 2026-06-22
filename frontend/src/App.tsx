import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Navigate, Route, BrowserRouter as Router, Routes } from 'react-router-dom';
import './index.css';
import { getUsername } from './api/client';
import AppHeader from './components/AppHeader';
import DeviceDetailPage from './pages/DeviceDetailPage';
import DiscoveryPage from './pages/DiscoveryPage';
import HistoryPage from './pages/HistoryPage';
import InventoryPage from './pages/InventoryPage';
import SetupsPage from './pages/SetupsPage';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000 } },
});

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!getUsername()) {
    return <Navigate to="/" replace />;
  }
  return (
    <div className="min-h-screen flex flex-col">
      <AppHeader />
      <div className="flex-1">{children}</div>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <Routes>
          <Route path="/" element={<DiscoveryPage />} />
          <Route
            path="/devices"
            element={
              <RequireAuth>
                <InventoryPage />
              </RequireAuth>
            }
          />
          <Route
            path="/devices/:id"
            element={
              <RequireAuth>
                <DeviceDetailPage />
              </RequireAuth>
            }
          />
          <Route
            path="/history"
            element={
              <RequireAuth>
                <HistoryPage />
              </RequireAuth>
            }
          />
          <Route
            path="/setups"
            element={
              <RequireAuth>
                <SetupsPage />
              </RequireAuth>
            }
          />
          <Route path="/admin" element={<Navigate to="/devices" replace />} />
          <Route path="*" element={<Navigate to="/devices" replace />} />
        </Routes>
      </Router>
    </QueryClientProvider>
  );
}
