import type { ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from './lib/auth/useAuth';
import { CaptureScreen } from './screens/CaptureScreen';
import { CookbookScreen } from './screens/CookbookScreen';
import { HomeScreen } from './screens/HomeScreen';
import { JobScreen } from './screens/JobScreen';
import { SignInScreen } from './screens/SignInScreen';
import { SplashScreen } from './screens/SplashScreen';

function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/signin" replace />;
  }
  return <>{children}</>;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<SplashScreen />} />
      <Route path="/signin" element={<SignInScreen />} />
      <Route
        path="/home"
        element={
          <RequireAuth>
            <HomeScreen />
          </RequireAuth>
        }
      />
      <Route
        path="/capture"
        element={
          <RequireAuth>
            <CaptureScreen />
          </RequireAuth>
        }
      />
      <Route
        path="/jobs/:jobId"
        element={
          <RequireAuth>
            <JobScreen />
          </RequireAuth>
        }
      />
      <Route
        path="/cookbook"
        element={
          <RequireAuth>
            <CookbookScreen />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
