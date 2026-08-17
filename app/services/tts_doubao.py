"""豆包（火山引擎）TTS 封装。

把文字合成语音，返回音频字节。供 nanobot 口语搭子在 Phase 2 调用，
让 AI「开口说话」。

用法：
    python tts_doubao.py "要合成的文字" --out out.mp3
环境变量（见项目根 .env.example）：
    VOLCENGINE_APP_ID / VOLCENGINE_ACCESS_TOKEN / VOLCENGINE_CLUSTER
"""

from __future__ import annotations

import argparse
import json
import os
import uuid

import httpx

API_URL = "https://openspeech.bytedance.com/api/v1/tts"


def synthesize(text: str, voice_type: str = "zh_female_qingxinnvsheng_moon_bigtts") -> bytes:
    """合成语音，返回音频字节（mp3）。"""
    app_id = os.environ.get("VOLCENGINE_APP_ID", "")
    access_token = os.environ.get("VOLCENGINE_ACCESS_TOKEN", "")
    cluster = os.environ.get("VOLCENGINE_CLUSTER", "volcano_tts")

    if not app_id or not access_token:
        raise RuntimeError(
            "缺少 VOLCENGINE_APP_ID / VOLCENGINE_ACCESS_TOKEN 环境变量，"
            "请参考 .env.example 配置。"
        )

    payload = {
        "app": {"appid": app_id, "token": access_token, "cluster": cluster},
        "user": {"uid": "langmate"},
        "audio": {
            "voice_type": voice_type,
            "encoding": "mp3",
            "speed_ratio": 1.0,
        },
        "request": {"reqid": str(uuid.uuid4()), "text": text, "operation": "query"},
    }
    headers = {"Authorization": f"Bearer;{access_token}"}

    resp = httpx.post(API_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()

    data = resp.json()
    if data.get("code") not in (3000, 0):
        raise RuntimeError(f"火山 TTS 失败: code={data.get('code')} message={data.get('message')}")

    audio_b64 = data.get("data")
    if not audio_b64:
        raise RuntimeError("火山 TTS 返回为空")

    return __import__("base64").b64decode(audio_b64)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="豆包 TTS")
    parser.add_argument("text", help="要合成的文字")
    parser.add_argument("--out", default="out.mp3", help="输出文件路径")
    parser.add_argument("--voice", default="zh_female_qingxinnvsheng_moon_bigtts", help="音色")
    args = parser.parse_args()

    audio = synthesize(args.text, voice_type=args.voice)
    with open(args.out, "wb") as f:
        f.write(audio)
    print(f"已合成 {len(audio)} 字节到 {args.out}")
