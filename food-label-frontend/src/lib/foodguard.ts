import type { User } from '@/types/auth';

export const focusGroupLabels = {
  adult: '自己 / 成年人',
  child: '儿童',
  elder: '老年人',
  pregnant: '孕妇',
  fitness: '健身 / 减脂',
} as const;

export const healthConditionLabels = {
  diabetes: '糖尿病 / 控糖',
  hypertension: '高血压 / 控钠',
  hyperuricemia: '高尿酸 / 痛风',
  allergy: '食物过敏',
} as const;

export const healthConditionDescriptions: Record<string, string> = {
  diabetes: '重点提示添加糖、隐形糖和高升糖风险配料。',
  hypertension: '重点计算钠含量占比并高亮高盐调味成分。',
  hyperuricemia: '优先排查高嘌呤和易诱发尿酸升高的食材。',
  allergy: '会优先标记与你过敏源相关的致敏成分。',
};

export function getUserInitial(user: Pick<User, 'display_name' | 'email'> | null): string {
  const raw = user?.display_name?.trim() || user?.email?.trim() || '';
  return raw.charAt(0).toUpperCase();
}

export function getScorePalette(score: number) {
  if (score >= 80) {
    return {
      text: 'text-emerald-600',
      ring: '#10b981',
      badge: '健康安全',
      badgeClass: 'bg-emerald-100 text-emerald-800',
      surfaceClass: 'from-emerald-50 to-white border-emerald-200',
      accentClass: 'bg-emerald-500',
    };
  }

  if (score >= 60) {
    return {
      text: 'text-amber-600',
      ring: '#f59e0b',
      badge: '中低风险',
      badgeClass: 'bg-amber-100 text-amber-800',
      surfaceClass: 'from-amber-50 to-white border-amber-200',
      accentClass: 'bg-amber-500',
    };
  }

  return {
    text: 'text-rose-600',
    ring: '#f43f5e',
    badge: '高风险',
    badgeClass: 'bg-rose-100 text-rose-800',
    surfaceClass: 'from-rose-50 to-white border-rose-200',
    accentClass: 'bg-rose-500',
  };
}

export function scoreRingOffset(score: number): number {
  const normalizedScore = Math.max(0, Math.min(score, 100));
  const circumference = 283;
  return circumference - (normalizedScore / 100) * circumference;
}

export function getHazardLevelLabel(level: string): string {
  if (level === 'high') {
    return '高风险';
  }
  if (level === 'medium') {
    return '中风险';
  }
  return '低风险';
}

export function getIngredientRiskMeta(risk: string) {
  if (risk === 'danger') {
    return {
      label: '高风险',
      chipClass: 'bg-rose-500 text-white',
      cardClass: 'bg-rose-50 border-rose-100',
      dotClass: 'bg-rose-500',
    };
  }

  if (risk === 'warning') {
    return {
      label: '中风险',
      chipClass: 'bg-amber-500 text-white',
      cardClass: 'bg-amber-50 border-amber-100',
      dotClass: 'bg-amber-500',
    };
  }

  return {
    label: '安全',
    chipClass: 'bg-emerald-500 text-white',
    cardClass: 'bg-emerald-50 border-emerald-100',
    dotClass: 'bg-emerald-500',
  };
}

export function formatReportDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function normalizeNutritionEntries(nutrition: Record<string, unknown> | null | undefined) {
  return Object.entries(nutrition ?? {}).filter(([, value]) => {
    if (value === null || value === undefined) {
      return false;
    }
    return String(value).trim().length > 0;
  });
}

export function getNutritionParseSourceLabel(source: string | null | undefined): string {
  if (source === 'table_recognition') {
    return '表格识别';
  }
  if (source === 'ocr_text') {
    return 'OCR 文本提取';
  }
  if (source === 'llm_fallback') {
    return '大模型补全';
  }
  return '未识别';
}

export function getNutritionLevelMeta(level: string) {
  if (level === 'warning') {
    return {
      badgeClass: 'bg-rose-100 text-rose-600',
      amountClass: 'text-rose-500',
      recommendationClass: 'text-rose-500',
      rowClass: 'bg-rose-50/50',
    };
  }

  if (level === 'attention') {
    return {
      badgeClass: 'bg-amber-100 text-amber-600',
      amountClass: 'text-amber-600',
      recommendationClass: 'text-amber-600',
      rowClass: 'bg-white',
    };
  }

  if (level === 'good') {
    return {
      badgeClass: 'bg-emerald-100 text-emerald-600',
      amountClass: 'text-slate-900',
      recommendationClass: 'text-emerald-600',
      rowClass: 'bg-white',
    };
  }

  return {
    badgeClass: 'bg-slate-100 text-slate-500',
    amountClass: 'text-slate-900',
    recommendationClass: 'text-slate-500',
    rowClass: 'bg-white',
  };
}

export function summarizePreferences(
  focusGroups: string[] = [],
  healthConditions: string[] = [],
  allergies: string[] = [],
) {
  return {
    focusGroups: focusGroups.map((item) => focusGroupLabels[item as keyof typeof focusGroupLabels] ?? item),
    healthConditions: healthConditions.map(
      (item) => healthConditionLabels[item as keyof typeof healthConditionLabels] ?? item,
    ),
    allergies,
  };
}
