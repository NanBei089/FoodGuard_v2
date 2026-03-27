import { apiClient } from '@/api/client';
import type { ApiResponse } from '@/types/api';
import type { TokenResponse, User, UserPreferences } from '@/types/auth';

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
  if (!user || !preferences) {
    return false;
  }

  return !user.display_name?.trim() || preferences.focus_groups.length === 0;
};

export const persistTokens = (tokens: TokenResponse): void => {
  localStorage.setItem('access_token', tokens.access_token);
  localStorage.setItem('refresh_token', tokens.refresh_token);
};

export const clearPersistedTokens = (): void => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
};

export async function fetchSessionContext(): Promise<{
  user: User;
  preferences: UserPreferences;
}> {
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

