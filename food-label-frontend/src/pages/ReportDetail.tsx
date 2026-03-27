import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  CheckCircle2,
  Info,
  ShieldAlert,
  Sparkles,
} from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { apiClient } from '@/api/client';
import {
  formatReportDate,
  getIngredientRiskMeta,
  getNutritionLevelMeta,
  getNutritionParseSourceLabel,
  getScorePalette,
  scoreRingOffset,
} from '@/lib/foodguard';
import { cn } from '@/lib/utils';
import type { ApiResponse } from '@/types/api';

interface IngredientAnalysisItem {
  name: string;
  risk: 'safe' | 'warning' | 'danger';
  description: string;
  function_category?: string | null;
  rules?: string[];
}

interface HealthAdviceItem {
  group: string;
  risk: 'safe' | 'warning' | 'danger';
  advice: string;
  hint: string;
}

interface ReportDetailData {
  report_id: string;
  task_id: string;
  image_url: string;
  ingredients_text: string;
  nutrition: Record<string, string> | null;
  nutrition_table: {
    title: string;
    subtitle: string | null;
    serving_basis: string | null;
    parse_source: string | null;
    rows: Array<{
      nutrient_key: string;
      name_cn: string;
      name_en: string | null;
      display_name: string;
      amount: string;
      nrv_percent: number | null;
      nrv_label: string | null;
      recommendation: string;
      level: 'good' | 'neutral' | 'attention' | 'warning';
      is_child: boolean;
      parent_key: string | null;
    }>;
    advice_title: string;
    advice_summary: string | null;
  } | null;
  nutrition_parse_source: string | null;
  analysis: {
    score: number;
    summary: string | null;
    hazards: Array<{ level: string; desc: string }>;
    benefits: string[];
    ingredients: IngredientAnalysisItem[];
    health_advice: HealthAdviceItem[];
  };
  rag_summary: {
    total_ingredients: number;
    retrieved_count: number;
    high_match_count: number;
    weak_match_count: number;
    empty_count: number;
  };
  created_at: string;
}

type ReportTab = 'ingredients' | 'nutrition' | 'advice';

