# -*- coding: utf-8 -*-
"""Generate markdown report from deep-research JSON results.
No third-party dependencies; parses the local fields.yaml subset used by this project.
"""
from pathlib import Path
import json
import re

BASE = Path(__file__).resolve().parent
FIELDS_PATH = BASE / "fields.yaml"
RESULTS_DIR = BASE / "results"
REPORT_PATH = BASE / "report.md"

TOC_FIELDS = ["entity_type", "current_status_2026", "primary_surface", "ai_scoring"]
INTERNAL_KEYS = {"_source_file", "uncertain"}
SPECIAL_SECTIONS = ["summary", "facts", "analysis", "recommendations", "sources", "uncertainty"]


def unquote(s: str) -> str:
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


def parse_fields():
    text = FIELDS_PATH.read_text(encoding="utf-8")
    categories = []
    uncertain = []
    in_categories = False
    in_uncertain = False
    current_cat = None
    current_field = None

    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("field_categories:"):
            in_categories = True
            continue
        if line.startswith("uncertain:"):
            in_categories = False
            in_uncertain = True
            continue
        if line.startswith("result_schema:"):
            in_uncertain = False
            continue

        if in_categories:
            m_cat = re.match(r"^\s{2}-\s*category:\s*(.+?)\s*$", line)
            if m_cat:
                current_cat = {"category": unquote(m_cat.group(1)), "fields": []}
                categories.append(current_cat)
                current_field = None
                continue
            m_name = re.match(r"^\s{6}-\s*name:\s*(.+?)\s*$", line)
            if m_name and current_cat is not None:
                current_field = {"name": unquote(m_name.group(1)), "description": "", "detail_level": ""}
                current_cat["fields"].append(current_field)
                continue
            m_desc = re.match(r"^\s{8}description:\s*(.+?)\s*$", line)
            if m_desc and current_field is not None:
                current_field["description"] = unquote(m_desc.group(1))
                continue
            m_detail = re.match(r"^\s{8}detail_level:\s*(.+?)\s*$", line)
            if m_detail and current_field is not None:
                current_field["detail_level"] = unquote(m_detail.group(1))
                continue

        if in_uncertain:
            m_unc = re.match(r"^\s{2}-\s*(.+?)\s*$", line)
            if m_unc:
                uncertain.append(unquote(m_unc.group(1)))

    known_fields = {f["name"] for c in categories for f in c["fields"]}
    return categories, set(uncertain), known_fields


def load_results():
    files = sorted(RESULTS_DIR.glob("*.json"))
    items = []
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as exc:
            data = {"summary": f"读取失败：{exc}", "uncertain": []}
        data["_source_file"] = fp.name
        items.append(data)
    return items


def find_value(data, field_name):
    if field_name in data:
        return data.get(field_name)
    for v in data.values():
        if isinstance(v, dict) and field_name in v:
            return v.get(field_name)
    return None


def contains_uncertain(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == "" or "[不确定]" in value
    try:
        return "[不确定]" in json.dumps(value, ensure_ascii=False)
    except Exception:
        return False


def short_value(value, limit=56):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    value = re.sub(r"\s+", " ", str(value)).strip()
    if len(value) > limit:
        return value[:limit] + "…"
    return value


def format_value(value, indent=0):
    pad = "  " * indent
    if value is None:
        return ""
    if isinstance(value, list):
        if not value:
            return ""
        if all(isinstance(x, dict) for x in value):
            lines = []
            for x in value:
                kv = " | ".join(f"{k}: {short_value(v, 80)}" for k, v in x.items())
                lines.append(f"{pad}- {kv}")
            return "\n".join(lines)
        if len(value) <= 6 and all(not isinstance(x, (dict, list)) for x in value):
            return "、".join(short_value(x, 40) for x in value)
        return "\n".join(f"{pad}- {format_value(x, 0)}" for x in value)
    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}- **{k}**:")
                lines.append(format_value(v, indent + 1))
            else:
                lines.append(f"{pad}- **{k}**: {short_value(v, 120)}")
        return "\n".join(lines)
    text = str(value).strip()
    if len(text) > 140:
        text = text.replace("。", "。<br>")
    return text


def anchor_for(index, data):
    name = data.get("entity_name") or data.get("name") or data.get("_source_file", f"item-{index}")
    return f"item-{index:02d}", str(name)


