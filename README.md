# 书籍口播稿 · 智能体流水线

不跑平台重管线：**代码只做清洗/分段/机械检查，模型步骤交给智能体，读稿和审稿用两个独立会话。**

## 两条产品线

| 产品线 | `meta.channel` | `meta.mode` | 用哪套提示词 | 产出 |
|---|---|---|---|---|
| **公众号（听书/阅读）** | `article` | `expository` | `prompts/nf_01–nf_04` + `05` | 五段 S1–S5，公众号文章，**不写品牌口播**，默认无 S6/结尾卡 |
| **视频（抖音/B站）** | `video` | `literary` / `narrative` | `prompts/01–05` | 六段 S1–S6，口播视频，**品牌固定「听书一刻」**，带品牌口播/开场结尾卡 |

`channel` 不用手填：建书时按 `mode` 自动推导，`expository → article`，其他 → `video`。老目录没有 `channel` 的，检查脚本也按这个规则推。

## 目录

```text
Book_Agent_Pipeline/
  WORKFLOW.md             给智能体的流程协议
  prompts/
    01_beat_sheet.md      精读笔记
    02_outline.md         六段大纲 + 背景/人物地图
    03_draft.md           写主体口播稿（S1–S5，含背景）
    04_audit.md           独立审稿（含零背景听众检查）
    05_publish.md         发布包装 + 拼完整版（公众号/视频两版）
    nf_01–nf_04.md        公众号非虚构线：笔记/大纲/写稿/审稿
  tools/
    prepare.py            清洗 + 章节识别 + 切段（不耗 token）
    new_book.py           交互式建书：拖 txt → 问几项 → 生成目录
    check.py              机械检查（引文逐字/字数/标记/禁用词）
    split_500.py          按段落切成 500 字符以内，生成 final_500.txt
    set_target.py         按目标分钟数和实际口播速度重算字数预算
    import_getbook.py     从 Get_book/Books 批量导入成当前 books 格式
    next_prompt.py        按已有文件判断下一步，打印该步提示词
  新建一本书.bat          把 txt 拖上去，最少操作建书
  books/<书名>/           每本书的输入和产物
    background.md         可选：作者/创作/时代背景（只写有来源的事实）
    final.txt             完整口播稿
    final_500.txt         按 500 字分区（===== 分割线，不切段落）
```

## 只有全文 txt？拖一下就行

1. 把 txt **拖到 `新建一本书.bat` 上**
2. 按提示回答：书名、作者、类型、来源、剧透、时长、账号名、内容提示（直接回车用默认）
3. 它会生成 `books/<书名>/`，并打印下一步发给智能体的话
4. 智能体还会先问你：**这期口播要多少分钟？** 默认 15；按 1.0x 实测约 408 字/分钟线性算字数

不想回答就加 `--yes` 用默认值：

```bash
python tools/new_book.py "D:\书\某本书.txt" --yes
```

## 从 Get_book 批量导入

```bash
python tools/import_getbook.py --dry-run
python tools/import_getbook.py
```

- 读 `Get_book/Books/<n>_<书名>/{meta.json, source/original.txt}`
- 已存在同名书跳过，不覆盖
- 统一生成 `books/<书名>/`：meta、source、segments、notes
- 导入报告在 `books/_import_getbook.json`

当前已导入 70+ 本；`麦琪的礼物` 因已存在而跳过。外文书 `language` 会标成 en/de/ja，写稿时要注意。

不想手动找路径时，可以按书名自动找：

```bash
python tools/new_book.py --find "掌控习惯" --title "掌控习惯-01" --mode expository --yes
```

下一步提示词不用手找：

```bash
python tools/next_prompt.py --book books/活着 --next
```

它会根据已有文件判断该做 Step 1–5 的哪一步，并打印可直接复制的提示词。全部提示词也整理在 `使用提示词.txt`。

## 时长和字数怎么算

暂定 **300 字/分钟**（非空白字符，含标点）：

```text
完整字数 = 分钟数 × 300
主体 S1–S5 = 完整字数 − 200（视频线的品牌/提示/S6；公众号不扣）
```

