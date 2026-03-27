import { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  FileImage,
  ImageUp,
  RefreshCw,
  Settings2,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { apiClient } from '@/api/client';
import { useAuthStore } from '@/store/auth';
import { summarizePreferences } from '@/lib/foodguard';
import type { ApiResponse } from '@/types/api';

const ANALYSIS_UPLOAD_TIMEOUT_MS = 120000;

export default function Home() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pickerHintTimeoutRef = useRef<number | null>(null);
  const preferences = useAuthStore((state) => state.preferences);
  const [dragActive, setDragActive] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [pickerHintVisible, setPickerHintVisible] = useState(false);

  useEffect(() => {
    return () => {
      if (pickerHintTimeoutRef.current !== null) {
        window.clearTimeout(pickerHintTimeoutRef.current);
      }
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  useEffect(() => {
    if (!pickerHintVisible) {
      return;
    }

    const handleWindowFocus = () => {
      window.setTimeout(() => {
        setPickerHintVisible(false);
      }, 150);
    };

    window.addEventListener('focus', handleWindowFocus);
    return () => {
      window.removeEventListener('focus', handleWindowFocus);
    };
  }, [pickerHintVisible]);

  const preferenceSummary = summarizePreferences(
    preferences?.focus_groups,
    preferences?.health_conditions,
    preferences?.allergies,
  );

  const showPickerHint = () => {
    if (pickerHintTimeoutRef.current !== null) {
      window.clearTimeout(pickerHintTimeoutRef.current);
    }

    setPickerHintVisible(true);
    pickerHintTimeoutRef.current = window.setTimeout(() => {
      setPickerHintVisible(false);
      pickerHintTimeoutRef.current = null;
    }, 5000);
  };

  const openFilePicker = () => {
    if (!fileInputRef.current) {
      return;
    }

    fileInputRef.current.value = '';
    showPickerHint();
    fileInputRef.current.click();
  };

  const handleDropZoneKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }

    event.preventDefault();
    openFilePicker();
  };

  const handleDrag = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    if (event.type === 'dragenter' || event.type === 'dragover') {
      setDragActive(true);
    } else if (event.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const updateFile = (selectedFile: File) => {
    if (!selectedFile.type.startsWith('image/')) {
      setError('请上传图片文件（JPG、PNG、WEBP）');
      return;
    }

    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }

    setFile(selectedFile);
    setPreviewUrl(URL.createObjectURL(selectedFile));
    setError('');
    setPickerHintVisible(false);
  };

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setDragActive(false);
    if (event.dataTransfer.files?.[0]) {
      updateFile(event.dataTransfer.files[0]);
    }
  };

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files?.[0]) {
      updateFile(event.target.files[0]);
      return;
    }

    setPickerHintVisible(false);
  };

  const clearFile = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setFile(null);
    setPreviewUrl('');
    setError('');
    setPickerHintVisible(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleUpload = async () => {
    if (!file) {
      return;
    }

    setLoading(true);
    setError('');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const analyzingPreviewUrl = URL.createObjectURL(file);
      sessionStorage.setItem('latest_upload_preview', analyzingPreviewUrl);

      const res = await apiClient.post<any, ApiResponse<{ task_id: string }>>(
        '/analysis/upload',
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
          timeout: ANALYSIS_UPLOAD_TIMEOUT_MS,
        },
      );

      if (res.code !== 0) {
        setError(res.message || '上传失败');
        return;
      }

      navigate(`/analyzing/${res.data.task_id}`);
    } catch (err: any) {
      if (err.code === 'ECONNABORTED') {
        setError('上传超时，请稍后重试');
      } else {
        setError(err.response?.data?.message || '网络请求失败，请稍后重试');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex w-full flex-1 flex-col">
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept="image/*"
        onChange={handleChange}
      />

      <div className="flex-1">
        {!file ? (
        <div className="mx-auto flex max-w-5xl flex-col items-center justify-center pt-6">
          <div className="mb-12 max-w-3xl text-center">
            <h1 className="mb-6 text-4xl font-extrabold leading-tight tracking-tight text-slate-900 md:text-5xl lg:text-6xl">
              看透食品标签，
              <br />
              <span className="bg-gradient-to-r from-emerald-500 to-teal-400 bg-clip-text text-transparent">
                吃得更明白、更健康
              </span>
            </h1>
            <p className="mx-auto max-w-2xl text-lg leading-relaxed text-slate-600">
              只需上传配料表或营养成分表照片，AI 会自动识别关键风险、提炼核心建议，并结合你的默认健康偏好给出更贴近实际的判断。
            </p>
          </div>

          <div className="w-full max-w-3xl rounded-[28px] border border-white bg-white/80 p-2 shadow-xl shadow-slate-200/50 backdrop-blur-xl">
            <div
              role="button"
              tabIndex={0}
              aria-label="选择上传图片"
              className={`file-drop-zone flex min-h-[280px] w-full cursor-pointer flex-col items-center justify-center rounded-[22px] bg-white px-8 py-10 text-center transition ${
                dragActive ? 'border-emerald-400 bg-emerald-50/70' : ''
              }`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={openFilePicker}
              onKeyDown={handleDropZoneKeyDown}
            >
              <div
                className={`mb-6 flex h-20 w-20 items-center justify-center rounded-full transition-transform duration-300 ${
                  dragActive ? 'scale-110 bg-emerald-100' : 'bg-emerald-50'
                }`}
              >
                <ImageUp className="h-10 w-10 text-emerald-500" />
              </div>
              <h3 className="mb-2 text-xl font-bold text-slate-900">点击上传 或 拖拽图片至此处</h3>
              <p className="text-sm text-slate-500">支持配料表、营养成分表照片（JPG、PNG、WEBP）</p>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  openFilePicker();
                }}
                className="mt-6 inline-flex items-center gap-2 rounded-full bg-emerald-500 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2"
              >
                <ImageUp className="h-4 w-4" />
                选择图片
              </button>
              <p className="mt-4 text-xs text-slate-500">
                {pickerHintVisible
                  ? '已打开系统文件选择窗口，请在系统窗口中选择图片。'
                  : '点击区域或按钮后会先进入图片预览，再点击“开始智能分析”正式上传。'}
              </p>
            </div>
          </div>
        </div>
        ) : (
        <div className="w-full">
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-slate-900">确认图片并开始分析</h1>
            <p className="mt-1 text-sm text-slate-500">
              请确认图片清晰可读。当前页面布局参考原型的“上传预览”页，分析会沿用你在个人设置里保存的默认偏好。
            </p>
          </div>

          <div className="flex flex-col gap-8 lg:flex-row">
            <div className="flex flex-1 flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="relative flex min-h-[420px] items-center justify-center overflow-hidden rounded-xl bg-slate-100">
                <img src={previewUrl} alt="上传预览" className="max-h-[620px] max-w-full object-contain" />
              </div>

              <div className="mt-4 flex items-center justify-between px-1">
                <div className="flex items-center gap-2 text-sm text-slate-500">
                  <FileImage className="h-4 w-4" />
                  <span>{file.name}</span>
                  <span>({(file.size / 1024 / 1024).toFixed(2)} MB)</span>
                </div>

                <button
                  type="button"
                  onClick={openFilePicker}
                  className="text-sm font-medium text-emerald-600 transition-colors hover:text-emerald-700"
                >
                  重新上传图片
                </button>
              </div>
            </div>

            <aside className="flex w-full flex-col gap-6 lg:w-80">
              <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="mb-4 flex items-center gap-2 text-base font-bold text-slate-900">
                  <Settings2 className="h-5 w-5 text-emerald-500" />
                  默认分析偏好
                </h3>

                <div className="space-y-4 text-sm">
                  <section>
                    <div className="mb-2 font-medium text-slate-700">关注人群</div>
                    <div className="flex flex-wrap gap-2">
                      {preferenceSummary.focusGroups.length > 0 ? (
                        preferenceSummary.focusGroups.map((item) => (
                          <span
                            key={item}
                            className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-emerald-700"
                          >
                            {item}
                          </span>
                        ))
                      ) : (
                        <span className="text-slate-400">未设置，将按通用标准分析</span>
                      )}
                    </div>
                  </section>

                  <section>
                    <div className="mb-2 font-medium text-slate-700">健康关注</div>
                    <div className="flex flex-wrap gap-2">
                      {preferenceSummary.healthConditions.length > 0 ? (
                        preferenceSummary.healthConditions.map((item) => (
                          <span
                            key={item}
                            className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-slate-600"
                          >
                            {item}
                          </span>
                        ))
                      ) : (
                        <span className="text-slate-400">未设置特殊健康条件</span>
                      )}
                    </div>
                  </section>

                  {preferenceSummary.allergies.length > 0 && (
                    <section>
                      <div className="mb-2 font-medium text-slate-700">过敏源</div>
                      <div className="flex flex-wrap gap-2">
                        {preferenceSummary.allergies.map((item) => (
                          <span
                            key={item}
                            className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-amber-700"
                          >
                            {item}
                          </span>
                        ))}
                      </div>
                    </section>
                  )}
                </div>
              </div>

              {error && (
                <div className="flex items-start gap-2 rounded-2xl border border-rose-100 bg-rose-50 p-4 text-sm text-rose-600">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <Button
                size="lg"
                onClick={handleUpload}
                isLoading={loading}
                className="group h-14 w-full rounded-2xl bg-emerald-500 text-lg font-bold hover:bg-emerald-600"
              >
                开始智能分析
                {!loading && <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-1" />}
              </Button>

              <div className="rounded-2xl border border-blue-100 bg-blue-50 p-4 text-xs leading-6 text-blue-800">
                <div className="mb-1 font-semibold">分析说明</div>
                <p>
                  当前链路会依次执行 OCR、知识库检索和大模型评估。根据图片清晰度与外部服务响应速度，整体耗时通常在
                  1 到 2 分钟之间。
                </p>
              </div>

              <button
                type="button"
                onClick={clearFile}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
              >
                <RefreshCw className="h-4 w-4" />
                取消并重新选择
              </button>
            </aside>
          </div>
        </div>
        )}
      </div>

      <div className="pt-8 text-center text-xs text-slate-400">
        <div className="mx-auto max-w-5xl border-t border-slate-200/70 pt-5">
          FoodGuard · 智能食品标签分析
        </div>
      </div>
    </div>
  );
}
