# 文件上传 RAG · 实现文档

> 功能定位：在「内容采集」基础上新增**本地文件上传**能力，把 PDF / DOCX / MD / TXT 文档自动转为可检索的 RAG 知识点。
> 本文记录完整实现细节，供后续维护与迭代参考。
>
> **更新注记（2026-08-22）**：本文写作时文件上传为「纯 RAG、不做大模型判断」；后续《知识库分类过滤与判分增强_实现文档》已将其升级为**统一走 `analyze_tags` 大模型判断**（只留托福 + 广告必过滤 + 打标），判断通过后才本地分块入库。本文的交互流程、存储结构（kind/filename 列、`file://<hash>` 去重键）、分块规则、接口契约仍然准确，归属判断以升级后的行为为准。

---

## 一、功能概述

在「内容采集」页顶部新增「粘贴链接 / 上传文件」两个 tab。上传文件模式下，用户选择本地文档，系统自动完成：

```
选择文件 → 前端读为 base64 → 上传(ingest.upload) → 提取文本 → 本地分块
        → 存 pending → 预览(文件名 + 知识点列表) → 用户确认 → RAG 增量入库
```

与链接导入的关键区别：上传文件**不抽题**（不判断题目归属、不做结构化提取），只做轻量打标判断（`analyze_tags`：考试/广告/科目标签），判断通过即按 RAG 入库，适合讲义、范文、备考方法论等知识类文档。

---

## 二、产品决策（2026-08-21 确认）

| 决策点 | 结论 |
|---|---|
| 归属判断 | ~~纯 RAG：提取→分块→直接进 RAG，不判断/抽取题目~~（后升级为统一 `analyze_tags` 轻量判断：只留托福 + 广告过滤 + 打标，见顶部注记） |
| 分块策略 | **本地规则分块**：按段落聚合约 500 字 + 块间约 80 字重叠，不调大模型 |
| 原文保存 | **保存提取文本**：全文存 `ingest_records.raw_text`，可溯源、可重解析 |
| 入口交互 | **采集页加 tab**：`ContentIngestView` 顶部「粘贴链接 / 上传文件」两个 tab |

---

## 三、交互流程

```
用户在「托福学习空间 → 工具 → 内容采集」切到「上传文件」tab
  → 点击选择或拖拽文件（pdf/docx/md/txt）
  → 前端校验类型与大小（≤10MB），FileReader 读为 base64
  → 调 ingest.upload，显示「解析分块中…」
  → 出预览：文件名 + 分类徽章(RAG 知识点) + 知识点(chunk)列表
  → 用户「确认入库」或「忽略」
     确认 → chunks 增量追加到 ingested-articles RAG → 状态 confirmed
     忽略 → 状态 ignored，不入库
```

**关键点**：同一文档重复上传时，按内容哈希合成唯一 key 去重（`ingest_records.url` UNIQUE）。

---

## 四、数据存储

### 4.1 采集记录表扩展（`data/ingest.db`）

在原有 `ingest_records` 表上幂等新增两列（`ALTER TABLE ADD COLUMN`，旧库自动迁移）：

```sql
ALTER TABLE ingest_records ADD COLUMN kind     TEXT NOT NULL DEFAULT 'link';
ALTER TABLE ingest_records ADD COLUMN filename TEXT NOT NULL DEFAULT '';
```

| 字段 | 链接导入 | 文件上传 |
|---|---|---|
| `url`（唯一键） | 原文 URL | `file://<sha256(提取文本)[:16]>` |
| `kind` | `link` | `file` |
| `filename` | `''` | 原始文件名 |
| `raw_text` | 抓取正文全文 | 提取出的纯文本全文 |
| `category` | 大模型判断 | 固定 `rag` |
| `result_json` | 判断结果 | `{"category":"rag","chunks":[{"text":...}]}` |
| `status` | pending/confirmed/ignored | 同左 |

### 4.2 RAG 落点（`data/rag/index/`）

文件上传与链接导入共用同一 source **`ingested-articles`**：
- `ingested-articles.faiss`（向量索引，`rag_append` 增量追加）
- `ingested-articles.json`（chunk 原文 + metadata）

chunk 元数据：`source='ingested-articles'`、`title=文件名`、`meta={"kind":"file","filename":"xxx.pdf"}`。

---

## 五、后端模块（`app/services/ingest/`）

| 文件 | 职责 |
|---|---|
| `extract_file.py` | 文件文本提取：pdf(pypdf) / docx(zipfile) / md·txt(utf-8)，含扩展名白名单、10MB 上限、空文本校验 |
| `chunker.py` | 本地规则分块：`chunk_text(text, target=500, overlap=80)`，段落聚合 + 块间重叠 |
| `store.py` | `IngestStore`：新增 `kind`/`filename` 列（幂等迁移），`upsert` 支持新列 |
| `ingest.py` | 新增 `upload_and_prepare`；`confirm_ingest`/`ignore_ingest` 入参由 `url` 泛化为 `key` |

