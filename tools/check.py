"""程序化检查：引文是否在原文、字段是否齐全、稿子是否合规。

用法：
    python tools/check.py --book "books/某本书" --stage notes
    python tools/check.py --book "books/某本书" --stage outline
    python tools/check.py --book "books/某本书" --stage draft
    python tools/check.py --book "books/某本书" --stage final
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

DEFAULT_CPM = 300.0
MARKERS = re.compile(r"[\[\]【】（）()/|]")
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")
FACT_ID = re.compile(r"\bseg-\d{4}\b")
QUOTE = re.compile(r"[“「]([^”」]{1,120})[”」]")
SELF_INTRO = re.compile(r"^\s*(大家好|今天给大家|欢迎来到|这里是|我是|各位听众)")
FORBIDDEN = {
    "literary": ["首先", "其次", "综上所述", "不得不说", "在这个快节奏的时代", "让我们一起", "众所周知", "值得一提的是"],
    "narrative": ["话不多说", "直接上干货", "接下来就是", "一波操作", "简直了", "燃爆了", "封神", "yyds"],
    "expository": ["综上所述", "本章将", "本节将", "由此可见", "不得不说", "众所周知", "让我们一起", "相信大家"],
    "general": ["令人震惊的是", "万万没想到", "命运的齿轮开始转动", "不禁让人", "值得我们深思"],
}
MORAL = ["告诉我们", "让我们明白", "人生道理", "其实我们", "收获", "感悟", "值得我们深思"]
STYLE_HINTS = ["天没亮", "几钟头", "数小时", "随即", "此时", "此前", "该军官", "其目的",
               "未进食", "前一日", "话音未落", "与此同时", "尚未", "并未", "颇为", "皆是",
               "此举", "该车", "该女子"]
# 公众号是公开文章：这些词多半是写稿人的职业/技术栈，出现就提示人工确认
PERSONAL_HINTS = ["座舱 Linux", "座舱Linux", "驱动文档", "格科微", "触控", "嵌入式",
                  "二〇二七年跳", "2027年跳", "AE工程师"]
STRONG_ENDING = ["结局是", "故事的结局", "最终结局", "大结局", "最后他离开", "最后她离开", "最后他们离开",
                 "最后他走了", "最后她走了", "最后他们走了", "最后他上船", "最后她上船", "最后他们上船"]


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    text = path.read_text(encoding="utf-8-sig").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    if start > 0:
        text = text[start:]
    return json.loads(text)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"\s+", "", text)
    table = {"＂": '"', "＇": "'", "，": ",", "。": ".", "！": "!", "？": "?", "：": ":", "；": ";",
             "（": "(", "）": ")", "【": "[", "】": "]", "《": "<", "》": ">", "、": ",", "—": "-",
             "–": "-", "～": "~", "…": "..."}
    text = "".join(table.get(ch, ch) for ch in text).lower()
    for quote in ('"', "'", "“", "”", "‘", "’", "「", "」", "『", "』"):
        text = text.replace(quote, "")
    return text


def count_chars(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?…])|\n+", text)
    return [part.strip() for part in parts if part and part.strip()]


def issue(message: str, sentence: str = "") -> dict:
    return {"message": message, "sentence": sentence[:300]}


def check(name: str, level: str, summary: str, issues: list[dict] | None = None) -> dict:
    return {"name": name, "level": level, "summary": summary, "issues": issues or []}


def load_book(book: Path) -> tuple[dict, str, list[dict]]:
    meta = read_json(book / "meta.json")
    source = read_text(book / "source" / "original.txt")
    segments = []
    index = book / "segments" / "index.jsonl"
    if index.is_file():
        for line in index.read_text(encoding="utf-8").splitlines():
            if line.strip():
                segments.append(json.loads(line))
    return meta, source, segments


def segment_ranges(segments: list[dict]) -> dict[str, tuple[int, int]]:
    return {str(seg["seg_id"]): (int(seg["start"]), int(seg["end"])) for seg in segments if "seg_id" in seg}


def book_mode(book: Path) -> str:
    """读 meta.json 的 mode；读不到按小说处理，保持旧行为不变。"""
    try:
        return str(read_json(book / "meta.json").get("mode") or "literary")
    except Exception:  # noqa: BLE001
        return "literary"


def channel_of(meta: dict) -> str:
    """article=公众号听书/阅读；video=抖音/B站。旧 meta 没 channel 时按 mode 推。"""
    channel = str(meta.get("channel") or "").strip()
    if channel in {"article", "video"}:
        return channel
    return "article" if str(meta.get("mode") or "") == "expository" else "video"


def base_title(meta: dict) -> str:
    """去到期号后缀，便于在正文里匹配《书名》。"""
    title = str(meta.get("title") or "").strip()
    return re.sub(r"-\d+$", "", title)


def check_notes(book: Path, source: str, segments: list[dict]) -> list[dict]:
    checks = []
    path = book / "notes" / "beat_sheet.json"
    try:
        data = read_json(path)
    except Exception as exc:  # noqa: BLE001
        return [check("精读笔记", "fail", f"读不到 notes/beat_sheet.json：{exc}")]

    if book_mode(book) == "expository":
        missing = [key for key in ("core_claim", "problem", "chapters", "concepts", "applications", "actionable")
                   if key not in data]
        if missing:
            checks.append(check("笔记字段", "fail", f"缺少字段：{', '.join(missing)}"))
        else:
            checks.append(check("笔记字段", "pass", "非虚构字段齐全"))
        chapters = data.get("chapters") if isinstance(data.get("chapters"), list) else []
        if len(chapters) < 3:
            checks.append(check("章节覆盖", "fail", f"只有 {len(chapters)} 章，至少 3 章"))
        else:
            checks.append(check("章节覆盖", "pass", f"{len(chapters)} 章"))
        concepts = data.get("concepts") if isinstance(data.get("concepts"), list) else []
        checks.append(check("核心概念", "pass" if len(concepts) >= 3 else "hint", f"{len(concepts)} 个概念"))
        apps = data.get("applications") if isinstance(data.get("applications"), list) else []
        checks.append(check("迁移点", "pass" if len(apps) >= 2 else "hint", f"{len(apps)} 条迁移"))
        quote_issues = []
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            candidates = chapter.get("quote_candidates")
            if not isinstance(candidates, list):
                continue
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                quote = str(candidate.get("text") or "")
                if len(quote) > 50:
                    quote_issues.append(issue(f"引文候选 {len(quote)} 字，超过 50 字", quote))
        checks.append(check("引文候选", "fail" if quote_issues else "pass",
                            f"{len(quote_issues)} 条引文超过 50 字" if quote_issues else "引文候选都 ≤50 字",
                            quote_issues))
        return checks

    missing = [key for key in ("logline", "characters", "scenes", "arc", "threads", "themes") if key not in data]
    if missing:
        checks.append(check("精读笔记字段", "fail", f"缺少字段：{', '.join(missing)}"))
    scenes = data.get("scenes") if isinstance(data.get("scenes"), list) else []
    if not 6 <= len(scenes) <= 8:
        checks.append(check("关键场景数量", "fail", f"要求 6–8 个，实际 {len(scenes)} 个"))
    else:
        checks.append(check("关键场景数量", "pass", f"{len(scenes)} 个"))
    ranges = segment_ranges(segments)
    bad_quotes = []
    bad_segments = []
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        quote = str(scene.get("quote") or "").strip()
        seg_id = str(scene.get("segment_id") or "").strip()
        if not quote or norm(quote) not in norm(source):
            bad_quotes.append(issue(f"第 {index + 1} 个场景的引文在原文里找不到", quote))
            continue
        if seg_id not in ranges:
            bad_segments.append(issue(f"第 {index + 1} 个场景的 segment_id 不存在：{seg_id}", quote))
            continue
        start, end = ranges[seg_id]
        position = source.find(quote)
        if position >= 0 and not (start <= position < end):
            bad_segments.append(issue(f"第 {index + 1} 个场景的引文不在 {seg_id} 范围内", quote))
    checks.append(check("场景引文可核", "fail" if bad_quotes else "pass",
                        f"{len(bad_quotes)} 条引文找不到" if bad_quotes else "全部引文可在原文中逐字找到", bad_quotes))
    checks.append(check("场景段落编号", "fail" if bad_segments else "pass",
                        f"{len(bad_segments)} 条 segment_id 不对" if bad_segments else "segment_id 全部有效", bad_segments))
    characters = data.get("characters") if isinstance(data.get("characters"), list) else []
    checks.append(check("人物表", "pass" if len(characters) >= 3 else "fail", f"{len(characters)} 个人物"))
    return checks


def check_outline(book: Path, segments: list[dict]) -> list[dict]:
    checks = []
    try:
        data = read_json(book / "outline.json")
    except Exception as exc:  # noqa: BLE001
        return [check("大纲", "fail", f"读不到 outline.json：{exc}")]
    sections = data.get("sections") if isinstance(data.get("sections"), list) else []
    slots = [str(sec.get("slot") or "") for sec in sections if isinstance(sec, dict)]
    mode = book_mode(book)
    if mode == "expository":
        expected = ["S1", "S2", "S3", "S4", "S5"]
        missing = [slot for slot in expected if slot not in slots]
        checks.append(check("五段大纲", "fail" if missing else "pass",
                            f"缺少：{', '.join(missing)}" if missing else "S1–S5 齐全"))
    else:
        expected = ["S1", "S2", "S3", "S4", "S5", "S6"]
        missing = [slot for slot in expected if slot not in slots]
        checks.append(check("六段大纲", "fail" if missing else "pass",
                            f"缺少：{', '.join(missing)}" if missing else "S1–S6 齐全"))
    seg_ids = set(segment_ranges(segments))
    bad_refs = []
    points_total = 0
    for section in sections:
        if not isinstance(section, dict):
            continue
        points = section.get("points") if isinstance(section.get("points"), list) else []
        points_total += len(points)
        for point in points:
            if not isinstance(point, dict):
                continue
            refs = point.get("source_refs") if isinstance(point.get("source_refs"), list) else []
            if not refs:
                # S2 允许引用 background.md，不强制 segment_id
                if section.get("slot") == "S2" and str(point.get("source") or "").startswith("background.md"):
                    continue
                # 非虚构的迁移/推论/批判不是书内事实，允许不挂原文段落
                if mode == "expository" and str(point.get("type") or "") in {"application", "inference", "critique"}:
                    continue
                bad_refs.append(issue(f"{section.get('slot')} 有要点没有 source_refs", str(point.get("text") or "")))
            for ref in refs:
                if str(ref) not in seg_ids:
                    bad_refs.append(issue(f"{section.get('slot')} 的引用不存在：{ref}", str(point.get("text") or "")))
    checks.append(check("大纲引用", "fail" if bad_refs else "pass",
                        f"{len(bad_refs)} 处引用问题" if bad_refs else f"{points_total} 个要点都有段落引用", bad_refs))
    if "claim" not in data or not str(data.get("claim") or "").strip():
        checks.append(check("一句话主张", "fail", "缺少 claim"))
    else:
        checks.append(check("一句话主张", "pass", "有 claim"))
    if "hook_type" not in data or not str(data.get("hook_type") or "").strip():
        checks.append(check("钩子类型", "fail", "缺少 hook_type"))
    else:
        checks.append(check("钩子类型", "pass", str(data.get("hook_type"))))

    has_background_file = (book / "background.md").is_file()
    background = data.get("background") if isinstance(data.get("background"), dict) else None
    if background is None:
        level = "hint"
        checks.append(check("背景资料", level,
                            "有 background.md，但 outline 没写 background" if has_background_file
                            else "没有 background.md；S2 只讲书内信息"))
    else:
        mode = str(background.get("mode") or "")
        bg_issues = []
        if has_background_file and mode != "full":
            bg_issues.append(issue("有 background.md，但 background.mode 不是 full", mode))
        if not has_background_file and mode == "full":
            bg_issues.append(issue("没有 background.md，却写了 full；作者背景可能编造", mode))
        for key in ("author", "creation", "era"):
            items = background.get(key) if isinstance(background.get(key), list) else []
            for item in items:
                if isinstance(item, dict) and not str(item.get("source") or "").strip():
                    bg_issues.append(issue(f"background.{key} 有事实没写 source", str(item.get("text") or "")[:60]))
        checks.append(check("背景资料", "hint" if bg_issues else "pass",
                            "背景有来源问题" if bg_issues else f"mode={mode or '未写'}", bg_issues))

    character_map = data.get("character_map") if isinstance(data.get("character_map"), list) else []
    if character_map and mode != "expository":
        map_issues = []
        if len(character_map) > 6:
            map_issues.append(issue(f"人物地图 {len(character_map)} 人，最多 6 人"))
        for person in character_map:
            if not isinstance(person, dict):
                continue
            if not str(person.get("name") or "").strip():
                map_issues.append(issue("人物地图有人缺少 name"))
            if not str(person.get("identity") or "").strip():
                map_issues.append(issue("人物地图有人缺少 identity", str(person.get("name") or "")))
            if not str(person.get("feature") or "").strip():
                map_issues.append(issue("人物地图有人缺少 feature", str(person.get("name") or "")))
            refs = person.get("source_refs") if isinstance(person.get("source_refs"), list) else []
            if not refs:
                map_issues.append(issue("人物地图有人没有 source_refs", str(person.get("name") or "")))
            for ref in refs:
                if str(ref) not in seg_ids:
                    map_issues.append(issue("人物地图引用不存在", f"{person.get('name')} -> {ref}"))
        checks.append(check("人物地图", "hint" if map_issues else "pass",
                            "人物地图需要修" if map_issues else f"{len(character_map)} 人", map_issues))

    if mode == "expository":
        exp_issues = []
        if not str(data.get("one_thing") or "").strip():
            exp_issues.append(issue("缺少 one_thing：这一期只解决的一件事"))
        if not str(data.get("action") or "").strip():
            exp_issues.append(issue("缺少 action：听完做一件事"))
        if not str(data.get("application") or "").strip():
            exp_issues.append(issue("缺少 application：怎么落到听众处境"))
        checks.append(check("非虚构要素", "fail" if exp_issues else "pass",
                            f"{len(exp_issues)} 处缺失" if exp_issues else "one_thing / action / application 齐全",
                            exp_issues))
    return checks


def check_draft_text(meta: dict, text: str, audit: dict | None, *, final: bool) -> list[dict]:
    checks = []
    chars = count_chars(text)
    cpm = float(meta.get("speech_rate_cpm") or DEFAULT_CPM)
    minutes = round(chars / cpm, 1)
    target = float(meta.get("target_minutes") or 15)
    if 10 <= minutes <= 25:
        level = "pass" if abs(minutes - target) < 3 else "hint"
        checks.append(check("时长", level, f"按 {cpm:.0f} 字/分钟估算约 {minutes} 分钟；目标 {target:g} 分钟"))
    else:
        checks.append(check("时长", "fail",
                            f"按 {cpm:.0f} 字/分钟估算约 {minutes} 分钟，不在 10–25 分钟；"
                            f"目标 {target:g} 分钟约需 {round(target * cpm)} 字"))
    parts = sentences(text)
    opening = "".join(parts[:3])
    structure = []
    if SELF_INTRO.search(opening):
        structure.append(issue("开头先自我介绍了", parts[0] if parts else ""))
    if len(opening) < 20:
        structure.append(issue("前 3 句太短，听不出具体信息", opening))
    if text.strip() and text.strip()[-1] not in "。！？!?…":
        structure.append(issue("结尾没有收住", text.strip()[-40:]))
    checks.append(check("结构", "hint" if structure else "pass",
                        "开头/收束需要人工判断" if structure else "开头有具体信息，结尾有收束", structure))
    marker_count = text.count("<!-- S1_END -->")
    if marker_count == 0:
        checks.append(check("S1 分段标记", "hint", "没有 <!-- S1_END -->；Step 5 只能把品牌口播插在第一段后"))
    elif marker_count > 1:
        checks.append(check("S1 分段标记", "fail", f"<!-- S1_END --> 出现 {marker_count} 次，只能有 1 次"))
    else:
        checks.append(check("S1 分段标记", "pass", "有 1 个 S1_END"))
    language = []
    for match in MARKERS.finditer(text):
        language.append(issue(f"正文出现标记「{match.group(0)}」", text[max(0, match.start() - 20): match.start() + 20]))
    for match in EMOJI.finditer(text):
        language.append(issue("正文出现 emoji", ""))
    if FACT_ID.search(text):
        language.append(issue("正文出现 segment 编号", FACT_ID.search(text).group(0)))
    for word in FORBIDDEN.get(str(meta.get("mode") or "literary"), []) + FORBIDDEN["general"]:
        if word in text:
            language.append(issue(f"出现禁用词「{word}」", word))
    lengths = [sum(1 for ch in part if "一" <= ch <= "鿿") for part in parts]
    lengths = [value for value in lengths if value]
    avg = round(sum(lengths) / len(lengths), 1) if lengths else 0
    long_sentences = [part for part in parts if sum(1 for ch in part if "一" <= ch <= "鿿") >= 40]
    hints = []
    for part in long_sentences[:5]:
        hints.append(issue("这句 ≥40 字，建议在逗号处断开", part))
    if avg and not 16 <= avg <= 26:
        hints.append(issue(f"平均句长 {avg} 字，参考 16–26 字"))
    for word in STYLE_HINTS:
        if word in text:
            hints.append(issue(f"「{word}」像书面压缩；改成口播说法", word))
    checks.append(check("语言", "fail" if language else ("hint" if hints else "pass"),
                        f"{len(language)} 处语言问题" if language else (hints[0]["message"] if hints else f"平均句长 {avg} 字"),
                        language + hints))
    if channel_of(meta) == "article":
        personal = [issue(f"公众号公开文章出现「{term}」，确认不是写稿人的个人信息", term)
                    for term in PERSONAL_HINTS if term in text]
        checks.append(check("公开性", "hint" if personal else "pass",
                            "有疑似个人职业/技术栈内容，请人工确认" if personal else "没有发现个人职业/技术栈内容",
                            personal))
        number_issues = []
        for match in re.finditer(r"[一二三四五六七八九〇零]{4}\s*年", text):
            number_issues.append(issue(f"年份写成中文「{match.group(0)}」，公众号改用阿拉伯数字",
                                       match.group(0)))
        for match in re.finditer(r"百分之[一二三四五六七八九十百千]+", text):
            number_issues.append(issue(f"百分比写成中文「{match.group(0)}」，公众号改用阿拉伯数字",
                                       match.group(0)))
        checks.append(check("数字写法", ("fail" if final else "hint") if number_issues else "pass",
                            f"{len(number_issues)} 处中文年份/百分比" if number_issues
                            else "年份/百分比为阿拉伯数字", number_issues))
        refs = text.count("书里")
        checks.append(check("归属频率", "hint" if refs > 8 else "pass",
                            f"「书里」出现 {refs} 次，偏多" if refs > 8 else f"「书里」{refs} 次",
                            [issue(f"「书里」出现 {refs} 次，案例可改为直接讲", "")] if refs > 8 else []))
    quotes = QUOTE.findall(text)
    total_quote = sum(len(quote) for quote in quotes)
    quote_issues = []
    for quote in quotes:
        if len(quote) > 50:
            quote_issues.append(issue(f"单处引文 {len(quote)} 字，超过 50 字", quote))
    if total_quote > 300:
        quote_issues.append(issue(f"引文合计 {total_quote} 字，超过 300 字", ""))
    no_quotes = (str(meta.get("quote_policy") or "") == "no_quotes"
                 or str(meta.get("source_level") or "C") == "C")
    if no_quotes and quotes:
        quote_issues.append(issue("来源 C 级或 quote_policy=no_quotes，禁止原文引用", quotes[0]))
    spoiler = meta.get("spoiler_policy") or "main_ending_ok"
    spoiler_issues = []
    # 非虚构没有"结局剧透"这个概念，跳过
    if spoiler == "no_ending" and str(meta.get("mode") or "") != "expository":
        tail = text[-max(300, len(text) // 10):]
        for pattern in STRONG_ENDING:
            if pattern in tail:
                spoiler_issues.append(issue(f"结尾出现「{pattern}」，请审稿员确认是否剧透", tail[-80:]))
                break
    if quote_issues:
        checks.append(check("剧透与版权", "fail", f"{len(quote_issues)} 处引文/版权问题", quote_issues))
    elif spoiler_issues:
        checks.append(check("剧透与版权", "hint", "结尾有疑似剧透的说法，交给审稿员判断", spoiler_issues))
    else:
        checks.append(check("剧透与版权", "pass", "引文规则符合；剧透由审稿员确认"))
    if str(meta.get("mode") or "literary") == "narrative":
        morals = [issue(f"出现「{word}」这类升华词，请审稿员判断", word) for word in MORAL if word in text]
        checks.append(check("类型与升华", "hint" if morals else "pass",
                            "有疑似升华段，交给审稿员判断" if morals else "没有明显升华词", morals))
    if audit is None:
        checks.append(check("独立审稿", "fail" if final else "hint",
                            "缺少 audit.json；先让独立审稿智能体审稿" if final else "还没有独立审稿结果"))
    else:
        problems = []
        for key in ("factual_errors", "unsupported_claims", "continuity_issues", "quote_issues", "tone_issues",
                    "application_issues", "structure_issues", "action_issues"):
            items = audit.get(key) if isinstance(audit.get(key), list) else []
            for item in items:
                sentence = item.get("sentence") if isinstance(item, dict) else ""
                message = item.get("problem") if isinstance(item, dict) else str(item)
                problems.append(issue(f"{key}：{message or ''}", str(sentence or "")))
        status = str(audit.get("status") or "revise")
        if status != "pass":
            problems.append(issue(f"审核状态是 {status}"))
        precision = audit.get("precision_checks")
        required_kinds = {"name", "place", "time", "number", "attribution"}
        if status == "pass":
            if not isinstance(precision, list) or not precision:
                problems.append(issue("pass 但缺少 precision_checks（逐句精度核对）"))
            else:
                kinds = {str(x.get("kind") or "") for x in precision if isinstance(x, dict)}
                missing = required_kinds - kinds
                if missing:
                    problems.append(issue(f"precision_checks 缺少类别：{', '.join(sorted(missing))}"))
                fixes = [x for x in precision
                         if isinstance(x, dict) and str(x.get("result") or "") == "fix"]
                if fixes:
                    problems.append(issue(f"precision_checks 仍有 {len(fixes)} 条 fix，不能 pass"))
        checks.append(check("独立审稿", "fail" if problems else "pass",
                            f"{len(problems)} 处问题" if problems else "审核通过", problems))
    return checks



def check_final_text(meta: dict, text: str) -> list[dict]:
    checks = []
    chars = count_chars(text)
    cpm = float(meta.get("speech_rate_cpm") or DEFAULT_CPM)
    minutes = round(chars / cpm, 1)
    checks.append(check("总时长（仅记录）", "hint",
                        f"按 {cpm:.0f} 字/分钟估算，完整版约 {minutes} 分钟；主体按 10–25 分钟判，附加段不计入"))
    language = []
    for match in MARKERS.finditer(text):
        language.append(issue(f"正文出现标记「{match.group(0)}」", text[max(0, match.start() - 20): match.start() + 20]))
    for match in EMOJI.finditer(text):
        language.append(issue("正文出现 emoji", ""))
    if FACT_ID.search(text):
        language.append(issue("正文出现 segment 编号", FACT_ID.search(text).group(0)))
    if "<!-- S1_END -->" in text:
        language.append(issue("final.txt 残留 <!-- S1_END --> 标记", ""))
    checks.append(check("完整版格式", "fail" if language else "pass",
                        f"{len(language)} 处格式问题" if language else "没有标题/编号/表格/emoji 标记", language))
    brand = str(meta.get("brand") or "").strip()
    opening_mode = str(meta.get("opening_mode") or "none")
    ending_mode = str(meta.get("ending_mode") or "none")
    channel = channel_of(meta)
    hints = []
    if opening_mode == "spoken":
        first = sentences(text)[0] if sentences(text) else ""
        if SELF_INTRO.search(first):
            hints.append(issue("第一句看起来像自我介绍；品牌口播应放在钩子之后", first))
        if brand and brand not in text[:1200]:
            hints.append(issue(f"前 1200 字里没找到账号名「{brand}」", ""))
    warning = str(meta.get("content_warning") or "").strip()
    if str(meta.get("content_warning_mode") or "none") == "spoken" and warning and warning not in text:
        hints.append(issue("选了口播内容提示，但 final.txt 里没有找到那句话", warning))
    if ending_mode in {"both", "s6"}:
        tail = text[-500:]
        if brand and brand not in tail:
            hints.append(issue(f"结尾 500 字里没找到账号名「{brand}」", tail[-80:]))
        if channel == "video" and not re.search(r"[?？]", tail):
            hints.append(issue("结尾没找到互动问题", tail[-80:]))
        if str(meta.get("spoiler_policy") or "") == "no_ending":
            for pattern in STRONG_ENDING:
                if pattern in tail:
                    hints.append(issue(f"结尾出现「{pattern}」，确认不是剧透", tail[-80:]))
                    break
    title = base_title(meta)
    author = str(meta.get("author") or "").strip()
    head = text[:1500]
    if head.count("今天讲") > 1:
        hints.append(issue("前 1500 字里“今天讲”出现多次", str(head.count("今天讲"))))
    if title and head.count(f"《{title}》") > 2:
        hints.append(issue(f"前 1500 字里《{title}》出现多次，可能有重复介绍", str(head.count(f"《{title}》"))))
    if author and len(author) >= 4 and head.count(author) > 2:
        hints.append(issue("前 1500 字里作者全名出现多次，可能有重复介绍", author))
    checks.append(check("发布版开头/结尾", "hint" if hints else "pass",
                        "有需要人工确认的开头/结尾项" if hints else "品牌/提示/结尾符合设置", hints))
    return checks


def check_split_file(book: Path, final_text: str, limit: int = 500) -> list[dict]:
    path = book / "final_500.txt"
    if not path.is_file():
        return [check("500 字分段", "fail",
                      "缺少 final_500.txt；跑 python tools/split_500.py --book <书目录>")]
    text = read_text(path)
    blocks = [part.strip() for part in re.split(r"(?m)^\s*={3,}\s*$", text) if part.strip()]
    if not blocks:
        return [check("500 字分段", "fail", "final_500.txt 没有正文")]
    over = []
    for index, block in enumerate(blocks, start=1):
        chars = len(block)
        if chars > limit:
            over.append(issue(f"第 {index} 区 {chars} 字符，超过 {limit}", block[:60]))
    if norm(final_text) != norm("".join(blocks)):
        over.append(issue("final_500.txt 和 final.txt 内容对不上", "可能漏段或改字"))
    counts = [len(block) for block in blocks]
    return [check("500 字符分段", "fail" if over else "pass",
                  f"{len(blocks)} 个分区，{min(counts)}–{max(counts)} 字符" if not over
                  else f"{len(over)} 个分段问题", over)]


def check_publish(book: Path, meta: dict) -> list[dict]:
    path = book / "publish.md"
    required = bool(meta.get("publish_required", True))
    if not path.is_file():
        return [check("发布信息", "fail" if required else "hint",
                      "缺少 publish.md；发布版需要标题/封面/简介/标签")]
    text = read_text(path)
    channel = channel_of(meta)
    checks = []
    if "AI" not in text or ("辅助生成" not in text and "AI生成" not in text):
        checks.append(check("AI 标识", "fail", "publish.md 里没有「本期文案与配音由 AI 辅助生成」"))
    else:
        checks.append(check("AI 标识", "pass", "有 AI 辅助生成标识"))
    lines = text.splitlines()
    titles = []
    in_titles = False
    for line in lines:
        if line.strip().startswith("## 标题"):
            in_titles = True
            continue
        if in_titles and line.strip().startswith("## "):
            break
        if in_titles:
            match = re.match(r"\s*[1-3][.、]\s*(.+)", line)
            if match:
                titles.append(match.group(1).strip())
    title_limit = 30 if channel == "article" else 20
    if len(titles) != 3:
        checks.append(check("标题数量", "fail", f"需要 3 个标题，实际 {len(titles)} 个"))
    else:
        bad = [title for title in titles if len(title) > title_limit]
        checks.append(check("标题长度", "fail" if bad else "pass",
                            f"{len(bad)} 个标题超过 {title_limit} 字" if bad
                            else f"3 个标题都不超过 {title_limit} 字"))
    if "## 标签" not in text:
        checks.append(check("标签", "fail", "缺少「## 标签」"))
    else:
        checks.append(check("标签", "pass", "有标签段"))
    if str(meta.get("source_level") or "") == "C" and "待核" not in text:
        checks.append(check("来源提示", "fail", "来源 C 级，但简介没写「部分内容待核」"))
    elif str(meta.get("source_level") or "") == "C":
        checks.append(check("来源提示", "pass", "有「部分内容待核」"))
    if channel == "article":
        if "## 摘要" in text or "## 简介" in text:
            checks.append(check("摘要", "pass", "有摘要/简介段"))
        else:
            checks.append(check("摘要", "fail", "公众号发布信息缺少「## 摘要」"))
        return checks
    cover = re.search(r"大字\s*[:：]\s*(.+)", text)
    if not cover:
        checks.append(check("封面大字", "hint", "没找到「大字：」"))
    else:
        value = cover.group(1).strip()
        checks.append(check("封面大字", "fail" if len(value) > 12 else "pass",
                            f"封面大字 {len(value)} 字" + ("，超过 12 字" if len(value) > 12 else "")))
    if str(meta.get("spoiler_policy") or "") == "main_ending_ok" and not any(word in text for word in ("剧透", "结局")):
        checks.append(check("剧透提示", "hint", "讲清结局时，简介最好标注含剧透"))
    if str(meta.get("opening_mode") or "") == "card" and "开场卡" not in text:
        checks.append(check("开场卡", "hint", "选了开场卡但 publish.md 没写"))
    if str(meta.get("ending_mode") or "") in {"both", "card"} and "结尾卡" not in text:
        checks.append(check("结尾卡", "hint", "选了结尾卡但 publish.md 没写"))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="程序化检查（不调用模型）")
    parser.add_argument("--book", required=True)
    parser.add_argument("--stage", default="final", choices=("notes", "outline", "draft", "publish", "final"))
    args = parser.parse_args()
    book = Path(args.book).expanduser().resolve()
    try:
        meta, source, segments = load_book(book)
    except Exception as exc:  # noqa: BLE001
        print(f"读不了书目录：{exc}")
        return 2

    checks: list[dict] = []
    if args.stage in {"notes", "outline", "draft", "final"}:
        checks.extend(check_notes(book, source, segments))
    if args.stage in {"outline", "draft", "final"}:
        checks.extend(check_outline(book, segments))
    if args.stage in {"draft", "final"}:
        # 主体永远检查 draft.md；final.txt 只做附加段和总时长检查。
        draft_path = book / "draft.md"
        try:
            draft = read_text(draft_path)
        except OSError:
            checks.append(check("主体稿", "fail", "读不到 draft.md"))
            draft = ""
        audit = None
        try:
            audit = read_json(book / "audit.json")
        except Exception:  # noqa: BLE001
            audit = None
        if draft:
            checks.extend(check_draft_text(meta, draft, audit, final=args.stage == "final"))
    if args.stage in {"publish", "final"}:
        checks.extend(check_publish(book, meta))
    if args.stage == "final":
        final_path = book / "final.txt"
        if not final_path.is_file():
            checks.append(check("最终稿", "fail", "缺少 final.txt"))
        else:
            final_text = read_text(final_path)
            checks.extend(check_final_text(meta, final_text))
            checks.extend(check_split_file(book, final_text))

    passed = all(item["level"] != "fail" for item in checks)
    result = {"passed": passed, "stage": args.stage, "checks": checks,
              "failed": [item["name"] for item in checks if item["level"] == "fail"]}
    (book / "qa.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in checks:
        mark = {"pass": "通过", "hint": "提示", "fail": "不通过"}[item["level"]]
        print(f"[{mark}] {item['name']}：{item['summary']}")
        for problem in item["issues"][:5]:
            print(f"    - {problem['message']} {problem['sentence'][:80]}")
    print(f"\n{'全部通过' if passed else '还有失败项'}；结果写到 {book / 'qa.json'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
