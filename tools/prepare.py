"""把一本 txt 清洗、识别章节、切段。纯代码，不调用模型。

用法：
    python tools/prepare.py --input "某本书.txt" --out "books/某本书" \
        --title "书名" --author "作者" --mode literary --source-level A \
        --spoiler-policy no_ending --target-minutes 15
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path

CHINESE_NUM = "0-9０-９一二三四五六七八九十百千万零〇两"
CHAPTER_PATTERNS = [
    re.compile(rf"^\s*第\s*[{CHINESE_NUM}]+\s*[章节回卷部篇集].*$"),
    # 允许带副标题，如「前言　我的故事」「结论 获得持久成果的秘诀」
    re.compile(r"^\s*(?:序章|楔子|引子|前言|序言|引言|导言|尾声|后记|终章|大结局|番外|结论|附录|鸣谢)\s*(?:[:：　 ]\s*.*)?$"),
    re.compile(r"^\s*(?:CHAPTER|Chapter|chapter)\s+(?:[0-9]+|[IVXLCDM]+)\b.*$"),
    re.compile(r"^\s*(?:PART|Part|part)\s+(?:[0-9]+|[IVXLCDM]+)\b.*$"),
]
ENDNOTE_PATTERNS = [
    re.compile(r"^\s*(?:注释|尾注|参考书目|参考文献|引用文献)\s*[:：]?\s*$"),
]
SENTENCE_END = "。！？!?…"


def decode(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            text = data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        if encoding == "utf-16" and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
            continue
        if text.count("�") > 3:
            continue
        return text, encoding
    return data.decode("gb18030", errors="replace"), "gb18030(有替换字符)"


def strip_gutenberg(text: str) -> str:
    start = re.search(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", text, re.I)
    end = re.search(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", text, re.I)
    if start:
        text = text[start.end():]
    if end:
        text = text[: end.start()]
    return text


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    # epub 转换残留在章节标题之间的占位行
    text = re.sub(r"(?m)^\s*未知\s*$\n?", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return False
    return any(pattern.match(stripped) for pattern in CHAPTER_PATTERNS)


def heading_key(title: str) -> str:
    return re.sub(r"[\s　]+", "", title)


def body_end(text: str) -> int:
    """正文结束位置：跳过目录里靠前的「注释」，从后半段找尾注区。"""
    lines = text.splitlines(keepends=True)
    offset = 0
    for line in lines:
        if offset > len(text) * 0.5 and any(p.match(line.strip()) for p in ENDNOTE_PATTERNS):
            return offset
        offset += len(line)
    return len(text)


def looks_like_toc(front: str) -> bool:
    return "目录" in front or re.search(r"^\s*(?:Contents|CONTENTS|Table of Contents)\s*$", front, re.M) is not None


def chapters_of(text: str) -> list[tuple[str, int, int]]:
    text = text[: body_end(text)]
    lines = text.splitlines(keepends=True)
    starts: list[tuple[int, str]] = []
    offset = 0
    for line in lines:
        if is_heading(line):
            starts.append((offset, line.strip()))
        offset += len(line)
    if not starts:
        return [("全文", 0, len(text))]
    # 目录中的章节名会和正文重复（空格可能是半角或全角），只保留最后一次出现
    last_index: dict[str, int] = {}
    for index, (_, title) in enumerate(starts):
        last_index[heading_key(title)] = index
    starts = [item for index, item in enumerate(starts) if last_index[heading_key(item[1])] == index]
    result: list[tuple[str, int, int]] = []
    front = text[: starts[0][0]]
    if front.strip() and not looks_like_toc(front):
        result.append(("前言", 0, starts[0][0]))
    for index, (start, title) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(text)
        if end > start:
            result.append((title[:80], start, end))
    return result


def split_long(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    units: list[tuple[int, int]] = []
    cursor = start
    while cursor < end:
        target = min(end, cursor + max_chars)
        if target >= end:
            units.append((cursor, end))
            break
        window = text[max(cursor, target - 600): min(end, target + 600)]
        best = -1
        base = max(cursor, target - 600)
        for match in re.finditer(r"\n\s*\n|\n|[" + re.escape(SENTENCE_END) + r"]", window):
            pos = base + match.end()
            if best < 0 or abs(pos - target) < abs(best - target):
                best = pos
        cut = best if best > cursor else target
        units.append((cursor, cut))
        cursor = max(cursor + 1, cut)
    return units


def build_segments(text: str, chapters: list[tuple[str, int, int]], target: int, maximum: int) -> list[dict]:
    segments: list[dict] = []

    def flush(start: int, end: int, chapter: str) -> None:
        body = text[start:end].strip()
        if not body:
            return
        segments.append({
            "seg_id": f"seg-{len(segments) + 1:04d}",
            "ordinal": len(segments) + 1,
            "chapter": chapter,
            "start": start,
            "end": end,
            "chars": sum(1 for ch in body if not ch.isspace()),
            "text": body,
        })

    for chapter, chapter_start, chapter_end in chapters:
        cursor = chapter_start
        current_start: int | None = None
        current_end = chapter_start
        for para_start, para_end in split_paragraphs(text, chapter_start, chapter_end):
            for start, end in split_long(text, para_start, para_end, maximum):
                if current_start is None:
                    current_start, current_end = start, end
                elif end - current_start > maximum:
                    flush(current_start, current_end, chapter)
                    current_start, current_end = start, end
                else:
                    current_end = end
                if current_start is not None and current_end - current_start >= target:
                    flush(current_start, current_end, chapter)
                    current_start, current_end = None, chapter_end
        if current_start is not None:
            flush(current_start, current_end, chapter)
    return segments


def split_paragraphs(text: str, start: int, end: int) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    cursor = start
    for match in re.finditer(r"\n\s*\n+", text[start:end]):
        para_end = start + match.start()
        if para_end > cursor:
            result.append((cursor, para_end))
        cursor = start + match.end()
    if cursor < end:
        result.append((cursor, end))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="清洗、章节识别、切段（不调用模型）")
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--author", default="未标注")
    parser.add_argument("--mode", default="literary", choices=("literary", "narrative", "expository"),
                        help="expository=公众号听书/阅读；literary/narrative=视频口播")
    parser.add_argument("--channel", default="", choices=("", "video", "article"),
                        help="留空按 mode 自动判断：expository→article，其他→video")
    parser.add_argument("--completion", default="finished", choices=("finished", "serial"))
    parser.add_argument("--source-level", default="A", choices=("A", "B", "C"))
    parser.add_argument("--spoiler-policy", default="no_ending", choices=("no_ending", "main_ending_ok"))
    parser.add_argument("--target-minutes", type=float, default=15)
    parser.add_argument("--cpm", type=float, default=300, help="口播速度，字/分钟；暂定 300")
    parser.add_argument("--platform", default="", help="留空按 channel 自动填：微信公众号 / 抖音/B站")
    parser.add_argument("--brand", default="", help="账号名/签名，3–8 字；留空则结尾不写签名")
    parser.add_argument("--opening-mode", default="spoken", choices=("card", "spoken", "none"))
    parser.add_argument("--ending-mode", default="", choices=("", "both", "s6", "card", "none"),
                        help="留空按 channel 自动填：公众号 none，视频 both")
    parser.add_argument("--next-episode", default="", help="下期预告书名；没有就留空")
    parser.add_argument("--content-warning", default="", help="成人/敏感内容提示；留空不写")
    parser.add_argument("--content-warning-mode", default="description", choices=("spoken", "description", "none"))
    parser.add_argument("--segment-chars", type=int, default=1800)
    parser.add_argument("--segment-max", type=int, default=2500)
    args = parser.parse_args()

    source_path = Path(args.input).expanduser().resolve()
    if not source_path.is_file():
        print(f"找不到输入：{source_path}")
        return 2
    out = Path(args.out).expanduser().resolve()
    (out / "source").mkdir(parents=True, exist_ok=True)
    (out / "segments").mkdir(parents=True, exist_ok=True)
    (out / "notes").mkdir(parents=True, exist_ok=True)

    raw, encoding = decode(source_path)
    cleaned = normalize(strip_gutenberg(raw))
    chapters = chapters_of(cleaned)
    segments = build_segments(cleaned, chapters, max(500, args.segment_chars), max(800, args.segment_max))
    if not segments:
        print("没有切出任何分段。")
        return 3

    (out / "source" / "original.txt").write_text(cleaned, encoding="utf-8")
    with (out / "segments" / "index.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for segment in segments:
            row = {key: value for key, value in segment.items() if key != "text"}
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            (out / "segments" / f"{segment['seg_id']}.md").write_text(segment["text"] + "\n", encoding="utf-8")

    chars = sum(1 for ch in cleaned if not ch.isspace())
    title = args.title.strip() or source_path.stem
    spoiler = "no_ending" if args.completion == "serial" else args.spoiler_policy
    channel = args.channel or ("article" if args.mode == "expository" else "video")
    platform = args.platform.strip() or ("微信公众号" if channel == "article" else "抖音/B站")
    ending_mode = args.ending_mode or ("none" if channel == "article" else "both")
    meta = {
        "title": title,
        "author": args.author.strip() or "未标注",
        "mode": args.mode,
        "channel": channel,
        "completion": args.completion,
        "source_level": args.source_level,
        "spoiler_policy": spoiler,
        "quote_policy": "no_quotes" if args.source_level == "C" else "quotes",
        "target_minutes": args.target_minutes,
        "speech_rate_cpm": round(args.cpm, 1),
        "target_chars_full": round(args.target_minutes * args.cpm),
        "target_chars_addons": 200,
        "target_chars": max(500, round(args.target_minutes * args.cpm - 200)),
        "platform": platform,
        "brand": args.brand.strip(),
        "opening_mode": args.opening_mode,
        "ending_mode": ending_mode,
        "next_episode": args.next_episode.strip(),
        "content_warning": args.content_warning.strip(),
        "content_warning_mode": args.content_warning_mode,
        "ai_notice": True,
        "publish_required": True,
        "chars": chars,
        "chapters": len(chapters),
        "segments": len(segments),
        "segment_chars": args.segment_chars,
        "reading_mode": "full_text" if chars <= 120000 else "chunked",
        "encoding": encoding,
        "source_path": str(source_path),
        "source_sha256": hashlib.sha256(cleaned.encode("utf-8")).hexdigest(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "out": str(out),
        "title": title,
        "chars": chars,
        "chapters": len(chapters),
        "segments": len(segments),
        "reading_mode": meta["reading_mode"],
        "encoding": encoding,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
