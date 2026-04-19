/** 当前登录用户资料。 */
export interface User {
  user_id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  is_verified: boolean;
  created_at: string;
}

/** 用户健康偏好。 */
export interface UserPreferences {
  focus_groups: string[];
  health_conditions: string[];
  allergies: string[];
  updated_at: string;
}

/** 登录或刷新 token 的响应数据。 */
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}
