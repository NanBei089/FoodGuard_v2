import type { ApiResponse, ApiValidationErrorData } from '@/types/api';

export type FieldErrorMap = Partial<Record<string, string>>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function getValidationErrors(payload: unknown) {
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

