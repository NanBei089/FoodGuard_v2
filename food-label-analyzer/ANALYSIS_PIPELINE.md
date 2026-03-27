# Food Label Analyzer 分析部分链路图

本文档描述了后端在接收到用户上传的图片后，执行的完整分析链路（基于 `app/tasks/analysis_task.py`）。

## 分析流程架构图 (Mermaid)

```mermaid
graph TD
    %% 角色与系统节点
    User((用户/前端))
    API[FastAPI 接口\n/api/v1/analysis/upload]
    DB[(PostgreSQL)]
    Redis[(Redis\nCelery Broker)]
    MinIO[(MinIO\n对象存储)]
    
    %% Celery Worker 节点
    subgraph Celery 分析任务 (process_image_task)
        Download[1. 下载源图片]
        
        subgraph 图像预处理与识别
            YOLO[2. YOLO 目标检测\n定位营养成分表]
            Split{是否检测到\n成分表?}
            Crop[裁剪出成分表图片\n& 遮罩处理原图]
            
            OCR_Parallel[3a. 并行 OCR 识别\n(原图去表 + 成分表)]
            OCR_Full[3b. 单图全量 OCR 识别\n(仅全量文本)]
        end
        
        subgraph 信息提取
            Nutri_Extract[4. 营养成分提取\n(nutrition_extractor)]
            Ingre_Extract[5. 配料表文本提取\n(ingredient_extractor)]
        end
        
        subgraph 知识增强与分析
            RAG[6. RAG 知识检索\n(检索 ChromaDB)]
            ChromaDB[(ChromaDB\n向量库)]
            LLM[7. LLM 综合健康分析\n(DeepSeek)]
        end
        
        SaveReport[8. 生成并保存最终报告\n(_complete_task_with_report)]
    end

    %% 主流程线条
    User -- "1. 上传图片 (UploadFile)" --> API
    API -- "2. 保存图片文件" --> MinIO
    API -- "3. 创建 AnalysisTask 记录" --> DB
    API -- "4. 发送 Celery 任务" --> Redis
    API -. "5. 返回 task_id" .-> User
    
    Redis -- "消费任务" --> Download
    Download -- "获取图片流" --> MinIO
    Download --> YOLO
    
    YOLO --> Split
    Split -- "是 (bbox存在)" --> Crop
    Crop --> OCR_Parallel
    Split -- "否 (无bbox)" --> OCR_Full
    
    OCR_Parallel --> Nutri_Extract
    OCR_Full --> Nutri_Extract
    
    OCR_Parallel --> Ingre_Extract
    OCR_Full --> Ingre_Extract
    
    Ingre_Extract -- "配料词条" --> RAG
    RAG <--> ChromaDB
    
    Nutri_Extract -- "结构化营养数据" --> LLM
    Ingre_Extract -- "配料表原文本" --> LLM
    RAG -- "增强知识/添加剂安全性" --> LLM
    
    LLM -- "健康评分与建议" --> SaveReport
    SaveReport -- "更新 Task 状态为 completed\n插入 Report 记录" --> DB
```

## 核心步骤详解

1. **接口接收阶段 ([app/api/v1/analysis.py](file:///E:/GraduationProject/foodguard/food-label-analyzer/app/api/v1/analysis.py))**
   - 校验图片合法性并上传至 MinIO。
   - 在 PostgreSQL 数据库创建状态为 `pending` (对外 `queued`) 的 `AnalysisTask`。
   - 通过 Celery 将分析任务推入 `analysis` 队列。

2. **YOLO 目标检测 ([app/workers/yolo_worker.py](file:///E:/GraduationProject/foodguard/food-label-analyzer/app/workers/yolo_worker.py))**
   - 读取图片，使用 `yolo26s.onnx` 模型寻找营养成分表区域（`bbox`）。
   - 如果找到：生成两张图 —— **仅成分表区域的裁剪图** 和 **原图抹掉成分表的遮罩图**。

3. **OCR 文本识别 ([app/workers/ocr_worker.py](file:///E:/GraduationProject/foodguard/food-label-analyzer/app/workers/ocr_worker.py))**
   - 调用 PaddleOCR 接口。
   - 如果有成分表，执行**双路并发OCR**：一路负责普通文本提取，一路负责表格提取。
   - 如果无成分表，则只执行单图的全量 OCR 文本提取。

4. **信息提取阶段 ([app/workers/extractor](file:///E:/GraduationProject/foodguard/food-label-analyzer/app/workers/extractor))**
   - **营养成分提取**: 将表格 OCR 结果转化为结构化 JSON 数据（能量、蛋白质、钠等），若无表格则使用全量文本作为 fallback。
   - **配料表提取**: 使用正则或简单逻辑从 OCR 全量文本中提取出配料表内容及独立配料词条。

5. **RAG 向量检索 ([app/workers/rag_worker.py](file:///E:/GraduationProject/foodguard/food-label-analyzer/app/workers/rag_worker.py))**
   - 使用 Ollama 模型将配料词条转换为向量。
   - 在本地的 ChromaDB (`gb2760_a1_grouped`) 中进行相似度检索，获取添加剂标准、安全上限及功效分类。

6. **大模型综合分析 ([app/workers/llm_worker.py](file:///E:/GraduationProject/foodguard/food-label-analyzer/app/workers/llm_worker.py))**
   - 将结构化的营养数据、配料表原文、RAG 检索结果拼接为上下文。
   - 提交给 DeepSeek 大模型（配置 `DEEPSEEK_MODEL`），由 LLM 根据提示词输出健康打分、人群建议和成分风险汇总。

7. **保存结果 ([app/tasks/analysis_task.py](file:///E:/GraduationProject/foodguard/food-label-analyzer/app/tasks/analysis_task.py))**
   - 解析 LLM 返回的 JSON 结果，写入 `reports` 表。
   - 更新 `analysis_tasks` 状态为 `completed`，整个异步分析流程结束。
