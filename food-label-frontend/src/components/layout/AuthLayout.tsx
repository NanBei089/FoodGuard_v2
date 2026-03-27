import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';

export function AuthLayout() {
  const { isAuthenticated, needsOnboarding } = useAuthStore();

  if (isAuthenticated) {
    return <Navigate to={needsOnboarding ? '/onboarding' : '/'} replace />;
  }

  return (
    <div className="bg-pattern relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-50 px-4 py-10">
      <div className="pointer-events-none absolute left-[-8%] top-[-10%] h-96 w-96 rounded-full bg-emerald-300/30 blur-3xl" />
      <div className="animation-delay-2000 pointer-events-none absolute bottom-[-10%] right-[-8%] h-96 w-96 rounded-full bg-teal-300/30 blur-3xl animate-blob" />

      <div className="relative z-10 w-full max-w-md">
        <Outlet />
      </div>
    </div>
  );
}
