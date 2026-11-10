---
name: wechat-sticker-pack
description: 用一张角色图（用户提供或现场生成）自动产出 24 张微信动态表情 GIF。覆盖形象基准归一化、24 条动作分解、3x2 六格 sprite sheet 提示词编译、ImageGen 批量生成、白底抠图、透明 GIF 编码与量化验收。This skill should be used when the user asks to 做表情包 / 做微信动态表情 / 一张图生成 24 张表情 / 角色表情包 / 表情专辑 GIF / sticker pack，或要求把某个角色做成成套动画表情。不内置也不复用任何用户历史图片；形象始终来自本次输入。只交付 GIF 本体，不产出封面、缩略图、横幅、CSV 或投稿 ZIP。
agent_created: true
---

# 一张图 → 24 张微信动态表情 GIF

## 定位与边界

- 输入只有两种：① 用户提供一张角色图；② 用户不给图，由 ImageGen 现场生成一张角色图。技能**不内置任何图片、不引用历史项目里的任何形象或定妆照**。
- 输出只有 24 张：`240×240 / 透明 / 6 帧 / 无限循环 / ≤100KB` 的动态 GIF，编号 `01`–`24`。附带逐帧预览图、`整体预览.html`、`qa.json` 供验收。
- **不产出**缩略图、封面、聊天页图标、详情页横幅、命名对照表、上传清单、ZIP 投稿包。除非用户另行明确要求，不要顺手做。
- 全流程一次授权后自动跑完 24 张，不逐张请示。花积分前只确认一次。

## 环境依赖

- Python 3.9+ 与 Pillow：`python -c "import PIL; print(PIL.__version__)"`，缺失则 `python -m pip install Pillow`。
- 本地中文字体（仅道具叠字需要）：`C:/Windows/Fonts/msyh.ttc`。
- 图像生成能力：WorkBuddy 的 `ImageGen`。调用前**必须先用 ToolSearch 加载 schema**，再用 `DeferExecuteTool` 调用，不要凭记忆猜参数。历史验证过的参数值见 [prompt-guide.md](references/prompt-guide.md)，以实际 schema 为准。
- 所有脚本在 `scripts/` 下互相 import，执行时把 `scripts/` 作为工作目录或加入 `PYTHONPATH`。

## 五步流程 · 门禁不可跳

```
A 形象基准（1 张图 → 透明基准卡 + 身份锁）
        ↓ 用户确认形象
B 条目与动作设计（默认 24 条，方案先行）
        ↓ 用户确认「不用改」
C 编译 prompt → 1 套样张 → 验收清单打勾
        ↓ 用户验收通过 + 一次性授权积分
D 批量生成 23 套 → 逐张程序化复核 → 针对性重做
        ↓
E 本地导出 24 张 GIF → QA 全绿 → 交付
```

**任何一步没确认，不进下一步。** 这是上一个项目用两次翻车换来的规则，全文见 [pitfalls.md](references/pitfalls.md)。用户明确说「一次性自动做完」时，把 B、C、D 的确认合并为开头的一次总授权，但**方案文档与样张仍要生成并留档**，不能跳过不写。

## 阶段 A · 形象基准

1. 取得一张角色图。用户给了就用用户给的；没给就调用一次 ImageGen 文生图（提示词要求：单个完整角色、纯白平底、正面站立、无文字无水印、四周留白），把输出路径记为 `--input`。
2. 运行 `python scripts/prepare_character.py --input <图> --workdir <项目目录>`。产出 `character/character-reference.png`（透明基准卡）、白底/深灰底验收图、`character-card.json` 骨架。
3. **用 ViewImage 打开基准图逐项核对**，手写 `character-card.json` 的 `identity_lock`（英文四层结构）、`identity_checks`、`expression_channels`。禁止凭文件名或文字描述推断形象结构——历史事故：把「头顶装饰墨镜」误当成遮住眼睛，据此写错整套 24 条表情系统。
4. 给用户看基准卡验收图，确认形象。定版后**不再改形象**；改形象等于 24 套图集全部重做。
5. 把定版基准卡路径固定为后续每一次 ImageGen 的 `image1`。

