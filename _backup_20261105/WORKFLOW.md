# 书籍口播稿 · 智能体工作流

> 你是执行这个工作流的智能体。**文件是唯一状态**：每一步只读上一步落盘的文件，不靠聊天记忆。每步结束必须停下来汇报，等用户说继续。

## 0. 目标

输入一本小说的全文 txt（可选一份 `background.md` 背景资料），输出一篇 **10–25 分钟的中文纯口播稿**（默认 15 分钟，约 3750 字），写到 `final.txt`；同时生成按 500 字分区的 `final_500.txt`。

目标听众：**没读过原著、不了解外国历史、对外国人名不敏感、靠耳朵听不能回看**。听完要能听懂，也能和别人讨论、对上原著。

主体顺序：**钩子 → 背景/人物地图 → 故事 → 主题 → 一句话总结**。不要在钩子之后立刻进情节；先把“作者为什么写、当时是什么环境、这些人是谁”讲清楚，再讲故事。

## 1. 目录

```text
books/<书名>/
  meta.json              书名、类型、target_minutes、speech_rate_cpm、target_chars、剧透策略、read_mode
  background.md          可选：作者/创作/时代背景（只写有来源的事实）
  source/original.txt    全文（只读，禁止修改）
  segments/index.jsonl   代码切好的分段
  segments/seg-XXXX.md   每段正文
  notes/beat_sheet.json  ① 精读笔记
  outline.json           ② 六段大纲（S1–S5，S6 留空）
  draft.md               ③ 主体口播稿（S1–S5）
  audit.json             ④ 主体审稿
  publish.md             ⑤ 发布包装
  qa.json                ⑥ 程序质检结果
  final.txt              ⑦ 完整口播稿（主体 + 品牌/提示/S6）
  final_500.txt          ⑦ 按 500 字分区（===== 分割线，不切段落）
```

## 2. 铁律（全程有效）

1. **小说事实只使用 `source/original.txt`；作者生平、创作背景、时代背景只使用 `background.md`。** 两个文件都没有的，不许补。禁止上网，禁止调用你对这本书的记忆，禁止补充原文没有的人物、情节、对白、结局、数字，也禁止编造作者生平、写作动机、发表经过。
2. **引文必须逐字**，并标 `segment_id`；来源级别 C 时禁止任何直接引文。
3. **不许跳步**：⑴ 笔记 → ⑵ 大纲 → ⑶ 主体稿 → ⑷ 独立审稿 → ⑸ 发布包装（问用户） → ⑹ final.txt。每一步的产物必须落盘。
4. **不改 `source/`、不改 `tools/`、不改 `prompts/`**；只写本步骤要求写的文件。
5. **写完必须跑检查**：`python tools/check.py --book <书目录> --stage <阶段>`；有 `fail` 就修，不要假装通过。
6. 每步结束汇报：写到哪个文件、检查结果、下一步是什么；然后停下等用户。

## 3. 判断走哪条路

先读 `meta.json` 的 `reading_mode`：

- `full_text`（≤12 万字）：可以直接读全文，走下面的标准流程。
- `chunked`（>12 万字）：先做 **1a 分段笔记**，再做 **1b 合并成精读笔记**，然后继续标准流程。写稿时必须把大纲引用到的**原文段落**一起读，不能只读笔记。

### 3.1 背景资料 `background.md`（可选，但作者背景必需）

想讲作者背景、创作背景、写作目的，就必须有 `background.md`。没有它，S2 只能讲书里能读到的东西，不要靠记忆补。

```markdown
# 背景资料
## 作者
- 事实（来源：书名/网页/论文，写清楚）
## 创作背景
- 事实（来源：...）
## 时代/历史
- 事实（来源：...）
## 写作目的/常见解读
- 观点（来源：...；标明是作者自述还是研究者观点）
## 不确定/不用
- 拿不准的写这里，不要进稿
```

规则：

- 只写有来源的事实；一条一行，能核对。
- 写稿时 S2 只能引用这里的作者/创作/时代信息；没有的就跳过。
- 审稿员要对照 `background.md` 查作者生平、创作背景有没有编。
- 不要把整篇百科贴进来；只留和这本书直接相关的 5–10 条。

### 3.2 先问时长（每期写稿前必须做）

先问用户：

> 这期口播要多少分钟？默认 15 分钟。

用户回答后跑：

```bash
python tools/set_target.py --book <书目录> --minutes 15
```

- 暂定按 **300 字/分钟** 算（非空白字符，含标点）。
- 字数线性增长：`完整字数 = 分钟数 × cpm`；`主体 S1–S5 = 完整字数 − 200`（品牌/提示/S6 约 200 字）。
- 15 分钟 → 完整 4500 字，主体 4300 字。
- 换声音、换语速，用已有 wav + `final.txt` 重新标定：

  ```bash
  python tools/set_target.py --book <书目录> --audio "D:\...\书名.wav" --minutes 15
  ```

