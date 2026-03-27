import { useState } from 'react';
import { AtSign, LockKeyhole } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { apiClient } from '@/api/client';
import {
  fetchSessionContext,
  needsOnboarding,
  persistTokens,
} from '@/lib/auth-session';
import { useAuthStore } from '@/store/auth';
import type { ApiResponse } from '@/types/api';
import type { TokenResponse } from '@/types/auth';

export default function Login() {
  const navigate = useNavigate();
  const setSession = useAuthStore((state) => state.setSession);
  const logout = useAuthStore((state) => state.logout);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError('');

    try {
      const res = await apiClient.post<any, ApiResponse<TokenResponse>>('/auth/login', {
        email,
        password,
      });

      if (res.code !== 0) {
        setError(res.message || '登录失败');
        return;
      }

      persistTokens(res.data);
      const { user, preferences } = await fetchSessionContext();
      setSession(user, preferences);
      navigate(needsOnboarding(user, preferences) ? '/onboarding' : '/');
    } catch (err: any) {
      logout();
      setError(err.response?.data?.message || '登录请求失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="mb-8 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400 to-emerald-600 shadow-lg shadow-emerald-500/30">
          <svg className="h-8 w-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
            />
          </svg>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">欢迎回来</h1>
        <p className="mt-2 text-sm text-slate-500">登录 FoodGuard，继续你的食品标签健康分析。</p>
      </div>

      <div className="soft-panel rounded-[28px] p-8">
        {error && (
          <div className="mb-5 rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-600">
            {error}
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-5">
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">邮箱账号</label>
            <div className="relative">
              <AtSign className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
              <Input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="请输入你的邮箱"
                className="bg-slate-50 pl-10 focus:bg-white"
                required
              />
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">密码</label>
            <div className="relative">
              <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
              <Input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="请输入密码"
                className="bg-slate-50 pl-10 focus:bg-white"
                required
              />
            </div>
          </div>

          <Button
            type="submit"
            size="lg"
            className="mt-2 w-full rounded-xl bg-slate-900 hover:bg-slate-800"
            isLoading={loading}
          >
            登录
          </Button>
        </form>

        <div className="relative mb-6 mt-8">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-slate-200" />
          </div>
          <div className="relative flex justify-center text-sm font-medium">
            <span className="bg-white px-4 text-slate-400">还没有账号？</span>
          </div>
        </div>

        <Link
          to="/register"
          className="inline-flex w-full justify-center rounded-xl border border-slate-200 bg-white px-4 py-3.5 font-semibold text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
        >
          注册新账号
        </Link>
      </div>

      <div className="mt-8 text-center text-xs text-slate-500">
        登录即代表你同意我们的{' '}
        <a href="#" className="text-emerald-600 hover:underline">
          服务条款
        </a>{' '}
        和{' '}
        <a href="#" className="text-emerald-600 hover:underline">
          隐私政策
        </a>
      </div>
    </>
  );
}
