"""有道智云语音评测（CAPT）封装。

接口：POST https://openapi.youdao.com/iseapi（form-urlencoded）
签名：sha256(appKey + input + salt + curtime + appSecret)，signType=v2
  其中 input = q前10字符 + q长度 + q后10字符（q 为音频 base64，长度>20 时）
文档：https://ai.youdao.com/DOCSIRMA/html/tts/api/yypc/index.html

音频要求：wav PCM 16kHz 16bit 单声道，≤120s。调用前请先经
services.pronunciation.audio.ensure_wav16k 转换。

返回维度（0-100 分）：pronunciation(准确度)/integrity(完整度)/fluency(流利度)，
音素级含重音(prominence/stress_detect)与纠错(calibration)信息。

环境变量：YOUDAO_APP_KEY / YOUDAO_APP_SECRET（见 app/.env.example）。
"""

from __future__ import annotations

import base64
import hashlib
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

API_URL = "https://openapi.youdao.com/iseapi"
TIMEOUT_S = 30.0


class PronunciationAssessmentError(RuntimeError):
    """有道评测调用失败（网络/鉴权/限流/内容无效等）。"""


@dataclass
class PhonemeResult:
    phoneme: str
    pronunciation: float          # 0-100
    correct: bool                 # judge
    calibration: str = ""         # 发错时实际发成了什么音
    prominence: float = 0.0       # 重音程度 0-100
    stress_ref: bool = False      # 标准答案是否应重读
    stress_detect: bool = False   # 用户实际是否重读


@dataclass
class WordResult:
    word: str
    ipa: str
    pronunciation: float          # 0-100
    phonemes: list[PhonemeResult] = field(default_factory=list)


@dataclass
class PronunciationReport:
    """结构化发音评测报告（喂给教学智能体的轨道 B 数据）。"""

    text: str                     # 评测参考文本
    overall: float                # 0-100 综合
    pronunciation: float          # 0-100 准确度
    fluency: float                # 0-100 流利度
    integrity: float              # 0-100 完整度
    speed: float                  # 语速（词/分钟）
    duration_s: float             # 音频时长（秒）
    words: list[WordResult] = field(default_factory=list)

    def problem_phonemes(self, threshold: float = 60.0) -> list[dict[str, Any]]:
        """提取发音问题音素（judge=false 或得分低于阈值）。"""
        problems: list[dict[str, Any]] = []
        for w in self.words:
            for p in w.phonemes:
                if not p.correct or p.pronunciation < threshold:
                    problems.append({
                        "word": w.word,
                        "phoneme": p.phoneme,
                        "score": p.pronunciation,
                        "heard_as": p.calibration,
                    })
        return problems

    def stress_issues(self) -> list[dict[str, Any]]:
        """提取重音问题：应重读未重读 / 不应重读却重读。"""
        issues: list[dict[str, Any]] = []
        for w in self.words:
            for p in w.phonemes:
                if p.stress_ref != p.stress_detect:
                    issues.append({
                        "word": w.word,
                        "phoneme": p.phoneme,
                        "should_stress": p.stress_ref,
                        "actually_stressed": p.stress_detect,
                    })
        return issues

    def to_prompt_dict(self) -> dict[str, Any]:
        """压缩成注入 LLM 上下文的结构（控制 token 体积）。"""
        return {
            "text": self.text,
            "scores_0_100": {
                "overall": self.overall,
                "pronunciation": self.pronunciation,
                "fluency": self.fluency,
                "integrity": self.integrity,
            },
            "speed_wpm": self.speed,
            "duration_s": self.duration_s,
            "weak_words": [
                {"word": w.word, "ipa": w.ipa, "score": w.pronunciation}
                for w in self.words if w.pronunciation < 60
            ],
            "problem_phonemes": self.problem_phonemes(),
            "stress_issues": self.stress_issues(),
        }


def _sign(app_key: str, q_b64: str, salt: str, curtime: str, app_secret: str) -> str:
    if len(q_b64) > 20:
        input_str = q_b64[:10] + str(len(q_b64)) + q_b64[-10:]
    else:
        input_str = q_b64
    raw = app_key + input_str + salt + curtime + app_secret
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_report(payload: dict[str, Any], text: str) -> PronunciationReport:
    def _f(key: str) -> float:
        try:
            return float(payload.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    def _pf(p: dict[str, Any], key: str) -> float:
        """音素/词级字段安全转 float：有道偶发返回 "N/A" 等非数值，
        单字段解析失败置 0，不让整份报告降级成纯文字模式。"""
        try:
            return float(p.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    words: list[WordResult] = []
    for w in payload.get("words") or []:
        phonemes = [
            PhonemeResult(
                phoneme=str(p.get("phoneme") or ""),
                pronunciation=_pf(p, "pronunciation"),
                correct=bool(p.get("judge", True)),
                calibration=str(p.get("calibration") or ""),
                prominence=_pf(p, "prominence"),
                stress_ref=bool(p.get("stress_ref", False)),
                stress_detect=bool(p.get("stress_detect", False)),
            )
            for p in (w.get("phonemes") or [])
        ]
        words.append(WordResult(
            word=str(w.get("word") or ""),
            ipa=str(w.get("IPA") or ""),
            pronunciation=_pf(w, "pronunciation"),
            phonemes=phonemes,
        ))

    return PronunciationReport(
        text=text,
        overall=_f("overall"),
        pronunciation=_f("pronunciation"),
        fluency=_f("fluency"),
        integrity=_f("integrity"),
        speed=_f("speed"),
        duration_s=_f("end") - _f("start"),
        words=words,
    )


async def score_pronunciation(
    wav_path: str | Path,
    text: str,
    *,
    lang_type: str = "en",
) -> PronunciationReport:
    """对 wav 音频做发音评测，返回结构化报告。

    Args:
        wav_path: 已转为 16kHz 单声道 wav 的音频路径
                  （请先用 services.pronunciation.audio.ensure_wav16k 处理）。
        text: 评测参考文本。复述题传原文；互动面试等自由作答
              传 ASR 转写文本（近似评测，完整度维度会失真）。
        lang_type: en / zh-CHS。

    Raises:
        PronunciationAssessmentError: 鉴权缺失、网络错误或评测失败。
    """
    app_key = os.environ.get("YOUDAO_APP_KEY", "")
    app_secret = os.environ.get("YOUDAO_APP_SECRET", "")
    if not app_key or not app_secret:
        raise PronunciationAssessmentError(
            "缺少 YOUDAO_APP_KEY / YOUDAO_APP_SECRET 环境变量，"
            "请按 app/.env.example 配置有道智云语音评测应用凭证。"
        )

    audio_bytes = Path(wav_path).read_bytes()
    q_b64 = base64.b64encode(audio_bytes).decode("ascii")
    salt = str(uuid.uuid4())
    curtime = str(int(time.time()))

    form = {
        "q": q_b64,
        "text": text,
        "langType": lang_type,
        "appKey": app_key,
        "salt": salt,
        "curtime": curtime,
        "signType": "v2",
        "sign": _sign(app_key, q_b64, salt, curtime, app_secret),
        "format": "wav",
        "rate": "16000",
        "channel": "1",
        "type": "1",
    }

    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        resp = await client.post(API_URL, data=form)
        resp.raise_for_status()
        payload = resp.json()

    error_code = str(payload.get("errorCode", ""))
    if error_code != "0":
        raise PronunciationAssessmentError(
            f"有道语音评测失败: errorCode={error_code} "
            f"requestId={payload.get('requestId', '')}"
        )

    return _parse_report(payload, text)