export default function ReportDetail() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<ReportDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<ReportTab>('ingredients');

  useEffect(() => {
    if (!id) {
      return;
    }

    const fetchReport = async () => {
      try {
        const res = await apiClient.get<any, ApiResponse<ReportDetailData>>(`/reports/${id}`);
        if (res.code !== 0) {
          setError(res.message || '获取报告失败');
          return;
        }

        setReport(res.data);
      } catch (err: any) {
        setError(err.response?.data?.message || '请求失败');
      } finally {
        setLoading(false);
      }
    };

    fetchReport();
  }, [id]);

  if (loading) {
    return <div className="py-12 text-center">加载中...</div>;
  }

  if (error) {
    return <div className="py-12 text-center text-rose-500">{error}</div>;
  }

  if (!report) {
    return <div className="py-12 text-center">未找到报告</div>;
  }

  const score = report.analysis?.score || 0;
  const palette = getScorePalette(score);
  const nutritionTable = report.nutrition_table;
  const ingredients = report.analysis?.ingredients || [];
  const healthAdvice = report.analysis?.health_advice || [];
  const dangerCount = ingredients.filter((item) => item.risk === 'danger').length;
  const warningCount = ingredients.filter((item) => item.risk === 'warning').length;
  const safeCount = ingredients.filter((item) => item.risk === 'safe').length;
  const primaryHazard = report.analysis?.hazards[0];

  const tabs: Array<{ id: ReportTab; label: string }> = [
    { id: 'ingredients', label: '配料分析' },
    { id: 'nutrition', label: '营养成分' },
    { id: 'advice', label: '人群建议' },
  ];

  return (
    <div className="w-full">
      <div className="mb-6">
        <Link
          to="/history"
          className="inline-flex items-center gap-2 text-sm text-slate-500 transition-colors hover:text-emerald-600"
        >
          <ArrowLeft className="h-4 w-4" />
          返回列表
        </Link>
      </div>

      <div className="mb-8 rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="flex flex-col items-center gap-10 lg:flex-row">
          <div className="group relative h-56 w-full overflow-hidden rounded-2xl shadow-inner lg:w-72 lg:shrink-0">
            <div className="absolute inset-0 z-10 bg-gradient-to-t from-black/20 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
            {report.image_url ? (
              <img src={report.image_url} alt="上传标签原图" className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" />
            ) : (
              <div className="flex h-full items-center justify-center bg-slate-100 text-slate-400">暂无图片</div>
            )}
            <div className="absolute bottom-3 left-3 z-20 rounded-full bg-white/90 px-3 py-1 text-xs font-medium text-slate-700 shadow-sm backdrop-blur">
              创建于 {formatReportDate(report.created_at)}
            </div>
          </div>

          <div className="flex w-full flex-1 flex-col items-center gap-10 md:flex-row">
            <div className="group relative shrink-0 cursor-default">
              <div className="absolute inset-0 rounded-full bg-emerald-400/20 blur-2xl transition-colors duration-500 group-hover:bg-emerald-400/30" />
              <svg className="-rotate-90 relative z-10 h-48 w-48" viewBox="0 0 100 100">
                <circle
                  cx="50"
                  cy="50"
                  r="45"
                  fill="none"
                  stroke="#f1f5f9"
                  strokeWidth="8"
                  className="report-score-ring-track"
                />
                <circle
                  cx="50"
                  cy="50"
                  r="45"
                  fill="none"
                  stroke={palette.ring}
                  strokeWidth="8"
                  strokeLinecap="round"
                  strokeDashoffset={scoreRingOffset(score)}
                  className="report-score-ring drop-shadow-md"
                />
              </svg>
              <div className="absolute inset-0 z-20 flex flex-col items-center justify-center">
                <span className="text-6xl font-black tracking-tight text-slate-900">{score}</span>
                <span className="mt-1 text-sm font-medium uppercase tracking-[0.24em] text-slate-500">
                  综合健康分
                </span>
              </div>
            </div>

            <div className="grid w-full flex-1 grid-cols-2 gap-4">
              <MetricCard
                dotClass="bg-amber-500"
                label="需关注成分"
                value={dangerCount + warningCount}
                suffix="项"
                surfaceClass="from-slate-50 to-slate-100/50"
              />
              <MetricCard
                dotClass="bg-emerald-500"
                label="营养亮点"
                value={report.analysis?.benefits?.length || 0}
                suffix="项"
                surfaceClass="from-emerald-50 to-emerald-50/30"
              />
              <MetricCard
                dotClass="bg-blue-500"
                label="总配料数"
                value={report.rag_summary?.total_ingredients || ingredients.length}
                suffix="项"
                surfaceClass="from-slate-50 to-slate-100/50"
              />
              <MetricCard
                dotClass="bg-rose-500"
                label="高置信匹配"
                value={report.rag_summary?.high_match_count || 0}
                suffix="项"
                valueClass="text-rose-600"
                surfaceClass="from-rose-50 to-rose-50/30"
              />
            </div>
          </div>

          <div
            className={`flex h-full shrink-0 flex-col items-center justify-center gap-3 rounded-2xl border bg-gradient-to-b p-6 shadow-sm lg:w-48 ${palette.surfaceClass}`}
          >
            <div className="relative">
              <div className={`absolute inset-0 rounded-full blur opacity-30 ${palette.accentClass}`} />
              <div
                className={`relative z-10 flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br ${
                  score >= 80 ? 'from-emerald-400 to-emerald-600' : score >= 60 ? 'from-amber-400 to-amber-600' : 'from-rose-400 to-rose-600'
                } text-white shadow-lg`}
              >
                <ShieldAlert className="h-8 w-8" />
              </div>
            </div>
            <div className="text-center">
              <div className="mb-1 text-lg font-bold text-slate-900">{palette.badge}</div>
              <div className={`rounded-full px-2.5 py-1 text-xs font-medium ${palette.badgeClass}`}>
                {score >= 80 ? '可以放心选择' : score >= 60 ? '建议适量食用' : '建议谨慎购买'}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mb-8">
        <h3 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-900">
          <Sparkles className="h-5 w-5 text-emerald-500" />
          核心洞察
        </h3>

        <div className="rounded-2xl border-2 border-amber-200 bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-amber-100">
              <span className="text-2xl">⚠️</span>
            </div>
            <div>
              <div className="mb-2 inline-flex items-center gap-1.5 rounded-md bg-amber-100 px-2.5 py-1 text-xs font-bold text-amber-800">
                <div className="h-1.5 w-1.5 rounded-full bg-amber-600 animate-pulse" />
                需要重点留意
              </div>
              <h4 className="text-xl font-bold text-slate-900">
                {primaryHazard ? primaryHazard.desc : '本次报告已生成完整健康总结'}
              </h4>
            </div>
          </div>

          <p className="mb-4 text-sm leading-relaxed text-slate-600">
            {report.analysis?.summary || '当前报告暂无总结，建议结合详细成分分析继续查看。'}
          </p>

          <div className="flex items-start gap-2 rounded-xl border border-amber-100 bg-amber-50 p-3 text-sm text-amber-800">
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
            <p>
              <strong>行动建议：</strong>
              {primaryHazard
                ? `优先关注“${primaryHazard.desc}”，并结合下方风险项与人群建议判断是否适合长期购买。`
                : '可继续查看营养成分与配料明细，辅助判断是否适合你的日常饮食。'}
            </p>
          </div>
        </div>
      </div>

      <div className="mb-6 rounded-2xl border border-slate-200 bg-white">
        <div className="flex flex-wrap border-b border-slate-200">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                'px-6 py-4 text-sm font-medium transition-colors',
                activeTab === tab.id
                  ? 'tab-active'
                  : 'text-slate-500 hover:text-slate-700',
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-6">
          {activeTab === 'ingredients' && (
            <div className="space-y-6">
              <div className="rounded-xl bg-slate-50 p-5">
                <h4 className="mb-4 text-sm font-semibold text-slate-900">配料风险分布</h4>
                <RiskBar label="高风险" count={dangerCount} total={ingredients.length} colorClass="bg-rose-500" />
                <RiskBar label="中风险" count={warningCount} total={ingredients.length} colorClass="bg-amber-500" />
                <RiskBar label="安全" count={safeCount} total={ingredients.length} colorClass="bg-emerald-500" />
              </div>

              <div className="rounded-xl bg-white p-5">
                <h4 className="mb-4 text-sm font-semibold text-slate-900">识别到的原始配料信息</h4>
                <p className="whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-sm leading-7 text-slate-600">
                  {report.ingredients_text || '未识别到原始配料文本'}
                </p>
              </div>

              <div>
                <h4 className="mb-4 text-sm font-semibold text-slate-900">详细配料列表</h4>
                {ingredients.length > 0 ? (
                  <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                    {ingredients.map((item) => {
                      const riskMeta = getIngredientRiskMeta(item.risk);
                      return (
                        <div key={`${item.name}-${item.risk}`} className={`rounded-xl border p-4 ${riskMeta.cardClass}`}>
                          <div className="mb-3 flex items-center gap-2">
                            <span className={`rounded px-2 py-0.5 text-xs font-medium ${riskMeta.chipClass}`}>
                              {riskMeta.label}
                            </span>
                          </div>
                          <div className="space-y-2">
                            <div className="flex items-center justify-between gap-3">
                              <span className="text-sm font-medium text-slate-900">{item.name}</span>
                              <span className={`h-2.5 w-2.5 rounded-full ${riskMeta.dotClass}`} />
                            </div>
                            <p className="text-xs leading-5 text-slate-600">{item.description}</p>
                            {item.function_category && (
                              <div className="text-xs text-slate-500">功能类别：{item.function_category}</div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-6 py-10 text-center text-sm text-slate-400">
                    暂无结构化配料风险结果
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'nutrition' && (
            <div className="space-y-8 rounded-[32px] border border-slate-200 bg-white p-8 shadow-sm">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-4">
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-600">
                    <BarChart3 className="h-7 w-7" />
                  </div>
                  <div>
                    <h4 className="text-2xl font-bold text-slate-900">
                      {nutritionTable?.title || '营养成分表'}
                    </h4>
                    <p className="mt-1 text-lg text-slate-500">
                      {nutritionTable?.serving_basis || nutritionTable?.subtitle || '每100克 (Per 100g)'}
                    </p>
                  </div>
                </div>

                <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-600">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  {getNutritionParseSourceLabel(
                    nutritionTable?.parse_source || report.nutrition_parse_source,
                  )}
                </div>
              </div>

              {nutritionTable?.rows?.length ? (
                <div className="space-y-6">
                  <div className="overflow-hidden rounded-[28px] bg-slate-50/70">
                    <div className="overflow-x-auto">
                      <div className="min-w-[820px] bg-white">
                        <div className="grid grid-cols-[1.8fr_0.7fr_0.6fr_1.3fr] gap-4 border-b-2 border-slate-200 px-6 py-4 text-sm font-bold text-slate-700">
                          <div>营养成分</div>
                          <div>含量</div>
                          <div>NRV%</div>
                          <div>摄入建议</div>
                        </div>

                        {nutritionTable.rows.map((row) => {
                          const tone = getNutritionLevelMeta(row.level);
                          return (
                            <div
                              key={`${row.nutrient_key}-${row.display_name}`}
                              className={cn(
                                'grid grid-cols-[1.8fr_0.7fr_0.6fr_1.3fr] gap-4 border-b border-slate-100 px-6 py-5 text-sm last:border-b-0',
                                tone.rowClass,
                              )}
                            >
                              <div
                                className={cn(
                                  'flex items-center text-slate-900',
                                  row.is_child ? 'pl-5 text-[15px] text-slate-500' : 'text-[18px] font-semibold',
                                )}
                              >
                                {row.is_child ? `↳ ${row.display_name}` : row.display_name}
                              </div>
                              <div className={cn('text-[18px] font-semibold', tone.amountClass)}>
                                {row.amount}
                              </div>
                              <div>
                                {row.nrv_label ? (
                                  <span
                                    className={cn(
                                      'inline-flex rounded-full px-3 py-1 text-sm font-semibold',
                                      tone.badgeClass,
                                    )}
                                  >
                                    {row.nrv_label}
                                  </span>
                                ) : (
                                  <span className="text-sm text-slate-400">-</span>
                                )}
                              </div>
                              <div className={cn('flex items-center gap-2 text-[15px]', tone.recommendationClass)}>
                                {row.level === 'warning' && <AlertTriangle className="h-4 w-4 shrink-0" />}
                                <span>{row.recommendation}</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  <div className="rounded-[24px] bg-amber-50/70 px-6 py-5">
                    <div className="mb-3 flex items-center gap-3">
                      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-100 text-amber-500">
                        <Info className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="text-2xl font-bold text-slate-900">
                          {nutritionTable.advice_title || '营养师建议'}
                        </div>
                      </div>
                    </div>
                    <p className="text-lg leading-8 text-slate-600">
                      {nutritionTable.advice_summary ||
                        '建议结合总能量、配料风险和个人健康目标综合判断。'}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-6 py-14 text-center text-sm text-slate-400">
                  未提取到结构化营养数据
                </div>
              )}
            </div>
          )}

          {activeTab === 'advice' && (
            <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {healthAdvice.length > 0 ? (
                  healthAdvice.map((item) => {
                    const riskMeta = getIngredientRiskMeta(item.risk);
                    return (
                      <div key={item.group} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                        <div className="mb-3 flex items-center gap-2">
                          <span className={`rounded px-2 py-0.5 text-xs font-medium ${riskMeta.chipClass}`}>
                            {item.group}
                          </span>
                          <span className="text-xs text-slate-400">{riskMeta.label}</span>
                        </div>
                        <p className="text-sm leading-6 text-slate-700">{item.advice}</p>
                        <div className="mt-4 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-500">{item.hint}</div>
                      </div>
                    );
                  })
                ) : (
                  <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-6 py-10 text-center text-sm text-slate-400">
                    暂无个性化人群建议
                  </div>
                )}
              </div>

              {report.analysis?.benefits?.length > 0 && (
                <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-5">
                  <h4 className="mb-4 flex items-center gap-2 text-sm font-semibold text-emerald-900">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                    可能的营养亮点
                  </h4>
                  <div className="grid gap-3 md:grid-cols-2">
                    {report.analysis.benefits.map((benefit) => (
                      <div key={benefit} className="rounded-xl bg-white px-4 py-3 text-sm text-slate-700 shadow-sm">
                        {benefit}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

    </div>
  );
}

function MetricCard({
  dotClass,
  label,
  value,
  suffix,
  surfaceClass,
  valueClass = 'text-slate-900',
}: {
  dotClass: string;
  label: string;
  value: number;
  suffix: string;
  surfaceClass: string;
  valueClass?: string;
}) {
  return (
    <div className={`rounded-2xl border border-slate-100 bg-gradient-to-br p-5 ${surfaceClass}`}>
      <div className="mb-2 flex items-center gap-2">
        <div className={`h-2 w-2 rounded-full ${dotClass}`} />
        <div className="text-sm font-medium text-slate-600">{label}</div>
      </div>
      <div className="flex items-baseline gap-1">
        <div className={`text-3xl font-bold ${valueClass}`}>{value}</div>
        <div className="text-sm text-slate-500">{suffix}</div>
      </div>
    </div>
  );
}

function RiskBar({
  label,
  count,
  total,
  colorClass,
}: {
  label: string;
  count: number;
  total: number;
  colorClass: string;
}) {
  const percentage = total > 0 ? (count / total) * 100 : 0;

  return (
    <div className="mb-3 flex items-center gap-4 last:mb-0">
      <div className="flex w-20 items-center gap-1 text-xs text-slate-600">
        <div className={`h-2 w-2 rounded-full ${colorClass}`} />
        {label}
      </div>
      <div className="h-3 flex-1 overflow-hidden rounded-full bg-slate-200">
        <div className={`h-full rounded-full ${colorClass}`} style={{ width: `${percentage}%` }} />
      </div>
      <div className="w-12 text-right text-xs text-slate-600">{count}项</div>
    </div>
  );
}
