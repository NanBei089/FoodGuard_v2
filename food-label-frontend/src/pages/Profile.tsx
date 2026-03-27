import { useEffect, useState } from 'react';
import { LockKeyhole, ShieldCheck, UserRound } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { apiClient } from '@/api/client';
import { clearPersistedTokens } from '@/lib/auth-session';
import { extractApiErrorDetails } from '@/lib/api-errors';
import { getUserInitial, healthConditionDescriptions, healthConditionLabels } from '@/lib/foodguard';
import { useAuthStore } from '@/store/auth';
import type { ApiResponse, PageResponse } from '@/types/api';
import type { User, UserPreferences } from '@/types/auth';

interface ReportListMeta {
  total: number;
}

const focusGroupOptions = [
  { id: 'adult', label: '自己 / 成年人' },
  { id: 'child', label: '儿童' },
  { id: 'elder', label: '老年人' },
  { id: 'pregnant', label: '孕妇' },
  { id: 'fitness', label: '健身 / 减脂' },
];

const healthConditionOptions = [
  { id: 'diabetes', label: '糖尿病 / 控糖' },
  { id: 'hypertension', label: '高血压 / 控钠' },
  { id: 'hyperuricemia', label: '高尿酸 / 痛风' },
];

export default function Profile() {
  const navigate = useNavigate();
  const { user, setUser, preferences: storePreferences, setPreferences, logout } = useAuthStore();
  const [displayName, setDisplayName] = useState(user?.display_name || '');
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileMessage, setProfileMessage] = useState('');
  const [totalReports, setTotalReports] = useState(0);
  const [preferences, setLocalPreferences] = useState<UserPreferences>(
    storePreferences ?? {
      focus_groups: [],
      health_conditions: [],
      allergies: [],
      updated_at: new Date().toISOString(),
    },
  );
  const [allergyInput, setAllergyInput] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState('');
  const [passwordErrors, setPasswordErrors] = useState<Partial<Record<string, string>>>({});

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [userRes, prefRes, reportRes] = await Promise.all([
          apiClient.get<any, ApiResponse<User>>('/users/me'),
          apiClient.get<any, ApiResponse<UserPreferences>>('/preferences/me').catch(() => null),
          apiClient
            .get<any, ApiResponse<PageResponse<unknown>>>('/reports?page=1&page_size=1')
            .catch(() => null),
        ]);

        if (userRes.code === 0) {
          setUser(userRes.data);
          setDisplayName(userRes.data.display_name || '');
        }

        if (prefRes?.code === 0) {
          setLocalPreferences(prefRes.data);
          setPreferences(prefRes.data);
        }

        if (reportRes?.code === 0) {
          const metadata = reportRes.data as ReportListMeta;
          setTotalReports(metadata.total || 0);
        }
      } catch (err) {
        console.error(err);
      }
    };

    fetchData();
  }, [setPreferences, setUser]);

  const toggleArrayItem = (key: 'focus_groups' | 'health_conditions', value: string) => {
    setLocalPreferences((current) => {
      const items = current[key];
      return {
        ...current,
        [key]: items.includes(value) ? items.filter((item) => item !== value) : [...items, value],
      };
    });
  };

  const toggleAllergyCondition = () => {
    setLocalPreferences((current) => {
      const hasAllergy = current.health_conditions.includes('allergy');
      return {
        ...current,
        health_conditions: hasAllergy
          ? current.health_conditions.filter((item) => item !== 'allergy')
          : [...current.health_conditions, 'allergy'],
        allergies: hasAllergy ? [] : current.allergies,
      };
    });
  };

  const addAllergy = () => {
    const nextItem = allergyInput.trim();
    if (!nextItem || preferences.allergies.includes(nextItem)) {
      return;
    }

    setLocalPreferences((current) => ({
      ...current,
      allergies: [...current.allergies, nextItem],
      health_conditions: current.health_conditions.includes('allergy')
        ? current.health_conditions
        : [...current.health_conditions, 'allergy'],
    }));
    setAllergyInput('');
  };

  const removeAllergy = (item: string) => {
    setLocalPreferences((current) => ({
      ...current,
      allergies: current.allergies.filter((entry) => entry !== item),
    }));
  };

  const handleSave = async () => {
    setSavingProfile(true);
    setProfileMessage('');

    try {
      const [userRes, prefRes] = await Promise.all([
        apiClient.patch<any, ApiResponse<User>>('/users/me', {
          display_name: displayName.trim(),
        }),
        apiClient.put<any, ApiResponse<UserPreferences>>('/preferences/me', {
          focus_groups: preferences.focus_groups,
          health_conditions: preferences.health_conditions,
          allergies: preferences.allergies,
        }),
      ]);

      if (userRes.code !== 0) {
        throw new Error(userRes.message || '保存资料失败');
      }

      if (prefRes.code !== 0) {
        throw new Error(prefRes.message || '保存偏好失败');
      }

      setUser(userRes.data);
      setPreferences(prefRes.data);
      setProfileMessage('保存成功');
    } catch (err: any) {
      setProfileMessage(err.response?.data?.message || err.message || '网络请求失败');
    } finally {
      setSavingProfile(false);
    }
  };

  const clearPasswordFieldError = (field: string) => {
    setPasswordMessage('');
    setPasswordErrors((current) => {
      if (!current[field]) {
        return current;
      }
      const next = { ...current };
      delete next[field];
      return next;
    });
  };

  const handleChangePassword = async (event: React.FormEvent) => {
    event.preventDefault();
    setPasswordMessage('');
    setPasswordErrors({});

    if (newPassword !== confirmNewPassword) {
      setPasswordMessage('两次输入的新密码不一致');
      setPasswordErrors({ confirmNewPassword: '两次输入的新密码不一致' });
      return;
    }

    setChangingPassword(true);

    try {
      const res = await apiClient.post<any, ApiResponse<null>>('/users/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      });

      if (res.code !== 0) {
        throw new Error(res.message || '修改密码失败');
      }

      setCurrentPassword('');
      setNewPassword('');
      setConfirmNewPassword('');
      setPasswordErrors({});
      setPasswordMessage('密码修改成功');
    } catch (err: any) {
      const { message, fieldErrors } = extractApiErrorDetails(
        err.response?.data,
        err.message || '修改密码失败',
      );
      if (Object.keys(fieldErrors).length === 0 && message.includes('当前密码')) {
        setPasswordErrors({ current_password: message });
      } else {
        setPasswordErrors(fieldErrors);
      }
      setPasswordMessage(message);
    } finally {
      setChangingPassword(false);
    }
  };

  const handleLogout = () => {
    clearPersistedTokens();
    logout();
    navigate('/login');
  };

  const hasAllergyCondition = preferences.health_conditions.includes('allergy');
  const activePreferenceCount =
    preferences.focus_groups.length + preferences.health_conditions.length + preferences.allergies.length;

  return (
    <div className="flex w-full flex-col gap-8 md:flex-row">
      <aside className="flex w-full flex-col gap-6 md:w-80">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm">
          <div className="group relative mx-auto mb-4 flex h-24 w-24 items-center justify-center rounded-full border-4 border-white bg-gradient-to-br from-emerald-100 to-teal-100 shadow-md">
            <span className="text-3xl font-bold text-emerald-600">{getUserInitial(user)}</span>
          </div>
          <h2 className="mb-1 text-xl font-bold text-slate-900">{displayName || '未设置昵称'}</h2>
          <p className="text-sm text-slate-500">{user?.email || ''}</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="mb-4 font-bold text-slate-900">使用数据</h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-xl bg-slate-50 p-4 text-center">
              <div className="mb-1 text-2xl font-bold text-slate-900">{totalReports}</div>
              <div className="text-xs text-slate-500">累计分析</div>
            </div>
            <div className="rounded-xl bg-slate-50 p-4 text-center">
              <div className="mb-1 text-2xl font-bold text-emerald-600">{activePreferenceCount}</div>
              <div className="text-xs text-slate-500">已设偏好</div>
            </div>
          </div>
        </div>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 bg-slate-50/60 p-5">
            <h2 className="flex items-center gap-2 text-base font-bold text-slate-900">
              <ShieldCheck className="h-4 w-4 text-slate-500" />
              账号安全与操作
            </h2>
          </div>
          <div className="space-y-5 p-5">
            <div>
              <h3 className="mb-1 text-sm font-semibold text-slate-900">修改密码</h3>
              <p className="mb-3 text-xs text-slate-500">修改后会立即更新账号密码，后续登录请使用新密码。</p>
              <form className="space-y-3" onSubmit={handleChangePassword}>
                {passwordMessage && (
                  <div
                    className={`rounded-xl px-3 py-2 text-sm ${
                      passwordMessage.includes('成功')
                        ? 'border border-emerald-100 bg-emerald-50 text-emerald-700'
                        : 'border border-rose-100 bg-rose-50 text-rose-600'
                    }`}
                  >
                    {passwordMessage}
                  </div>
                )}

                <div>
                  <label className="mb-2 block text-xs font-medium text-slate-600">当前密码</label>
                  <div className="relative">
                    <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <Input
                      type="password"
                      value={currentPassword}
                      onChange={(event) => {
                        setCurrentPassword(event.target.value);
                        clearPasswordFieldError('current_password');
                      }}
                      placeholder="请输入当前密码"
                      className="bg-slate-50 pl-10 focus:bg-white"
                      error={passwordErrors.current_password}
                      required
                    />
                  </div>
                </div>

                <div>
                  <label className="mb-2 block text-xs font-medium text-slate-600">新密码</label>
                  <div className="relative">
                    <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <Input
                      type="password"
                      value={newPassword}
                      onChange={(event) => {
                        setNewPassword(event.target.value);
                        clearPasswordFieldError('new_password');
                      }}
                      placeholder="8-32 位，需包含大写字母、小写字母和数字"
                      className="bg-slate-50 pl-10 focus:bg-white"
                      error={passwordErrors.new_password}
                      required
                    />
                  </div>
                </div>

                <div>
                  <label className="mb-2 block text-xs font-medium text-slate-600">确认新密码</label>
                  <div className="relative">
                    <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <Input
                      type="password"
                      value={confirmNewPassword}
                      onChange={(event) => {
                        setConfirmNewPassword(event.target.value);
                        clearPasswordFieldError('confirmNewPassword');
                      }}
                      placeholder="请再次输入新密码"
                      className="bg-slate-50 pl-10 focus:bg-white"
                      error={passwordErrors.confirmNewPassword}
                      required
                    />
                  </div>
                </div>

                <p className="text-[11px] leading-relaxed text-slate-500">
                  新密码需为 8-32 位，并同时包含大写字母、小写字母和数字。
                </p>

                <Button type="submit" isLoading={changingPassword} className="w-full bg-slate-900 hover:bg-slate-800">
                  修改密码
                </Button>
              </form>
            </div>

            <div className="h-px bg-slate-100" />

            <div>
              <h3 className="mb-1 text-sm font-semibold text-slate-900">退出登录</h3>
              <p className="mb-3 text-xs text-slate-500">退出当前设备上的 FoodGuard 登录状态。</p>
              <button
                type="button"
                onClick={handleLogout}
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
              >
                退出登录
              </button>
            </div>

            <div className="h-px bg-slate-100" />

            <div>
              <h3 className="mb-1 text-sm font-semibold text-rose-600">注销账号</h3>
              <p className="mb-3 text-xs text-slate-500">危险操作，当前前端暂不直接暴露。</p>
              <button
                type="button"
                disabled
                className="w-full rounded-xl border border-rose-100 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-300"
              >
                暂未开放
              </button>
            </div>
          </div>
        </div>
      </aside>

      <section className="flex-1 space-y-6">
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 bg-slate-50/60 p-6">
            <h2 className="flex items-center gap-2 text-lg font-bold text-slate-900">
              <UserRound className="h-5 w-5 text-emerald-600" />
              账号设置
            </h2>
            <p className="mt-1 text-sm text-slate-500">管理你的基本资料与默认分析配置。</p>
          </div>
          <div className="space-y-6 p-6">
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">昵称</label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-900 transition-all focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">邮箱账号</label>
                <input
                  type="email"
                  value={user?.email || ''}
                  disabled
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-900"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/60 p-6">
            <div>
              <h2 className="text-lg font-bold text-slate-900">默认健康偏好</h2>
              <p className="mt-1 text-sm text-slate-500">这些设置会在每次分析时自动带入，作为个性化判断依据。</p>
            </div>
            <Button onClick={handleSave} isLoading={savingProfile} className="bg-emerald-500 hover:bg-emerald-600">
              保存修改
            </Button>
          </div>

          <div className="space-y-8 p-6">
            {profileMessage && (
              <div
                className={`rounded-xl px-4 py-3 text-sm ${
                  profileMessage.includes('成功')
                    ? 'border border-emerald-100 bg-emerald-50 text-emerald-700'
                    : 'border border-rose-100 bg-rose-50 text-rose-600'
                }`}
              >
                {profileMessage}
              </div>
            )}

            <div>
              <div className="mb-5 flex items-center gap-2">
                <div className="h-4 w-1.5 rounded-full bg-emerald-500" />
                <h3 className="text-base font-bold text-slate-800">常驻关注人群</h3>
                <span className="rounded border border-slate-200 bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
                  多选
                </span>
              </div>
              <div className="flex flex-wrap gap-3">
                {focusGroupOptions.map((item) => {
                  const checked = preferences.focus_groups.includes(item.id);
                  return (
                    <label key={item.id} className="cursor-pointer">
                      <input
                        type="checkbox"
                        className="peer sr-only"
                        checked={checked}
                        onChange={() => toggleArrayItem('focus_groups', item.id)}
                      />
                      <div
                        className={`flex items-center justify-center rounded-full border px-5 py-2.5 transition-all ${
                          checked
                            ? 'border-emerald-500 bg-emerald-500 text-white shadow-sm'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-emerald-300 hover:bg-emerald-50/30'
                        }`}
                      >
                        <span className="text-sm font-medium">{item.label}</span>
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>

            <div className="h-px bg-slate-100" />

            <div>
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-4 w-1.5 rounded-full bg-emerald-500" />
                  <h3 className="text-base font-bold text-slate-800">个人特殊健康状况</h3>
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-400">可多选</span>
                </div>
                <div className="rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                  已选 {preferences.health_conditions.length} 项
                </div>
              </div>

              <p className="mb-4 text-sm text-slate-500">用于在报告里优先突出与你相关的风险点和建议。</p>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {healthConditionOptions.map((item) => {
                  const checked = preferences.health_conditions.includes(item.id);
                  return (
                    <label key={item.id} className="block cursor-pointer rounded-2xl">
                      <input
                        type="checkbox"
                        className="peer sr-only"
                        checked={checked}
                        onChange={() => toggleArrayItem('health_conditions', item.id)}
                      />
                      <div
                        className={`flex h-full flex-col rounded-2xl border-2 p-5 transition-all ${
                          checked
                            ? 'border-emerald-500 bg-emerald-50/40'
                            : 'border-slate-200 bg-white hover:border-emerald-300'
                        }`}
                      >
                        <div className="mb-3 text-base font-bold text-slate-800">{item.label}</div>
                        <div className="text-[13px] leading-relaxed text-slate-500">
                          {healthConditionDescriptions[item.id]}
                        </div>
                      </div>
                    </label>
                  );
                })}

                <label className="block cursor-pointer rounded-2xl">
                  <input
                    type="checkbox"
                    className="peer sr-only"
                    checked={hasAllergyCondition}
                    onChange={toggleAllergyCondition}
                  />
                  <div
                    className={`flex h-full flex-col rounded-2xl border-2 p-5 transition-all ${
                      hasAllergyCondition
                        ? 'border-emerald-500 bg-emerald-50/40'
                        : 'border-slate-200 bg-white hover:border-emerald-300'
                    }`}
                  >
                    <div className="mb-3 text-base font-bold text-slate-800">{healthConditionLabels.allergy}</div>
                    <div className="text-[13px] leading-relaxed text-slate-500">
                      {healthConditionDescriptions.allergy}
                    </div>
                  </div>
                </label>
              </div>
            </div>

            {hasAllergyCondition && (
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6">
                <label className="mb-2 block text-sm font-bold text-slate-800">请填写你的食物过敏源</label>
                <p className="mb-4 text-xs text-slate-500">保存后，报告会优先标记这些成分。</p>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={allergyInput}
                    onChange={(event) => setAllergyInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        addAllergy();
                      }
                    }}
                    placeholder="例如：花生、牛奶、麸质、虾蟹"
                    className="flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20"
                  />
                  <Button type="button" onClick={addAllergy} className="bg-emerald-500 hover:bg-emerald-600">
                    添加
                  </Button>
                </div>

                {preferences.allergies.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {preferences.allergies.map((item) => (
                      <span
                        key={item}
                        className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700"
                      >
                        {item}
                        <button
                          type="button"
                          onClick={() => removeAllergy(item)}
                          className="ml-1 text-slate-400 transition-colors hover:text-rose-500"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