- 用户没说时长就不要开写；不要自己按 15 分钟猜。

## 4. Step 1：精读笔记

提示词：`prompts/01_beat_sheet.md`

- 输入：`source/original.txt`、`segments/index.jsonl`、`segments/*.md`、`meta.json`；`background.md` 可读，但笔记只记原著事实
- 输出：`notes/beat_sheet.json`
- full_text：读完整个 `source/original.txt` 再写；不要只读开头。
- chunked：按 `segments/index.jsonl` 顺序逐段读，先在 `notes/segments/seg-XXXX.json` 记每段要点（谁、做了什么、结果、原文引文），再合并成 `notes/beat_sheet.json`；不确定的写进 `gaps`。
- 场景 6–8 个，每个带原文引文 + `segment_id`；人物 3–7 个；弧线、伏笔、主题。
- 跑：`python tools/check.py --book <书目录> --stage notes`
- 通过后停下，等用户看笔记。

## 5. Step 2：六段大纲

提示词：`prompts/02_outline.md`

- 输入：`notes/beat_sheet.json`、`meta.json`、`segments/index.jsonl`、`background.md`（可选）
- 输出：`outline.json`
- S1–S6 齐全；每个要点挂真实 `segment_id`；钩子 8 选 1；剧透策略按 meta。
- S2 不再只是“书、作者、时代、一句话主线”，要规划 **背景 + 人物地图**：作者背景、创作背景、写作目的、最少历史背景；人物超过 4 个或名字难记时，先给 4–6 人最小人物表。
- 作者/创作/时代信息只能来自 `background.md`；没有就只写书内信息，不许编。
- 跑：`python tools/check.py --book <书目录> --stage outline`
- 通过后停下，等用户确认大纲。

## 6. Step 3：写主体口播稿

提示词：`prompts/03_draft.md`

- 输入：`source/original.txt`、`notes/beat_sheet.json`、`outline.json`、`meta.json`、`background.md`（可选）
- 输出：`draft.md`（**只写 S1–S5 主体**，不写品牌开场、内容提示、S6、B 表）
- **写稿时必须看原文**：full_text 读全文；chunked 按大纲 `source_refs` 找到对应 `segments/seg-XXXX.md`，把原文段落一起读。
- **S1 钩子结束处单独写一行 `<!-- S1_END -->`**；Step 5 用它找品牌口播的插入点，然后删掉标记。钩子可以多段，但标记只能有一个。
- **`opening_mode=spoken` 时，钩子里不要出现书名/作者/“今天讲”**；这些留给品牌口播。S2 开头也不要再重复书名/作者全名/“这是……的短篇”，直接从作者背景开始。
- S2 先讲背景，再讲故事：作者背景 → 创作背景 → 写作目的 → 最少历史背景 → 人物地图（必要时） → 一句话主线。`opening_mode=card/none` 时才在 S2 开头补书名/作者/时代。
- 目标字数按 `meta.json` 的主体预算；开头 3 句要有具体信息；S1–S5 完整；不注水、不升华、不编。
- **口播语体**：像一个人坐在对面讲书，不用书面压缩/新闻稿腔。例：“天没亮”改成“天还没亮”；“随即”改成“马上”；“该军官”改成“这个军官”。
- 跑：`python tools/check.py --book <书目录> --stage draft`
- 通过后进入审核。

## 7. Step 4：独立审稿（另一个智能体）

**这一步必须新开一个智能体会话**，只给它 `prompts/04_audit.md` 和书目录；不要给它写稿会话的聊天记录，也不要让写稿智能体自己审自己。

- 输入：`source/original.txt`、`draft.md`、`outline.json`、`notes/beat_sheet.json`、`meta.json`、`background.md`（可选）
- 输出：`audit.json`
- 审稿员先跑机械检查：`python tools/check.py --book <书目录> --stage draft`
- `check.py` 只做机械校验（引文逐字、字数、标记、禁用词、C 级引文）；**语义判断（事实、结构、类型、剧透、质量）由审稿智能体负责**。
- 审稿员必须对照原文；只给问题和替换句，不重写全文；证据不足给 `revise` / `blocked`。
- 写稿智能体按 `patches` 只改对应句子；改完再让审稿员跑一次（最好再新开会话），直到 `status=pass`。
- 最终 `audit.json` 的 `status` 必须是 `pass`。

## 8. Step 5：发布包装（问用户，再拼完整版）

提示词：`prompts/05_publish.md`

- 前提：`audit.json` 的 `status=pass`。
- **一次性问用户 5 件事**：账号名、下期、内容提示、开场形式、结尾形式；给默认值。
- 用户回答后：写进 `meta.json`；在**不改主体事实**的前提下拼 `final.txt`：
  - 钩子：`draft.md` 开头到 `<!-- S1_END -->` 之前（可以多段）
  - 品牌口播（整个钩子之后）
  - 内容提示（如选口播）
  - `draft.md` 从 `<!-- S1_END -->` 之后到结尾（S2–S5 原文）
  - S6 固定尾（如选）
  - 删掉 `final.txt` 里的 `<!-- S1_END -->`
