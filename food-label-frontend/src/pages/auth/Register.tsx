import { useEffect, useState } from 'react';
import { AtSign, BadgeCheck, LockKeyhole } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { apiClient } from '@/api/client';
import {
  fetchSessionContext,
  needsOnboarding,
  persistTokens,
} from '@/lib/auth-session';
import { extractApiErrorDetails } from '@/lib/api-errors';
import { useAuthStore } from '@/store/auth';
import type { ApiResponse } from '@/types/api';
import type { TokenResponse } from '@/types/auth';

export default function Register() {
  const navigate = useNavigate();
  const setSession = useAuthStore((state) => state.setSession);
  const logout = useAuthStore((state) => state.logout);
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [cooldown, setCooldown] = useState(0);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<string, string>>>({});

  const clearErrors = () => {
    setError('');
    setFieldErrors({});
  };

  const clearFieldError = (field: string) => {
    setError('');
    setFieldErrors((current) => {
      if (!current[field]) {
        return current;
      }

      const next = { ...current };
      delete next[field];
      return next;
    });
  };

  const inferFieldFromMessage = (message: string) => {
    if (message.includes('验证码')) {
      return 'code';
    }
    if (message.includes('邮箱')) {
      return 'email';
    }
    if (message.includes('密码')) {
      return 'password';
    }
    return undefined;
  };

  const applyApiError = (payload: unknown, fallbackMessage: string, fallbackField?: string) => {
    const nextError = extractApiErrorDetails(payload, fallbackMessage);
    const inferredField = fallbackField || inferFieldFromMessage(nextError.message);

    if (Object.keys(nextError.fieldErrors).length > 0) {
      setFieldErrors(nextError.fieldErrors);
    } else if (inferredField) {
      setFieldErrors({ [inferredField]: nextError.message });
    } else {
      setFieldErrors({});
    }

    setError(nextError.message);
  };

  useEffect(() => {
    if (cooldown <= 0) {
      return;
    }

    const timer = window.setTimeout(() => {
      setCooldown((current) => current - 1);
    }, 1000);

    return () => window.clearTimeout(timer);
  }, [cooldown]);

  const handleSendCode = async () => {
    if (!email.trim()) {
      setError('请先输入邮箱');
      setFieldErrors({ email: '请先输入邮箱' });
      return;
    }

    clearErrors();

    try {
      const res = await apiClient.post<any, ApiResponse<{ cooldown_seconds: number }>>(
        '/auth/register/send-code',
        { email },
      );

      if (res.code !== 0) {
        applyApiError(res, '发送验证码失败', 'email');
        return;
      }

      setCooldown(res.data.cooldown_seconds || 60);
    } catch (err: any) {
      applyApiError(err.response?.data, '发送验证码失败', 'email');
    }
  };

  const handleRegister = async (event: React.FormEvent) => {
    event.preventDefault();
    clearErrors();

    if (password !== confirmPassword) {
      setError('两次输入的密码不一致');
      setFieldErrors({ confirmPassword: '两次输入的密码不一致' });
      return;
    }

    setLoading(true);

    try {
      const registerRes = await apiClient.post<any, ApiResponse<null>>('/auth/register', {
        email,
        code,
        password,
      });

      if (registerRes.code !== 0) {
        applyApiError(registerRes, '注册失败');
        return;
      }

      const loginRes = await apiClient.post<any, ApiResponse<TokenResponse>>('/auth/login', {
        email,
        password,
      });

      if (loginRes.code !== 0) {
        throw new Error(loginRes.message || '注册成功，但自动登录失败');
      }

      persistTokens(loginRes.data);
      const { user, preferences } = await fetchSessionContext();
      setSession(user, preferences);
      navigate(needsOnboarding(user, preferences) ? '/onboarding' : '/');
    } catch (err: any) {
      logout();
      applyApiError(err.response?.data, err.message || '注册请求失败');
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
              d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"
            />
          </svg>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">创建你的账号</h1>
        <p className="mt-2 text-sm text-slate-500">加入 FoodGuard，让每一张配料表都更透明可读。</p>
      </div>

      <div className="soft-panel rounded-[28px] p-8">
        {error && (
          <div className="mb-5 rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-600">
            {error}
          </div>
        )}

        <form onSubmit={handleRegister} className="space-y-5">
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">邮箱账号</label>
            <div className="relative">
              <AtSign className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
              <Input
                type="email"
                value={email}
                onChange={(event) => {
                  setEmail(event.target.value);
                  clearFieldError('email');
                }}
                placeholder="请输入常用邮箱"
                className="bg-slate-50 pl-10 focus:bg-white"
                error={fieldErrors.email}
                required
              />
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">邮箱验证码</label>
            <div className="flex gap-3">
              <div className="relative flex-1">
                <BadgeCheck className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
                <Input
                  type="text"
                  value={code}
                  onChange={(event) => {
                    setCode(event.target.value);
                    clearFieldError('code');
                  }}
                  placeholder="请输入 6 位验证码"
                  className="bg-slate-50 pl-10 focus:bg-white"
                  maxLength={6}
                  error={fieldErrors.code}
                  required
                />
              </div>
              <Button
                type="button"
                variant="outline"
                className="h-11 whitespace-nowrap px-4"
                disabled={cooldown > 0}
                onClick={handleSendCode}
              >
                {cooldown > 0 ? `${cooldown}s 后重试` : '获取验证码'}
              </Button>
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">设置密码</label>
            <div className="relative">
              <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
              <Input
                type="password"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                  clearFieldError('password');
                }}
                placeholder="8-32 位，需包含大写字母、小写字母和数字"
                className="bg-slate-50 pl-10 focus:bg-white"
                error={fieldErrors.password}
                required
              />
            </div>
            <p className="mt-2 text-xs text-slate-500">密码需为 8-32 位，并同时包含大写字母、小写字母和数字。</p>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">确认密码</label>
            <div className="relative">
              <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
              <Input
                type="password"
                value={confirmPassword}
                onChange={(event) => {
                  setConfirmPassword(event.target.value);
                  clearFieldError('confirmPassword');
                }}
                placeholder="请再次输入密码"
                className="bg-slate-50 pl-10 focus:bg-white"
                error={fieldErrors.confirmPassword}
                required
              />
            </div>
          </div>

          <Button
            type="submit"
            size="lg"
            className="mt-2 w-full rounded-xl bg-emerald-500 hover:bg-emerald-600"
            isLoading={loading}
          >
            立即注册
          </Button>
        </form>

        <div className="relative mb-6 mt-8">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-slate-200" />
          </div>
          <div className="relative flex justify-center text-sm font-medium">
            <span className="bg-white px-4 text-slate-400">已经有账号？</span>
          </div>
        </div>

        <Link
          to="/login"
          className="inline-flex w-full justify-center rounded-xl bg-slate-900 px-4 py-3.5 font-semibold text-white shadow-sm transition hover:bg-slate-800"
        >
          返回登录
        </Link>
      </div>

      <div className="mt-8 text-center text-xs text-slate-500">
        注册即代表你同意我们的{' '}
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