四层身份锁写法与常见漂移点见 [prompt-guide.md](references/prompt-guide.md)。

## 阶段 B · 条目与动作设计

1. 复制 `assets/entries-24.json` 到项目根目录 `entries.json`。这是默认 24 条完整设计稿（文案 / 含义词 / 构图 / 道具规格 / 六帧分解 / 表情 / 辨识点），可整体替换。
2. 用户没指定文案就直接用默认稿，不必逐条请示；用户指定了就改 `text` / `name` / `meaning`，并说明「只改文案零成本、不重新生图」。
3. 复核六帧是否合格：每格至少 3 个部位同时变化（躯干 / 重心腿脚 / 头颈 / 双臂双手 / 表情 / 道具），C4 为峰值，C6 接回 C1，禁用前倾/后仰/转身背对等**深度方向**姿态（正面 2D 剪影几乎不变且会丢脸）。
4. 构图默认全身；只有语义完全依赖手指精细形态或小道具细节才用 `half`；`scene` 仅用于宽场景，且必须在 `extra_guard` 里写死「六格独立成格」。
5. 交付方案文档给用户确认。改文案 = 改数据；改动作 = 重生成对应 sheet，如实说明成本。

24 条数据字段规范见 `assets/entries-24.json` 的 `_readme`。

## 阶段 C · 编译 prompt 与样张

1. `python scripts/make_prompts.py --workdir <项目目录>`，在 `prompts/01.txt` … `24.txt` 生成 24 份完整 prompt。模板已内置：网格独立成格（最高优先级）、纯白底、24px 留白、身份锁注入、道具全程保持、精准文字留空块、STRICT NEGATIVE、C6 闭合。
2. 先只生成 **1 套样张**（建议 10 号「笑不活了」：全身、无道具、幅度最大，一次只验一个变量）。调用 ImageGen：`image1` = 基准卡，`size=1536x1024`、`quality=high`、`background=opaque`、`revise=false`、`input_fidelity=medium`，`output_dir` = `sheets/10/`。
3. `python scripts/check_sheet.py --workdir <项目目录> --only 10` 程序化复核，`python scripts/export_gifs.py --workdir <项目目录> --only 10` 导出单张看效果。
4. 按 [workflow.md](references/workflow.md) 的九项验收清单逐条打勾。**全身联动不通过就改 prompt 重出样张，不铺开。** 常见解法：把六帧写成剪影差异极大的具体姿态名词 + 明写 `SILHOUETTE MUST BE DRAMATICALLY DIFFERENT IN EVERY FRAME` + `input_fidelity=medium`。
5. 样张通过后一次性告知预计消耗（约 24 次生图 / 120–240 积分），取得授权再进 D。

## 阶段 D · 批量生成

1. 逐份把 `prompts/NN.txt` 投给 ImageGen，`output_dir` = `sheets/NN/`，`image1` 恒定，**每套只调用一次**。重做时新 PNG 落在同一目录、取最新，旧图不要删（留作审计）。
2. 每批生成完立刻 `python scripts/check_sheet.py --workdir <项目目录>` 复核：尺寸 1536×1024、四角纯白、无灰格线、无空格、无裁切、道具色六帧连续、右下角水印诊断。
3. 不合格的针对性重做，把旧图移到 `sheets/NN/_reject/`。**不要靠降低抠图阈值去救生成失误**（见 [export-pipeline.md](references/export-pipeline.md)）。
4. 工具在整张画布右下角注入的淡色水印通常是白字压白底，会被 flood-fill 一并抠掉。先验一遍真实导出管线再决定是否重做，别一见水印就烧积分。

## 阶段 E · 导出与交付

