# LangMate —— AI 英语学习搭子

一个「亦师亦友」的 AI 英语学习搭子：不是刷题网站，而是一个有教学法、有长期记忆、有人格的对话式学习伙伴，深度参与「诊断 → 规划 → 学习 → 反馈 → 复盘」全过程。先从**新托福口语备考**起步，逐步扩展到雅思、全英语学习（以 CEFR 欧标度量水平）。

基于 [nanobot](https://github.com/HKUDS/nanobot)（HKUDS 轻量 AI Agent 框架）二次开发，核心差异化是**高度定制化 + 个人知识库（RAG）**。

## 目录结构

```
langmate/
├── app/                    # 应用代码
│   ├── nanobot/            # git submodule（fork 的基座）
│   ├── workspace/skills/   # 自研 Skill（口语搭子教学法）
│   ├── services/           # 自建服务（TTS、评分）
│   └── config.json         # nanobot 配置
├── docs/
│   ├── research/           # 市场调研（机构 + 竞品）
│   └── product/            # 产品形态与方向分析
├── .gitignore
└── README.md               # 本文件
```

## 快速开始

应用运行方式见 [`app/README.md`](app/README.md)。当前阻塞项：需要 `DEEPSEEK_API_KEY` 才能跑通对话。

## 项目背景

作者是一名备考新托福（2026 后改革版）的学生，同时是智能体开发者。目标先做自用的托福备考助手，后续扩展为产品。

## 工作成果

1. **市场调研**（`docs/research/`）：中国托福机构的「引流 → 诊断 → 转化 → 交付」链路，以及 AI native 学习搭子竞品（可栗/咕噜口语、Speak/ELSA、学而思小精龙、腾讯 LearnBuddy 等）。
2. **产品形态分析**（`docs/product/`）：确定「对话式智能体 + Skill 编排 + 语音优先」的产品形态，MVP 从「新托福口语搭子」起步。

## 关键决策

- 已定：AI native 搭子（非题库网站）、口语起步、CEFR 分级、nanobot 基座 + DeepSeek + 豆包 TTS + LightRAG。
- 待定：口语评分引擎选型、长期记忆方案、本地资料版权（商用需授权）。

## 下一步

做最小可玩原型（新托福口语复述题搭子闭环），自用验证教学法，再扩展。