15 分钟 → 完整约 4500 字，主体约 4300 字。

每期写稿前，智能体先问“这期要多少分钟”，然后：

```bash
python tools/set_target.py --book "books/羊脂球" --minutes 15
```

注意：当前 1.0x 录音实测约 408 字/分钟（3732 字 / 9.138 分钟）；如果保持这个速度，15 分钟需要约 6126 字。现在暂定 300，是**目标语速**，不是当前录音速度。换声音/语速后，用已有 wav 重新标定：

```bash
python tools/set_target.py --book "books/羊脂球" --audio "D:\...\羊脂球.wav" --minutes 15
```

## 想讲作者背景 / 创作背景？放 `background.md`

现在主体的 S2 会先讲背景，再讲故事。作者生平、创作背景、写作目的、时代背景**只能来自** `books/<书名>/background.md`；没有这个文件，智能体只讲书内信息，不许靠记忆补。

把下面模板存成 `books/<书名>/background.md`，每条写来源：

```markdown
# 背景资料
## 作者
- 事实（来源：...）
## 创作背景
- 事实（来源：...）
## 时代/历史
- 事实（来源：...）
## 写作目的/常见解读
- 观点（来源：...；标明作者自述/研究者观点）
## 不确定/不用
- 拿不准的放这里，不进稿
```

只留和这本书直接相关的 5–10 条，不要贴整篇百科。

建书时同目录有 `background.md` 会自动复制；也可以：

```bash
python tools/new_book.py "某本书.txt" --background "D:\书\background.md"
```

## 视频线主体结构（S1–S6）

> 公众号/非虚构线不用这张表，结构见 `prompts/nf_02_outline.md`：钩子 → 坐标 → 论证一 → 论证二/边界 → 收束+动作。

| 段 | 内容 |
|---|---|
| S1 | 钩子：100–250 字，具体的人/事/冲突，不自我介绍 |
| S2 | **背景 + 人物地图 + 一句话主线**：书名/作者/时代 → 作者背景 → 创作背景 → 写作目的 → 最少历史背景 → 人物地图（超过 4 个关键人物才做） |
| S3/S4 | 故事主体：按三幕讲，每幕“发生了什么—为什么—听众该注意什么”；每 5 分钟一句小结 |
| S5 | 主题 + 一句话总结：最后一句必须出现书名 + 至少两个核心人物原名 |
| S6 | 固定尾（Step 5 按用户选择加） |

S2 的背景只允许来自 `background.md`；没有就只讲书内信息，不编作者生平。

### 口播语体

写“人会说出口的话”，不是新闻稿/摘要：

- 天没亮 → **天还没亮**
- 几钟头前 → 几个钟头前
- 数小时前 → 好几个钟头前
- 随即 → 马上 / 紧接着
- 此时 → 这时候
- 该军官 → 这个军官
- 其目的 → 他想的是
- 未进食 → 没吃东西
- 前一日 → 前一天
- 话音未落 → 话还没说完

`check.py` 会提示这类书面压缩；语义判断在独立审稿。

### 钩子结束标记 `S1_END`

钩子可以多段。`draft.md` 在钩子结束处单独写一行：

```text
<!-- S1_END -->
```

视频线 Step 5 在标记后插入品牌口播和内容提示，再把标记删掉。这样品牌口播不会插进钩子中间；公众号不插品牌口播。

`opening_mode=spoken`（仅视频线）时：

- 钩子里不要出现书名、作者名、“今天讲”
- 品牌口播介绍一次书名/作者
- S2 不再重复“这是《书名》/今天讲/作者全名”，直接从作者背景开始

## `final_500.txt`：按 500 字符分区

`final.txt` 写完后跑：

```bash
python tools/split_500.py --book "books/羊脂球"
```

规则：

- 按空行识别段落，**分割线不切段落**
- 贪心装段：能塞进当前分区就塞；下一段会超过 500 字符，就开新分区
- 用 `=====` 隔开，每区 ≤500 字符（按原始字符算：汉字、数字、标点、空格、段落间空行都算；分割线不算）
- 某段本身超过 500 字符，脚本会报错；先把那段拆成更小的段落，再重跑

