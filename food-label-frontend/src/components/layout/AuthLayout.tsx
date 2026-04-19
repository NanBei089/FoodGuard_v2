import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';

/** 未登录区域布局，负责把已登录用户重定向回应用页。 */
export function AuthLayout() {
  const { isAuthenticated, needsOnboarding } = useAuthStore();

  if (isAuthenticated) {
    // 已登录用户访问登录/注册页时直接回到当前应进入的业务页面。
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
