export interface ApiResponse<T = any> {
  code: number;
  message: string;
  data: T;
}

export interface ApiValidationErrorItem {
  field: string;
  message: string;
  type: string;
}

export interface ApiValidationErrorData {
  errors?: ApiValidationErrorItem[];
}

export interface PageResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