### 5.1 提取规则（`extract_file`）

- `.pdf`：`pypdf.PdfReader(BytesIO(data))` 逐页 `extract_text()`。
- `.docx`：`zipfile.ZipFile` 读 `word/document.xml`，正则剥标签还原段落（与 corpus 的 docx 解析一致，不引入 python-docx）。
- `.md`/`.txt`：UTF-8 解码，失败回退 latin-1。
- 提取结果压缩空白后为空则抛 `FileExtractionError`。

### 5.2 分块规则（`chunk_text`）

- 按空行切段落，贪心聚合至约 `target=500` 字。
- 单段超过 500 字时按字符滑动窗口硬切（步长 `target - overlap`）。
- flush 时把当前 chunk 尾部约 80 字带入下一块开头，避免切断语义。

### 5.3 编排（`upload_and_prepare`）

```
base64 解码 → 大小校验(10MB) → extract_file → chunk_text → 计算内容哈希 key
→ IngestStore.upsert(kind='file', category='rag', status='pending')
→ 返回预览 {key, url, filename, title, source, category, reason, items, chunks, status}
```

---

## 六、后端接口（WebUI mutation，走 WebSocket）

| action | mutation path | 说明 |
|---|---|---|
| `ingest.fetch` | `/api/toefl/ingest/fetch` | 链接导入（原有） |
| `ingest.upload` | `/api/toefl/ingest/upload` | **新增**：文件上传 → 提取 + 分块 + 存 pending，返回预览（超时 120s） |
| `ingest.confirm` | `/api/toefl/ingest/confirm` | 确认入库（链接/文件共用） |
| `ingest.ignore` | `/api/toefl/ingest/ignore` | 忽略（链接/文件共用） |

请求/响应 payload：

- `upload`：`{ filename, content_base64 }` → `{ key, url, filename, title, source, category, reason, items, chunks, status }`
- `confirm`：`{ url }`（链接传 URL、文件传 `file://<hash>` key）→ `{ status, questions, chunks }`
- `ignore`：`{ url }` → `{ status: "ignored" }`

均走 `_mutation_payload` 读 body、`check_api_token` 校验、`services.ingest` 惰性导入（nanobot 脱离 langmate 仍可运行）。

---

## 七、前端实现

| 文件 | 内容 |
|---|---|
| `ContentIngestView.tsx` | 顶部新增「粘贴链接 / 上传文件」tab；文件 tab 用 `<input type="file">`（`accept=".pdf,.docx,.md,.txt"`）+ 拖拽 + FileReader 读 base64；复用「预览→确认/忽略」流程 |
| `types.ts` | 新增 `IngestUploadPreview` 类型（结构对齐 `IngestPreview`，多 `key`/`filename`） |
| `api.ts` | 新增 `uploadIngest(transport, filename, contentBase64)`（timeout 120s） |

前端校验：扩展名白名单 + 文件大小 ≤10MB，不合规则就地红色提示，不发起请求。

---

## 八、使用方式

1. 进入「托福学习空间 → 工具 → 内容采集」。
2. 切到「上传文件」tab。
3. 点击选择或拖拽一个 PDF / DOCX / MD / TXT 文件。
4. 等待「解析分块中…」完成后查看预览（文件名 + 知识点列表）。
5. 点「确认入库」写入 RAG，或「忽略」放弃。
6. 后续写作/口语判分与答疑会自动检索到新入库的知识点。

---

## 九、已知限制与风险

1. **WebSocket 消息大小**：10MB 文件 base64 后约 13.3MB，可能触及 nanobot `max_message_bytes` 帧上限；若超限可下调上限至 5MB（base64 约 6.7MB）或前端对大文件拦截。
2. **扫描件 PDF**：无文本层的扫描 PDF 提取结果为空，会报「未提取到文本」，需 OCR 才能支持（当前不支持）。
3. **纯文本提取**：文件上传只提取文本，图片/表格中的内容不进入 RAG。
4. **RAG 删除**：与链接导入一致，faiss 只增难删，删除/更正走「逻辑删除 + 全量重建」。
5. **去重粒度**：按提取文本哈希去重，同一文档改几个字会被视为新文档重新入库。

---

## 十、依赖

- 后端：`pypdf`（PDF 提取，已在 langmate 环境）、`zipfile`/`html`/`re`（DOCX 提取，标准库）、`base64`/`hashlib`（解码与哈希）、`faiss-cpu` + 百炼 embedding（RAG 入库）。
- 环境变量：`BAILIAN_API_KEY`（RAG embedding，未配置则确认入库时 RAG 追加失败，但预览/记录正常）。
- 数据库：`data/ingest.db`（采集记录）、`data/rag/index/`（向量索引）。
