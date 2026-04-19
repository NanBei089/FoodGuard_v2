/** 后端统一 API 响应结构。 */
export interface ApiResponse<T = any> {
  code: number;
  message: string;
  data: T;
}

/** 后端字段级校验错误项。 */
export interface ApiValidationErrorItem {
  field: string;
  message: string;
  type: string;
}

/** 后端字段级校验错误集合。 */
export interface ApiValidationErrorData {
  errors?: ApiValidationErrorItem[];
}

/** 后端分页响应结构。 */
export interface PageResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