1. `python scripts/export_gifs.py --workdir <项目目录>` → `output/gifs/01.gif` … `24.gif`、`output/preview/*`、`output/qa.json`。
2. 需要道具精确文字时，把 `assets/config.template.json` 复制为项目根 `config.json`，填 `prop_text_overlay`。**叠字前先看实际 sheet 确认哪几帧是平放页**——AI 实际帧序可能与方案文档相反。
3. 局部画面返修只用 `config.json` 的 `cutout_overrides` 按编号覆写，**绝不动全局默认阈值**；返修后对全部 GIF 做 sha256 diff，证明只有目标条目变化。
4. QA 全绿才算完成：`count=24` / `missing=[]` / 全 240×240 / 全 ≤100KB / 6 帧互异 / `loop=0` / `transparency=255` / 无空白帧 / 无边缘裁切。
5. 用 ViewImage 看 `output/preview/整体预览.html` 对应的深灰底总览，人工复核深色模式下有无白边、角色是否缺块。**QA 数字不能替代肉眼复核。**
6. 交付时只报 GIF 目录与 QA 结论，不夸大「动感」「精细」，如实说明残留限制。

## 硬规则速查

| # | 规则 |
|---|---|
| R1 | 方案未经确认，不调用生成工具、不花积分。 |
| R2 | 生成前锁死输出环境：纯白 #FFFFFF、完整入框、四周留白、不跨边界、不画名字条/水印/落款、基准卡作 image1、身份锁。写进 prompt，不靠事后检查。 |
| R3 | 生成产物必须归一化到管线假设再进管线；绝不靠降抠图阈值救生成失误。 |
| R4 | 构图由动作需要决定，默认全身。 |
| R5 | 六帧写全身联动，每格 ≥3 部位变化，C6 接回 C1。禁深度方向姿态。 |
| R6 | 道具写规格不写名字，写明非白 / 非中性灰。 |
| R7 | 一次只验一个变量；先出 1 套样张，逐条打勾再铺开。 |
| R8 | 验收清单前置，先定标准再动手。 |
| R9 | 凡要写「做不到 / 必须 / 一律不动」的硬约束，先打开基准图核对。**设计源头错一次，写得越细错得越远。** |
| R10 | 身份结构写进生成 prompt 和验收清单。 |
| R11 | 别把用户口径扩大化。「无字版」= 不叠加名字条，不是画面内零文字。 |
| R12 | 精确文字走本地 Pillow 叠加，不让 AI 写字。 |
| R13 | 局部问题用局部覆写 + 哈希 diff 修；halo 白边靠形态学腐蚀清，不靠降阈值。 |
| R14 | 帧差只证明画面变了，不证明人物在动；姿态看质心位移与轮廓变化。 |

全文、事故经过与量化判据见 [pitfalls.md](references/pitfalls.md)。

## 资源索引

| 路径 | 用途 |
|---|---|
| [references/workflow.md](references/workflow.md) | 五步流程细则、九项验收清单、生图调用模板 |
| [references/platform-spec.md](references/platform-spec.md) | 单张 GIF 硬规格（本技能唯一需要遵守的平台约束） |
| [references/prompt-guide.md](references/prompt-guide.md) | 身份锁四层、模板 Guard、姿态词库、ImageGen 参数 |
| [references/export-pipeline.md](references/export-pipeline.md) | 抠图阈值、编码参数、局部覆写、QA 判据 |
| [references/pitfalls.md](references/pitfalls.md) | 血泪事故库 + 硬规则全文 |
| `scripts/sticker_lib.py` | 抠图 / 排版 / GIF 编码 / 量化 QA 核心库 |
| `scripts/prepare_character.py` | 阶段 A 形象归一化 |
| `scripts/make_prompts.py` | 阶段 C 编译 24 份 prompt |
| `scripts/check_sheet.py` | 阶段 D 逐张 sprite sheet 验收 |
| `scripts/export_gifs.py` | 阶段 E 导出 24 张 GIF |
| `assets/entries-24.json` | 默认 24 条完整动作设计稿（可整体替换） |
| `assets/config.template.json` | 体积 / 抠图覆写 / 本地叠字配置模板 |
