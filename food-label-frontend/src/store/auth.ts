import { create } from 'zustand';
import { needsOnboarding } from '@/lib/auth-session';
import type { User, UserPreferences } from '@/types/auth';

/** 鉴权与偏好在 localStorage 中的持久化 key。 */
const USER_STORAGE_KEY = 'foodguard_user';
const PREFERENCES_STORAGE_KEY = 'foodguard_preferences';

function readPersistedValue<T>(key: string): T | null {
  /** 读取并解析持久化状态；坏数据直接清理，避免污染后续状态恢复。 */
  const raw = localStorage.getItem(key);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as T;
  } catch {
    localStorage.removeItem(key);
    return null;
  }
}

function persistValue(key: string, value: unknown): void {
  /** 统一处理状态持久化和删除逻辑。 */
  if (value === null) {
    localStorage.removeItem(key);
    return;
  }

  localStorage.setItem(key, JSON.stringify(value));
}

const persistedUser = readPersistedValue<User>(USER_STORAGE_KEY);
const persistedPreferences = readPersistedValue<UserPreferences>(PREFERENCES_STORAGE_KEY);

interface AuthState {
  user: User | null;
  preferences: UserPreferences | null;
  isAuthenticated: boolean;
  needsOnboarding: boolean;
  setSession: (user: User, preferences: UserPreferences) => void;
  setUser: (user: User | null) => void;
  setPreferences: (preferences: UserPreferences | null) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: persistedUser,
  preferences: persistedPreferences,
  isAuthenticated: !!localStorage.getItem('access_token'),
  needsOnboarding: needsOnboarding(persistedUser, persistedPreferences),
  setSession: (user, preferences) =>
    set(() => {
      persistValue(USER_STORAGE_KEY, user);
      persistValue(PREFERENCES_STORAGE_KEY, preferences);
      return {
        user,
        preferences,
        isAuthenticated: true,
        needsOnboarding: needsOnboarding(user, preferences),
      };
    }),
  setUser: (user) =>
    set((state) => {
      persistValue(USER_STORAGE_KEY, user);
      return {
        user,
        // access token 可能仍然存在，因此这里不能仅根据 user 是否为空判断鉴权状态。
        isAuthenticated: !!user || !!localStorage.getItem('access_token'),
        needsOnboarding: needsOnboarding(user, state.preferences),
      };
    }),
  setPreferences: (preferences) =>
    set((state) => {
      persistValue(PREFERENCES_STORAGE_KEY, preferences);
      return {
        preferences,
        needsOnboarding: needsOnboarding(state.user, preferences),
      };
    }),
  logout: () => {
    // 登出时同步清空 token 和缓存资料，避免后续会话恢复读到旧数据。
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem(USER_STORAGE_KEY);
    localStorage.removeItem(PREFERENCES_STORAGE_KEY);
    set({
      user: null,
      preferences: null,
      isAuthenticated: false,
      needsOnboarding: false,
    });
  },
}));
