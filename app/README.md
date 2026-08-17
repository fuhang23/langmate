# LangMate —— 新托福口语搭子（MVP 开发中）

基于 [nanobot](https://github.com/HKUDS/nanobot)（HKUDS 轻量 AI Agent 框架）二次开发。
目标是做一个「亦师亦友」的 AI 英语学习搭子，先从新托福口语备考开始。

## 项目结构

```
app/
├── nanobot/                 # 基座源码（git submodule → fuhang23/nanobot fork）
├── workspace/
│   └── skills/
│       └── toefl-speaking/  # 自研口语搭子 Skill（教学法核心）
│           └── SKILL.md
├── services/
│   ├── tts_doubao.py        # 豆包 TTS（Phase 2，语音合成）
│   └── speech_score.py      # 口语发音评分（Phase 3，骨架）
├── config.json              # nanobot 配置（DeepSeek 主模型 + workspace + WebUI）
└── .env.example             # 需要的 API key 清单
```

> `app/nanobot` 是 git submodule，指向你 fork 的 [fuhang23/nanobot](https://github.com/fuhang23/nanobot)。
> 若要追官方上游更新，进入子模块执行 `git fetch upstream && git merge upstream/main`。

## 当前进度

- [x] nanobot 基座安装（v0.3.0，conda 环境 `langmate`）
- [x] DeepSeek 主模型配置（`config.json`）
- [x] 口语搭子 Skill（`toefl-speaking`）编写 + 验证加载
- [x] TTS / 评分服务骨架
- [ ] 真实 API key 跑通对话（**阻塞项**）
- [ ] LightRAG 知识库（本地资料入库）
- [ ] 语音链路（ASR + TTS + WebUI）

## 如何运行

> 注意：`config.json` 里的 workspace 是相对路径（`workspace`），nanobot 会相对于**运行时的工作目录（CWD）**解析它。因此下面的命令都需**先 `cd` 到 `app/` 目录**再执行；若想从任意目录运行，可加 `-w` 参数指定 workspace 的绝对路径。

```bash
cd app
# 1. 填 API key（参考 .env.example）
# 2. 设置环境变量后，文字版对话：
export DEEPSEEK_API_KEY="sk-你的key"
nanobot agent -c config.json -m "你好，我想练托福口语"

# 3. WebUI（浏览器界面）：
nanobot webui -c config.json
```

## 关键发现（关于基座）

- nanobot 的 WebUI **已内置麦克风录音 → ASR**（`transcription` 配置），语音输入不用改前端。
- nanobot 已内置 docx/pdf 文档读取，是 LightRAG 之外的轻量兜底。
- 缺的只有 **TTS**（需自建，见 `services/tts_doubao.py`）和 **口语评分引擎**。