- 没有 `S1_END` 标记：只能退回“第一段之后插品牌”，并在汇报里警告钩子可能被切开；建议回 Step 3 加标记。
- 品牌口播已经介绍书名/作者；S2 开头如果又写“这是《书名》”“今天讲”“作者全名”，只删重复介绍，不改事实。
- 写 `publish.md`：3 个标题、封面大字、简介（含 AI 标识/剧透/来源提示）、标签、开场/结尾卡文案。
- **生成 `final_500.txt`**：`final.txt` 的段落之间空一行，然后跑：

  ```bash
  python tools/split_500.py --book <书目录>
  ```

  - 按空行识别段落；
  - 贪心装段：能塞进当前分区就塞，下一段会超过 500 字符就开新分区；
  - `=====` 分割线，**不切段落**；
  - 每区 ≤500 字符（按原始字符算：汉字、数字、标点、空格、段落间空行都算；分割线不算）。
  - 某一段本身 >500 字符：不要硬切，回 `final.txt` 把那段拆成更小的段落，再重跑。
- 只轻审新增段（品牌、提示、S6、publish.md）：剧透、禁用词、是否编下期；主体不动不重审。
- 跑：`python tools/split_500.py --book <书目录>`，再跑 `python tools/check.py --book <书目录> --stage final`

## 9. 时长规则（按实际口播速度）

- 口播速度看 `meta.speech_rate_cpm`，暂定 **300 字/分钟**（非空白字符，含标点）；不要用旧的 250 字/分钟。
- `meta.target_chars` = `target_minutes × speech_rate_cpm − 200`，是 S1–S5 主体预算。
- **主体 `draft.md`（S1–S5）**按 `字数 ÷ speech_rate_cpm` 估算；10–25 分钟是硬范围，目标 ±3 分钟是提示。
- 例子：15 分钟 → 完整约 4500 字，主体约 4300 字。
- 品牌口播、内容提示、S6、开场/结尾卡：**不计入主体时长**；总时长只记录。
- S6 单独 100–160 字，不从主体扣字数。

## 10. 定稿汇报

- 跑 `check.py --stage final`；`fail` 必须为 0。
- 汇报 `final.txt`、`final_500.txt`（几个分区、每区字数范围）、`publish.md`、主体字数/估算时长、附加段长度。
- 最终判断权在独立审稿智能体；`check.py` 只是机械安全网。

## 11. 检查脚本怎么用

```bash
python tools/check.py --book "books/羊脂球" --stage notes
python tools/check.py --book "books/羊脂球" --stage outline
python tools/check.py --book "books/羊脂球" --stage draft
python tools/check.py --book "books/羊脂球" --stage final
```

- `final` 阶段会检查 `final_500.txt`；先跑 `python tools/split_500.py --book <书目录>`。
- 退出码 0 = 没有 fail；1 = 有 fail；2/3 = 文件或目录有问题。
- 结果同时写到 `qa.json`。
- `hint` 不阻断，但要在汇报里写出来。

## 12. 启动方式

用户会对你说：

> 读 `WORKFLOW.md`，输入目录是 `books/羊脂球`。先做 Step 1，写完停下。

你就只做 Step 1，跑 `check.py --stage notes`，汇报后停下。用户说继续，再做 Step 2。不要一口气从读全文直接写到 final，除非用户明确说“全部跑完”。

## 13. 禁止事项

- 不要把 `notes/beat_sheet.json` 当成原文写稿；写稿要读 `source/original.txt` / 对应分段。
- 不要用“我印象里这本书……”补任何情节。
- 不要靠记忆写作者生平、创作背景、写作目的；只能引用 `background.md`，没有就跳过。
- 不要把背景写成历史课：作者/创作/时代加起来最多 3 小段，讲完立刻回到人物和故事。
- 不要在人物地图里连续报 6 个名字；超过 4 个关键人物才做地图，每人“原名 + 身份 + 一句话特征”。
- 不要在 `final.txt` 里留标题、时间码、来源编号、括号注释、表格、emoji，也不要留 `<!-- S1_END -->`。
- 不要把品牌开场放在钩子之前，也不要插在钩子中间；钩子可以多段，品牌必须等整个钩子结束。
- 不要让钩子、品牌口播、S2 三处都介绍“今天讲《书名》”；spoken 模式下品牌口播介绍一次，S2 不再重复。
- 不要为了加 S6 压缩主体。
- 不要在 Step 3 写品牌/内容提示/S6；这些只在 Step 5 按用户选择加。
- 不要在检查失败时把 `qa.json` 改掉或跳过检查。
