import { apiClient } from '@/api/client';
import type { ApiResponse } from '@/types/api';
import type { TokenResponse, User, UserPreferences } from '@/types/auth';

/** 生成一个空偏好对象，作为新用户或异常兜底时的默认值。 */
export const emptyPreferences = (): UserPreferences => ({
  focus_groups: [],
  health_conditions: [],
  allergies: [],
  updated_at: new Date().toISOString(),
});

export const needsOnboarding = (
  user: User | null,
  preferences: UserPreferences | null,
): boolean => {
  /** 判断是否仍需进入 onboarding，标准是昵称和关注人群至少完成基础配置。 */
  if (!user || !preferences) {
    return false;
  }

  return !user.display_name?.trim() || preferences.focus_groups.length === 0;
};

export const persistTokens = (tokens: TokenResponse): void => {
  /** 持久化 access/refresh token。 */
  localStorage.setItem('access_token', tokens.access_token);
  localStorage.setItem('refresh_token', tokens.refresh_token);
};

export const clearPersistedTokens = (): void => {
  /** 清理本地 token。 */
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
};

export async function fetchSessionContext(): Promise<{
  user: User;
  preferences: UserPreferences;
}> {
  /** 并行拉取用户资料与偏好，用于页面刷新后的会话恢复。 */
  const [userRes, preferenceRes] = await Promise.all([
    apiClient.get<any, ApiResponse<User>>('/users/me'),
    apiClient.get<any, ApiResponse<UserPreferences>>('/preferences/me'),
  ]);

  if (userRes.code !== 0) {
    throw new Error(userRes.message || 'Failed to load user profile');
  }

  if (preferenceRes.code !== 0) {
    throw new Error(preferenceRes.message || 'Failed to load user preferences');
  }

  return {
    user: userRes.data,
    preferences: preferenceRes.data ?? emptyPreferences(),
  };
}

