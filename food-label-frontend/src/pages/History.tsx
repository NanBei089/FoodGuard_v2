import { useEffect, useState } from 'react';
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Eye,
  FileImage,
  Filter,
  Search,
  Trash2,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { apiClient } from '@/api/client';
import { formatReportDate, getScorePalette } from '@/lib/foodguard';
import type { ApiResponse, PageResponse } from '@/types/api';

interface ReportListItem {
  report_id: string;
  task_id: string;
  score: number;
  summary: string;
  image_url: string;
  created_at: string;
}

export default function History() {
  const navigate = useNavigate();
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');

  const fetchReports = async (pageNumber = 1) => {
    try {
      setLoading(true);
      setError('');

      const res = await apiClient.get<any, ApiResponse<PageResponse<ReportListItem>>>(
        `/reports?page=${pageNumber}&page_size=10`,
      );

      if (res.code !== 0) {
        setError(res.message || '获取记录失败');
        return;
      }

      setReports(res.data.items);
      setTotal(res.data.total);
      setPage(res.data.page);
      setPageSize(res.data.page_size);
    } catch (err: any) {
      setError(err.response?.data?.message || '获取记录失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReports(page);
  }, [page]);

  const handleDelete = async (id: string, event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();

    if (!window.confirm('确定要删除这条记录吗？')) {
      return;
    }

    try {
      const res = await apiClient.delete<any, ApiResponse<null>>(`/reports/${id}`);
      if (res.code === 0) {
        setReports((current) => current.filter((item) => item.report_id !== id));
        setTotal((current) => Math.max(0, current - 1));
      }
    } catch {
      window.alert('删除失败');
    }
  };

  const filteredReports = reports.filter((report) => {
    const keyword = search.trim().toLowerCase();
    if (!keyword) {
      return true;
    }

    return [report.summary, report.report_id]
      .join(' ')
      .toLowerCase()
      .includes(keyword);
  });

  if (loading) {
    return <div className="py-12 text-center text-slate-500">加载中...</div>;
  }

  if (error) {
    return (
      <div className="py-12 text-center">
        <div className="mb-4 flex items-center justify-center gap-2 text-red-500">
          <AlertCircle className="h-5 w-5" />
          {error}
        </div>
        <Button onClick={() => fetchReports(page)} variant="outline">
          重试
        </Button>
      </div>
    );
  }

  return (
    <div className="w-full">
      <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">分析历史记录</h1>
          <p className="mt-1 text-sm text-slate-500">查看和管理你过去的食品标签分析报告。</p>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索报告..."
              className="w-full rounded-xl border border-slate-200 py-2 pl-9 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 md:w-64"
            />
          </div>
          <button
            type="button"
            className="flex items-center gap-2 rounded-xl border border-slate-200 p-2 text-slate-600 transition-colors hover:bg-slate-50"
          >
            <Filter className="h-4 w-4" />
            <span className="hidden text-sm font-medium sm:inline">筛选</span>
          </button>
        </div>
      </div>

      {filteredReports.length === 0 ? (
        <div className="rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50 p-12 text-center text-slate-500">
          <FileImage className="mx-auto mb-4 h-12 w-12 text-slate-300" />
          <p>{search ? '当前搜索条件下没有报告' : '暂时还没有分析记录'}</p>
          {!search && (
            <div className="mt-4">
              <Link to="/">
                <Button variant="outline">去上传第一张标签</Button>
              </Link>
            </div>
          )}
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-sm font-semibold text-slate-600">
                  <th className="px-6 py-4">报告信息</th>
                  <th className="px-6 py-4">健康评分</th>
                  <th className="hidden px-6 py-4 md:table-cell">核心摘要</th>
                  <th className="hidden px-6 py-4 sm:table-cell">分析时间</th>
                  <th className="px-6 py-4 text-right">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredReports.map((report) => {
                  const palette = getScorePalette(report.score);

                  return (
                    <tr
                      key={report.report_id}
                      className="group cursor-pointer transition-colors hover:bg-slate-50"
                      onClick={() => navigate(`/reports/${report.report_id}`)}
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-4">
                          <div className="h-12 w-12 shrink-0 overflow-hidden rounded-lg bg-slate-100">
                            {report.image_url ? (
                              <img src={report.image_url} alt="标签缩略图" className="h-full w-full object-cover" />
                            ) : (
                              <FileImage className="m-3 h-6 w-6 text-slate-300" />
                            )}
                          </div>
                          <div className="space-y-1">
                            <div className="line-clamp-1 font-bold text-slate-900 transition-colors group-hover:text-emerald-600">
                              AI 健康分析报告
                            </div>
                            <div className="text-xs text-slate-400">报告 ID：{report.report_id.slice(0, 8)}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <div
                            className={`flex h-8 w-8 items-center justify-center rounded-full border-2 ${
                              report.score >= 80
                                ? 'border-emerald-500'
                                : report.score >= 60
                                  ? 'border-amber-500'
                                  : 'border-rose-500'
                            }`}
                          >
                            <span className={`text-xs font-bold ${palette.text}`}>{report.score}</span>
                          </div>
                          <span className={`rounded px-2 py-0.5 text-xs font-medium ${palette.badgeClass}`}>
                            {palette.badge}
                          </span>
                        </div>
                      </td>
                      <td className="hidden px-6 py-4 md:table-cell">
                        <div className="line-clamp-2 max-w-xs text-sm text-slate-500">
                          {report.summary || '暂无摘要'}
                        </div>
                      </td>
                      <td className="hidden px-6 py-4 text-sm text-slate-500 sm:table-cell">
                        {formatReportDate(report.created_at)}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="flex items-center justify-end gap-3">
                          <button
                            type="button"
                            className="flex items-center gap-1.5 rounded-lg bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-600 transition-colors hover:bg-emerald-100"
                            onClick={(event) => {
                              event.stopPropagation();
                              navigate(`/reports/${report.report_id}`);
                            }}
                          >
                            <Eye className="h-4 w-4" />
                            查看详情
                          </button>
                          <button
                            type="button"
                            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-slate-500 transition-colors hover:bg-rose-50 hover:text-rose-600"
                            onClick={(event) => handleDelete(report.report_id, event)}
                          >
                            <Trash2 className="h-4 w-4" />
                            删除
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {total > pageSize && (
            <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 p-4">
              <span className="text-sm text-slate-500">共 {total} 条记录</span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  disabled={page === 1}
                  onClick={() => setPage((current) => current - 1)}
                  className="rounded-lg border border-slate-200 p-1.5 text-slate-400 transition-colors hover:bg-white disabled:opacity-50"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <button type="button" className="h-8 w-8 rounded-lg bg-emerald-500 text-sm font-medium text-white">
                  {page}
                </button>
                <button
                  type="button"
                  disabled={page * pageSize >= total}
                  onClick={() => setPage((current) => current + 1)}
                  className="rounded-lg border border-slate-200 p-1.5 text-slate-600 transition-colors hover:bg-white disabled:opacity-50"
                >
                  <ChevronRight className="h-5 w-5" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
