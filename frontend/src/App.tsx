import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from './lib/auth/AuthProvider';
import { AppRoutes } from './router';

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
