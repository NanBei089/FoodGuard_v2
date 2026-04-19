import type { ApiResponse, ApiValidationErrorData } from '@/types/api';

/** 表单字段到错误消息的映射。 */
export type FieldErrorMap = Partial<Record<string, string>>;

function isRecord(value: unknown): value is Record<string, unknown> {
  /** 判断未知值是否为普通对象。 */
  return typeof value === 'object' && value !== null;
}

function getValidationErrors(payload: unknown) {
  /** 从统一 API 错误响应中提取字段级校验错误。 */
  if (!isRecord(payload)) {
    return [];
  }

  const data = payload.data;
  if (!isRecord(data) || !Array.isArray(data.errors)) {
    return [];
  }

  return data.errors;
}

export function extractApiErrorDetails(
  payload: unknown,
  fallbackMessage = '请求失败',
): {
  message: string;
  fieldErrors: FieldErrorMap;
} {
  /** 统一抽取接口错误的页面级消息和字段级消息。 */
  const response = (isRecord(payload) ? payload : {}) as Partial<ApiResponse<ApiValidationErrorData>>;
  const validationErrors = getValidationErrors(payload);
  const fieldErrors: FieldErrorMap = {};

  for (const item of validationErrors) {
    if (!isRecord(item)) {
      continue;
    }

    const field = typeof item.field === 'string' ? item.field : '';
    const message = typeof item.message === 'string' ? item.message : '';
    if (!field || !message || fieldErrors[field]) {
      continue;
    }
    fieldErrors[field] = message;
  }

  const responseMessage =
    typeof response.message === 'string' && response.message.trim()
      ? response.message.trim()
      : '';
  const fieldMessage = Object.values(fieldErrors)[0];

  return {
    message: responseMessage || fieldMessage || fallbackMessage,
    fieldErrors,
  };
}

