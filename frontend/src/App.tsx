import { BrowserRouter } from 'react-router-dom';
import { AppBootGate } from './components/AppBootGate';
import { AuthProvider } from './lib/auth/AuthProvider';
import { JobsProvider } from './lib/jobs/JobsProvider';
import { AppRoutes } from './router';

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <JobsProvider>
          <AppBootGate>
            <AppRoutes />
          </AppBootGate>
        </JobsProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
