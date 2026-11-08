"""按目标分钟数重算字数预算（按目标口播速度，不按固定 250 字/分钟）。

用法：
    python tools/set_target.py --book "books/羊脂球" --minutes 15
    python tools/set_target.py --book "books/羊脂球" --audio "D:\\...\\羊脂球.wav"
    python tools/set_target.py --book "books/羊脂球" --audio "羊脂球.wav" --minutes 15

说明：
    - 默认口播速度 300 字/分钟（暂定）。
    - 目标字数按 target_minutes × cpm 线性算。
    - 另扣 200 字给品牌口播/内容提示/S6，剩的是 S1–S5 主体预算。
    - 如果换声音、换语速，用 --audio + 已有 final.txt 重新标定。
"""

from __future__ import annotations

import argparse
import json
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CPM = 300.0
ADDON_CHARS = 200


def count_chars(text: str) -> int:
    return sum(1 for char in text if not char.isspace())


def audio_minutes(path: Path) -> float:
    if path.suffix.lower() != ".wav":
        raise ValueError("标定只支持 wav；其他格式先转 wav")
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate() / 60


def main() -> int:
    parser = argparse.ArgumentParser(description="按目标分钟数重算字数预算")
    parser.add_argument("--book", required=True)
    parser.add_argument("--minutes", type=float, default=0, help="目标口播分钟数；不给就用 meta")
    parser.add_argument("--cpm", type=float, default=0, help="字/分钟；不给就用 meta 或 300")
    parser.add_argument("--audio", default="", help="可选：用已有 wav + final.txt 标定 cpm")
    parser.add_argument("--script", default="", help="标定用的稿子；默认 final.txt")
    args = parser.parse_args()

    book = Path(args.book)
    if not book.is_absolute():
        book = (ROOT / book).resolve()
    meta_path = book / "meta.json"
    if not meta_path.is_file():
        print(f"找不到 meta.json：{meta_path}")
        return 2
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))

    cpm = args.cpm or float(meta.get("speech_rate_cpm") or DEFAULT_CPM)
    if args.audio:
        audio = Path(args.audio).expanduser()
        if not audio.is_absolute():
            audio = (Path.cwd() / audio).resolve()
        script = Path(args.script).expanduser() if args.script else book / "final.txt"
        if not script.is_absolute():
            inside = book / script
            script = inside if inside.is_file() else (Path.cwd() / script)
        if not script.is_file():
            print(f"标定需要稿子：{script}")
            return 2
        chars = count_chars(script.read_text(encoding="utf-8-sig"))
        minutes_audio = audio_minutes(audio)
        if minutes_audio <= 0:
            print("音频时长读不到。")
            return 2
        cpm = chars / minutes_audio
        print(f"标定：{chars} 字 / {minutes_audio:.3f} 分钟 = {cpm:.1f} 字/分钟")

    minutes = args.minutes or float(meta.get("target_minutes") or 15)
    full_chars = round(minutes * cpm)
    main_chars = max(500, full_chars - ADDON_CHARS)
    meta.update({
        "target_minutes": round(minutes, 2),
        "speech_rate_cpm": round(cpm, 1),
        "target_chars_full": full_chars,
        "target_chars_addons": ADDON_CHARS,
        "target_chars": main_chars,
    })
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n目标：{minutes:g} 分钟 × {cpm:.1f} 字/分钟 = {full_chars} 字（完整 final.txt）")
    print(f"主体 S1–S5：{main_chars} 字（扣掉约 {ADDON_CHARS} 字品牌/提示/S6）")
    print("建议分段：")
    for slot, ratio in (("S1", 0.05), ("S2", 0.12), ("S3", 0.28), ("S4", 0.33), ("S5", 0.22)):
        print(f"  {slot}: {round(main_chars * ratio)} 字")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