def main():
    categories, uncertain_from_fields, known_fields = parse_fields()
    items = load_results()
    lines = []

    lines.append("# 中国托福培训机构产品形态与用户交互阶段性调研报告")
    lines.append("")
    lines.append("> 范围说明：本报告基于已完成的第 1 批 5 个对象（新东方/新东方在线、新航道、新通教育、学而思国际/原考满分、小站教育）以及一次联网补充扫描。用户已决定停止后续深挖，因此本报告是**阶段性结论**，不是完整市场终稿。")
    lines.append("")
    lines.append("> 证据规则：JSON 中标注 `[不确定]` 或列入 `uncertain` 的字段已在本报告中跳过；剩余内容仍可能包含机构自述、软文或第三方估计，决策前需做 primary-source 核验。")
    lines.append("")

    # TOC
    lines.append("## 目录")
    lines.append("")
    for idx, data in enumerate(items, start=1):
        anchor, name = anchor_for(idx, data)
        uncertain_set = set(data.get("uncertain") or []) | uncertain_from_fields
        parts = []
        for field in TOC_FIELDS:
            if field in uncertain_set:
                continue
            value = find_value(data, field)
            if contains_uncertain(value):
                continue
            sv = short_value(value)
            if sv:
                parts.append(f"{field}: {sv}")
        suffix = " | " + " | ".join(parts) if parts else ""
        lines.append(f"{idx}. [{name}](#{anchor}){suffix}")
    lines.append("")

    # Details
    for idx, data in enumerate(items, start=1):
        anchor, name = anchor_for(idx, data)
        uncertain_set = set(data.get("uncertain") or []) | uncertain_from_fields
        lines.append(f"## {idx}. {name}")
        lines.append(f'<a id="{anchor}"></a>')
        lines.append("")
        lines.append(f"- 结果文件：`results/{data.get('_source_file', '')}`")
        if data.get("uncertain"):
            lines.append("- 不确定字段：" + "、".join(data.get("uncertain") or []))
        lines.append("")

        # Special sections first if present
        for sec in SPECIAL_SECTIONS:
            value = data.get(sec)
            if contains_uncertain(value):
                continue
            formatted = format_value(value)
            if formatted:
                lines.append(f"### {sec}")
                lines.append(formatted)
                lines.append("")

        # Defined fields by category
        lines.append("### 字段详情")
        lines.append("")
        for cat in categories:
            cat_lines = []
            for field in cat["fields"]:
                fname = field["name"]
                if fname in uncertain_set:
                    continue
                value = find_value(data, fname)
                if contains_uncertain(value):
                    continue
                formatted = format_value(value)
                if not formatted:
                    continue
                cat_lines.append(f"**{fname}**：{formatted}")
            if cat_lines:
                lines.append(f"#### {cat['category']}")
                lines.append("")
                lines.extend(cat_lines)
                lines.append("")

        # Extra fields
        extras = []
        for k, v in data.items():
            if k in INTERNAL_KEYS or k in SPECIAL_SECTIONS or k in known_fields:
                continue
            if k in uncertain_set or contains_uncertain(v):
                continue
            formatted = format_value(v)
            if formatted:
                extras.append(f"**{k}**：{formatted}")
        if extras:
            lines.append("### 其他信息")
            lines.append("")
            lines.extend(extras)
            lines.append("")

    lines.append("## 阶段性综合判断")
    lines.append("")
    lines.append("- **主流形态**：传统头部仍以课程交付为核心，但普遍用免费题库、模考、测评报告和 App 做前置获客；线下/OMO 侧强调学管、助教、主讲的多师督学。")
    lines.append("- **AI 落地深度不均**：新通、学而思国际/考满分更接近平台化与工具化；新东方/新航道强在品牌、课程与官方叙事；小站教育暴露了重销售轻交付与 AI 能力浅的风险。")
    lines.append("- **对智能体助手的机会**：差异化不应再做一个“题库+课程销售入口”，而应做可信的即时反馈闭环：基线诊断、可解释评分、错题到微课/练习的自动衔接、过程数据驱动的下一步建议。")
    lines.append("- **关键风险**：评分权威性、题源合规、保分/提分承诺、顾问式强转化都会伤害信任；学生自用智能体应优先保证透明、可复核、低打扰。")
    lines.append("")
    lines.append("## Limitations & Decision Conditions")
    lines.append("")
    lines.append("This analysis is decision support based on the available evidence and stated assumptions. It is not a substitute for primary customer research, financial or legal due diligence, or professional investment advice. Market conditions, platform rules, costs, and regulations can change; verify decision-critical inputs before committing capital.")
    lines.append("")
    lines.append("- 未完成对象：学为贵、启德考培、啄木鸟教育、ETS 官方 TestReady/TOEFL Go!、多次元/LingoLeap/海外 AI 工具尚未逐项深挖；相关判断只来自联网补充扫描，置信度低于已完成的 5 个对象。")
    lines.append("- 下一步最便宜验证：用 5-10 名目标用户做 30 分钟可用性测试，验证“即时口写反馈 + 下一步练习推荐”是否比传统报告更能提升次日留存与练习完成率。")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(f"Items: {len(items)}")


if __name__ == "__main__":
    main()
