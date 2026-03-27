import { useEffect, useState } from 'react';
import { AlertCircle } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { apiClient } from '@/api/client';
import type { ApiResponse } from '@/types/api';

interface TaskStatus {
  task_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  progress_message: string;
  report_id: string | null;
  error_message: string | null;
}

function revokePreview(url: string | null) {
  if (url && url.startsWith('blob:')) {
    URL.revokeObjectURL(url);
  }
  sessionStorage.removeItem('latest_upload_preview');
}

export default function Analyzing() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [status, setStatus] = useState<TaskStatus | null>(null);
  const [error, setError] = useState('');
  const previewUrl =
    sessionStorage.getItem('latest_upload_preview') ||
    'https://images.unsplash.com/photo-1622483767028-3f66f32aef97?w=400&q=80';

  useEffect(() => {
    if (!taskId) {
      return;
    }

    let timeoutId: ReturnType<typeof setTimeout>;
    let pollInterval = 1500;

    const checkStatus = async () => {
      try {
        const res = await apiClient.get<any, ApiResponse<TaskStatus>>(`/analysis/tasks/${taskId}`);

        if (res.code !== 0) {
          setError(res.message || '分析任务状态获取失败');
          return;
        }

        setStatus(res.data);

        if (res.data.status === 'completed' && res.data.report_id) {
          revokePreview(previewUrl);
          navigate(`/reports/${res.data.report_id}`);
          return;
        }

        if (res.data.status === 'failed') {
          setError(res.data.error_message || '分析失败');
          revokePreview(previewUrl);
          return;
        }

        pollInterval = Math.min(pollInterval + 500, 3000);
        timeoutId = setTimeout(checkStatus, pollInterval);
      } catch {
        timeoutId = setTimeout(checkStatus, pollInterval);
      }
    };

    checkStatus();

    return () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [navigate, previewUrl, taskId]);

  const progressPercentage =
    status?.status === 'queued'
      ? 12
      : status?.status === 'processing' && !status.progress_message.includes('LLM')
        ? 42
        : status?.status === 'processing' && status.progress_message.includes('LLM')
          ? 82
          : status?.status === 'completed'
            ? 100
            : 0;

  return (
    <div className="flex min-h-[calc(100vh-220px)] items-center justify-center py-6">
      <div className="relative w-full max-w-md overflow-hidden rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-xl">
        <div className="absolute left-1/2 top-0 -z-10 h-64 w-64 -translate-x-1/2 rounded-full bg-emerald-400/10 blur-3xl" />

        {error || status?.status === 'failed' ? (
          <>
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-rose-100 text-rose-600">
              <AlertCircle className="h-8 w-8" />
            </div>
            <h2 className="text-2xl font-bold text-slate-900">分析失败</h2>
            <p className="mt-2 text-slate-600">{error || status?.error_message}</p>
            <Button onClick={() => navigate('/')} className="mt-6 w-full">
              返回首页重试
            </Button>
          </>
        ) : (
          <>
            <div className="mb-8">
              <div className="relative mx-auto h-48 w-48 overflow-hidden rounded-2xl border border-slate-200 bg-slate-100 shadow-inner">
                <img src={previewUrl} alt="分析中" className="h-full w-full object-cover opacity-70" />
                <div className="absolute inset-0 rounded-2xl border-2 border-emerald-500/50" />
                <div className="scanner-line animate-scan z-10" />
                <div className="absolute left-[10%] top-[20%] h-[10%] w-[80%] rounded border border-emerald-400/80 bg-emerald-400/10" />
                <div className="absolute left-[10%] top-[40%] h-[8%] w-[60%] rounded border border-emerald-400/80 bg-emerald-400/10" />
                <div className="absolute left-[10%] top-[60%] h-[12%] w-[70%] rounded border border-emerald-400/80 bg-emerald-400/10" />
              </div>
            </div>

            <h2 className="mb-2 text-2xl font-bold text-slate-900">AI 正在深度分析</h2>
            <p className="mb-8 h-5 text-sm text-slate-500">
              {status?.progress_message || '初始化分析引擎中...'}
            </p>

            <div className="relative mb-2 h-3 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className="progress-bar-fill relative h-full rounded-full bg-emerald-500"
                style={{ width: `${progressPercentage}%` }}
              >
                <div className="absolute inset-0 animate-[pulse_2s_linear_infinite] bg-gradient-to-r from-transparent via-white/40 to-transparent" />
              </div>
            </div>
            <div className="flex justify-between text-xs font-medium text-slate-400">
              <span>0%</span>
              <span className="text-emerald-600">{progressPercentage}%</span>
              <span>100%</span>
            </div>

            <div className="mt-8 space-y-4 text-left">
              <Step title="图片预处理与增强" status={status?.status === 'queued' ? 'processing' : 'completed'} stepNum={1} />
              <Step
                title="执行 OCR 文字识别"
                status={
                  status?.status === 'processing' && !status.progress_message.includes('LLM')
                    ? 'processing'
                    : status?.progress_message.includes('LLM') || status?.status === 'completed'
                      ? 'completed'
                      : 'pending'
                }
                stepNum={2}
              />
              <Step
                title="大模型成分风险评估"
                status={
                  status?.progress_message.includes('LLM')
                    ? 'processing'
                    : status?.status === 'completed'
                      ? 'completed'
                      : 'pending'
                }
                stepNum={3}
              />
              <Step
                title="生成个性化健康报告"
                status={status?.status === 'completed' ? 'processing' : 'pending'}
                stepNum={4}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Step({
  title,
  status,
  stepNum,
}: {
  title: string;
  status: 'pending' | 'processing' | 'completed';
  stepNum: number;
}) {
  return (
    <div
      className={`flex items-center gap-3 transition-opacity duration-300 ${
        status === 'pending' ? 'opacity-40' : status === 'completed' ? 'opacity-50' : ''
      }`}
    >
      {status === 'completed' ? (
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
          </svg>
        </div>
      ) : status === 'processing' ? (
        <div className="animate-pulse-fast flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-100 text-blue-600">
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </div>
      ) : (
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 border-slate-200 text-slate-400">
          <span className="text-xs">{stepNum}</span>
        </div>
      )}
      <span className={`text-sm ${status === 'processing' ? 'font-bold text-slate-900' : 'font-medium text-slate-700'}`}>
        {title}
      </span>
    </div>
  );
}