`check.py --stage final` 会校验 `final_500.txt`：分区不超 500 字符，且内容和 `final.txt` 对得上。

## 手动准备（以《羊脂球》为例）

### 1. 代码准备（不耗 token）

```bash
python tools/prepare.py \
  --input "F:\Desktop\Study\#Project\Book_Commentary_App\data\books\羊脂球\source\original.txt" \
  --out "books/羊脂球" \
  --title "羊脂球" --author "居伊·德·莫泊桑" \
  --mode literary --source-level A \
  --spoiler-policy no_ending --target-minutes 15
```

输出：`source/original.txt`、`segments/index.jsonl`、`segments/seg-*.md`、`meta.json`。
`meta.reading_mode` 会告诉智能体：全文能放下就 `full_text`，否则 `chunked`。

### 2. 写稿智能体

新开一个会话，把这句话发它：

> 读 `WORKFLOW.md`，输入目录是 `books/羊脂球`。先做 Step 1，写完停下。

它应当：

1. 读全文 → 写 `notes/beat_sheet.json`
2. 跑 `python tools/check.py --book books/羊脂球 --stage notes`
3. 汇报后停下

你说继续，它再做 Step 2（`outline.json`）、Step 3（`draft.md`）。每步都跑检查、落盘、停下。

Step 3 只写**主体 S1–S5**；视频线的品牌开场/内容提示/S6 留到 Step 5，公众号没有品牌口播和 S6。

### 3. 审稿智能体（必须另开一个）

新开**另一个**会话，把这句话发它：

> 读 `WORKFLOW.md` 和 `prompts/04_audit.md`，只做 Step 4：审 `books/羊脂球/draft.md`，写 `audit.json`；先跑 `python tools/check.py --book books/羊脂球 --stage draft`。

不要让写稿会话自己审自己。

### 4. 发布包装（审稿之后，同一个写稿智能体）

审核 `status=pass` 后，让写稿智能体会话做 Step 5：

> 读 `prompts/05_publish.md`，只做 Step 5：按 meta 默认值直接拼 `final.txt` 和 `publish.md`，不要再问我。

公众号不写品牌、不问账号名；视频的下期/内容提示/开场结尾用 `meta.json` 已有值，只有 `brand` 为空时才问一句。在**不改主体事实**的前提下拼：

```text
公众号：钩子 → S2–S5 原文（不写品牌口播）
视频：  钩子 → 品牌口播 → 内容提示 → S2–S5 原文 → S6
```

再写对应渠道的 `publish.md`：公众号写标题/摘要/标签/AI 标识/来源提示（最终标题打包时统一加「好书分享《书名》· 第N期 | 候选」）；视频写标题/封面/简介/标签/开场结尾卡。

### 5. 定稿检查

```bash
python tools/check.py --book "books/羊脂球" --stage final
```

- `fail` 必须为 0；`hint` 记录在 `qa.json`。
- 主体时长只卡 `draft.md`（S1–S5）的 10–25 分钟；品牌/提示/S6/卡片不计入，总时长只记录。

## 为什么 check 分成两层

- **`check.py`（机械）**：文件/JSON 是否存在、引文是否逐字在原文、字数、标记、禁用词、C 级引文。这类事情代码比模型可靠、免费、可复现。
- **独立审稿智能体（语义 + 逐句精度）**：事实、结构、类型、剧透、质量、是否像“读过书的人讲书”；外加逐句回原文核对专有名词、地点、时间、数字、归属主体（`audit.json` 的 `precision_checks`，五类缺一不能 pass）。

`check.py` 的 `hint` 不阻断；最终判断权在独立审稿智能体，`check.py` 只是安全网。

## 规则

- `source/` 只读；不改 `tools/`、`prompts/`。
- 文件是唯一状态，不靠聊天记忆。
- 每步落盘、跑检查、停下汇报。
- 长书（>12 万字）：Step 1 先按段做笔记，再合并成 `beat_sheet.json`；写稿时按大纲引用读原文段落，不能只看笔记。
