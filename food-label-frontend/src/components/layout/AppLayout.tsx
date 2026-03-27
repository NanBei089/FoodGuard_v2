import { useEffect } from 'react';
import { Navigate, NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';
import { fetchSessionContext } from '@/lib/auth-session';
import { cn } from '@/lib/utils';
import { getUserInitial } from '@/lib/foodguard';

export function AppLayout() {
  const location = useLocation();
  const { isAuthenticated, needsOnboarding, user, preferences, setSession } = useAuthStore();

  useEffect(() => {
    if (!isAuthenticated || (user && preferences)) {
      return;
    }

    let cancelled = false;

    const hydrateSession = async () => {
      try {
        const session = await fetchSessionContext();
        if (!cancelled) {
          setSession(session.user, session.preferences);
        }
      } catch {
        // Keep the existing UI state. Auth failures are already handled by the API client.
      }
    };

    void hydrateSession();

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, preferences, setSession, user]);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (needsOnboarding && location.pathname !== '/onboarding') {
    return <Navigate to="/onboarding" replace />;
  }

  if (!needsOnboarding && location.pathname === '/onboarding') {
    return <Navigate to="/" replace />;
  }

  const showBlobs = location.pathname === '/';
  const navGlass = location.pathname === '/';
  const userInitial = user ? getUserInitial(user) : '';

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      {showBlobs && (
        <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
          <div className="absolute left-1/4 top-0 h-96 w-96 rounded-full bg-emerald-300/20 blur-3xl" />
          <div className="animation-delay-2000 absolute right-1/4 top-0 h-96 w-96 rounded-full bg-cyan-300/20 blur-3xl animate-blob" />
          <div className="animation-delay-4000 absolute bottom-[-8rem] left-1/3 h-96 w-96 rounded-full bg-teal-300/20 blur-3xl animate-blob" />
        </div>
      )}

      <nav
        className={cn(
          'sticky top-0 z-50 border-b',
          navGlass
            ? 'glass-panel border-white/60'
            : 'border-slate-200 bg-white/95 backdrop-blur',
        )}
      >
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <NavLink to="/" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-400 to-emerald-600 shadow-lg shadow-emerald-500/30">
              <svg className="h-6 w-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
                />
              </svg>
            </div>
            <span className="text-xl font-bold">FoodGuard</span>
          </NavLink>

          <div className="hidden items-center gap-6 md:flex">
            <NavLink
              to="/"
              className={({ isActive }) =>
                cn(
                  'text-sm font-medium transition-colors',
                  isActive ? 'text-emerald-600' : 'text-slate-600 hover:text-emerald-600',
                )
              }
            >
              首页
            </NavLink>
            <NavLink
              to="/history"
              className={({ isActive }) =>
                cn(
                  'text-sm font-medium transition-colors',
                  isActive ? 'text-emerald-600' : 'text-slate-600 hover:text-emerald-600',
                )
              }
            >
              历史记录
            </NavLink>
          </div>

          <NavLink
            to="/profile"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-200 text-sm font-semibold text-slate-600 transition-all hover:ring-2 hover:ring-emerald-500 hover:ring-offset-2"
          >
            {userInitial}
          </NavLink>
        </div>
      </nav>

      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-6 py-8 md:py-10">
        <Outlet />
      </main>
    </div>
  );
}
