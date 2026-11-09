"""Edge TTS worker and content-addressed audio cache (no GUI dependency)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path

from lingua.materials import digest
from lingua.storage import _write_json_atomic


def audio_key(text: str, voice: str, rate: str) -> str:
    if not text.strip() or not re.fullmatch(r"[a-z]{2,3}-(?:[A-Za-z0-9]+-)+[A-Za-z0-9]+Neural", voice):
        raise ValueError("請輸入有效的 Edge 語音名稱，例如 en-US-AriaNeural")
    if not re.fullmatch(r"[+-]\d{1,2}%", rate):
        raise ValueError("語速格式應為 +0%、-20% 等（使用半形 %）")
    return digest([text, voice, rate])


def cached_audio(root: Path, text: str, voice: str, rate: str):
    key = audio_key(text, voice, rate)
    audio, metadata = root / f"{key}.mp3", root / f"{key}.json"
    try:
        data = json.loads(metadata.read_text(encoding="utf-8"))
        if not audio.stat().st_size or data["request"] != [text, voice, rate] or data["sha256"] != hashlib.sha256(audio.read_bytes()).hexdigest():
            return None
        boundaries = data["boundaries"]
        if not isinstance(boundaries, list):
            return None
        previous = -1
        for item in boundaries:
            if not (isinstance(item, dict) and isinstance(item.get("start"), (int, float))
                    and isinstance(item.get("end"), (int, float)) and math.isfinite(item["end"])
                    and 0 <= item["start"] <= item["end"] and item["start"] >= previous):
                return None
            previous = item["start"]
        return audio, boundaries
    except (OSError, ValueError, KeyError, TypeError):
        return None


async def synthesize(root: Path, text: str, voice: str, rate: str):
    import edge_tts

    key = audio_key(text, voice, rate)
    cached = cached_audio(root, text, voice, rate)
    if cached:
        return cached
    root.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".speech-", suffix=".tmp", dir=root)
    temporary = Path(name)
    boundaries = []
    try:
        with os.fdopen(descriptor, "wb") as output:
            async with asyncio.timeout(90):
                async for chunk in edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary").stream():
                    if chunk["type"] == "audio":
                        output.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        boundaries.append({"start": chunk["offset"] / 10000,
                                           "end": (chunk["offset"] + chunk["duration"]) / 10000})
        if not temporary.stat().st_size:
            raise RuntimeError("TTS 未傳回音訊")
        sha = hashlib.sha256(temporary.read_bytes()).hexdigest()
        os.replace(temporary, root / f"{key}.mp3")
        _write_json_atomic(root / f"{key}.json", {"request": [text, voice, rate], "sha256": sha, "boundaries": boundaries})
    finally:
        temporary.unlink(missing_ok=True)
    return cached_audio(root, text, voice, rate)


async def _worker(request):
    for text in request["texts"]:
        await synthesize(Path(request["root"]), text, request["voice"], request["rate"])


if __name__ == "__main__":
    try:
        asyncio.run(_worker(json.load(sys.stdin)))
    except Exception as error:
        print(str(error) or type(error).__name__, file=sys.stderr)
        sys.exit(1)
