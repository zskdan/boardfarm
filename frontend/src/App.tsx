import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Navigate, Route, BrowserRouter as Router, Routes } from 'react-router-dom';
import './index.css';
import { getUsername } from './api/client';
import AdminPage from './pages/AdminPage';
import BoardDetailPage from './pages/BoardDetailPage';
import DiscoveryPage from './pages/DiscoveryPage';
import HistoryPage from './pages/HistoryPage';
import InventoryPage from './pages/InventoryPage';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000 } },
});

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!getUsername()) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <Routes>
          <Route path="/" element={<DiscoveryPage />} />
          <Route
            path="/boards"
            element={
              <RequireAuth>
                <InventoryPage />
              </RequireAuth>
            }
          />
          <Route
            path="/boards/:id"
            element={
              <RequireAuth>
                <BoardDetailPage />
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
            path="/admin"
            element={
              <RequireAuth>
                <AdminPage />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/boards" replace />} />
        </Routes>
      </Router>
    </QueryClientProvider>
  );
}
