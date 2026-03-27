import { create } from 'zustand';
import { needsOnboarding } from '@/lib/auth-session';
import type { User, UserPreferences } from '@/types/auth';

const USER_STORAGE_KEY = 'foodguard_user';
const PREFERENCES_STORAGE_KEY = 'foodguard_preferences';

function readPersistedValue<T>(key: string): T | null {
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
