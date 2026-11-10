# Sprite Sheet 提示词工程

生成活的全部前置约束都在这里。`make_prompts.py` 已把本文的模板与 Guard 固化成代码，本文解释**为什么**这么写，以及需要人工改 prompt 时怎么改。

---

## 1. 输出格式：3×2 六格连续帧图集

一张 `1536×1024` PNG = 6 个 `512×512` 独立格子，按 C1 左上 → C2 中上 → C3 右上 → C4 左下 → C5 中下 → C6 右下排序，对应 GIF 的 6 帧。

选图集而不是 6 次单格生成的原因：一次调用出 6 帧，成本 1/6，且模型在同一次生成里更容易保持角色身份一致。代价是模型倾向输出「同一角色六个微变体」，大幅姿态会威胁一致性 —— 所以才有 §4 的剪影约束。

**拆成 6 次单格 1024×1024** 可作为兜底（姿态最可控、可逐张筛），但 6 格容易出现身份/风格漂移，反而返工且多花 30–60 积分。优先调图集 prompt。

---

## 2. IDENTITY LOCK 四层结构

`character-card.json` 的 `identity_lock` 由 WorkBuddy 用 ViewImage 打开基准卡**逐项核对后手写**，模板四层自上而下：

```
IDENTITY LOCK — the reference image is the ONLY character, keep it identical in
all six frames except pose/expression. Four layers, top to bottom:
(1) [最上层装饰件及其确切位置，以及「绝不在哪」的否定]
(2) [次层装饰件 / 结构件，若是静态装饰必须写死 never opens or changes shape]
(3) FACE: [发型、眼睛的完整可见性与细节、真正的嘴、脸颊、眉]
(4) [颈部配饰、躯干服装、手型、腿脚鞋，以及允许变化的部位]
```

写法要点：
- 用英文短句，每条写「是什么 + 在哪 + 绝不怎样」。模型对否定句敏感，`NEVER over the eyes, never on the nose` 这类双重要比「头顶装饰」有效得多。
- **把容易被误读的结构写成显式否定**。历史项目里模型极易把头顶墨镜画到眼睛上、把兜帽上的黄色装饰件当嘴来开合，所以最终版是四句独立英文锁：
  - `sunglasses rest on top never cover eyes`
  - `yellow duck bill is fixed ornament not a mouth`
  - `real mouth is small rosy oval`
  - `both grey-blue eyes always fully visible`
  （以上是历史案例的形态，**不是本技能的默认形象**，只演示写法。）
- 身份锁和验收清单必须成对出现。写进 prompt 的每一条，`identity_checks` 里都要有对应检查项。
- 抬头可写可不写：`make_prompts.py` 检测到 `IDENTITY LOCK` 开头就原样使用，否则自动补 `IDENTITY LOCK:`。两种写法都不会出现重复标题，不要自己再加一层。

---

## 3. 模板 Guard 全文与理由

`make_prompts.py` 的 `TEMPLATE` 由以下块拼成，顺序即优先级：

### GRID LAYOUT（最高优先级，首尾重复）

```
GRID LAYOUT — HIGHEST PRIORITY. EXACTLY SIX INDEPENDENT 512x512 CELLS ...
Each cell contains EXACTLY ONE complete self-contained picture.
NEVER treat the canvas as one continuous scene. NEVER leave an empty cell.
NEVER put two scenes in one cell. NEVER let any object cross a cell border.
Clean 24px white margin on all four sides of EVERY cell.
```

**为什么放最前**：宽场景 / 远景条目把 `WIDE / DISTANT / SIDE-VIEW` 写在 prompt 开头时，模型把整张画布当连续画面铺，出现 C2 整格纯白、C1/C3/C4/C6 画面跨格重排（半截伞）、六格缺道具。把网格独立成格提到最高优先级并首尾重复后稳定。这是唯一一个历史项目里连试三版才解决的生成事故。

### CLEAN_SHEET_GUARD

纯平白 `#FFFFFF`、无灰 / 渐变 / 地面 / 阴影 / 地平线；无格线、无分隔线、无角标；无 AI 文字 / 字母 / 数字 / 名字条 / 字幕条 / 水印 / logo / 签名。道具上要承载精确文字的表面画成干净空白色块，文字后期本地叠。

### PROP_PERSIST_GUARD

每件道具在**六帧全程存在**，大小 / 形状 / 颜色 / 数量 / 朝向 / 位置不变（帧描述明确写了移动的除外）；不消失、不变物、不变色。**禁止纯白与中性浅灰道具件** —— 白底 flood-fill 抠图会整块吃掉（实测 0% 保留），浅色件改暖米白 / 暖橙 / 深蓝 / 深棕且色散 > 20。

### ACCENT_GUARD

星屑 / 汗滴 / 星光 / 发光只在明确点名的帧出现，其余帧一律不画。

### MOTION_DRAMATIC（动作型）

```
CRITICAL — SILHOUETTE MUST BE DRAMATICALLY DIFFERENT IN EVERY FRAME.
Hip height, head height, foot positions, torso angle and arm span MUST
visibly change between frames. Each pose below is a named, instantly
recognizable body shape. Use FRONTAL 2D silhouette changes only:
side lean, shoulder-line slope, head tilt, arm span, squat, kick, reach.
NEVER use depth-direction poses (leaning forward / backward / turning
the back to the viewer / stepping away).
```

**为什么禁深度方向**：正面 2D 画面里前倾/后仰几乎不改变剪影，「稍等一下」写成前倾/后仰那版比只动手掌的初版还差；「明天再说」写成转身背对还会把脸转没，丢掉整套表情系统里最好用的通道。改成侧倾、肩线高低、头歪方向、臂展后成功。

### MOTION_STATE（状态 / 表情 / 道具叙事型）

六帧共用一个稳定姿势和固定机位，动画只来自脸（眼 / 瞳 / 眉 / 嘴 / 脸颊）、肩头轻微呼吸起伏、手与道具的真实小动作。**禁止整体平移 / 缩放 / 旋转 / 上下浮动伪造动作**；相邻帧至少 3 个表情或手部通道不同，C4 最强。

状态型的量化验收线要单独定，不能套动作型的质心位移判据 —— 比心、点赞、捂脸、台历这类靠「手势恒定 + 脸变化」表达，质心几乎不动是设计使然。

### FRAMING

| composition | 模板要点 |
|---|---|
| `full` | 角色填满格子，约 450–465px 高，双脚每帧可见，六帧同尺 |
| `half` | 腰部以上，双手与道具抬到胸前放大以便手指可读；腰被构图故意裁掉；六帧取景与比例完全一致；即使没有腿，躯干倾斜 / 肩线 / 头歪 / 臂展仍要变化 |
| `scene` | 角色与道具组成一组，占格宽约 400–450px，四周大量留白；角色刻意小但头手脚道具完整入框；固定机位；无满铺背景 / 海 / 天 / 地平线 / 地面 / 阴影 |

### STRICT NEGATIVE

禁整体平移缩放旋转伪造动作、禁六格同站姿、禁「一只胳膊动其余全身不动」、禁裁头手脚道具、禁缺肢或多肢、禁额外角色、禁未点名的道具、禁纯白或中性灰道具件、禁灰底或彩色底、禁 AI 文字 / 数字 / 名字条 / 字幕条 / 水印 / 签名、**C6 必须干净接回 C1**。

---

## 4. 六帧姿态词库

写 `frames` 时直接用**英文具名姿态名词**，不要写相对角度（「前倾 12°」模型执行不了），要写能改变 2D 外轮廓的剪影。

| 用途 | 可用词 |
|---|---|
| 窄高基线 | `NARROW TALL STANDING`、`NARROW UPRIGHT`、`ARMS DOWN, HEAD LEVEL` |
| 压缩变矮 | `HUNCHED SHOULDER GIGGLE`、`DEEP SQUAT INTO A BALL`、`BENT DOUBLE AT WAIST`、`KNEES BUCKLING` |
| 最宽峰值 | `ARMS FLUNG WIDE ONE LEG KICKED UP`、`BOTH ARMS UP IN A WIDE V`、`FULL REACH`、`MAXIMUM OPEN HAND`、`ARMS FULLY WRAPPED FORWARD` |
| 不对称 | `ONE-EYE PRESS, ASYMMETRICAL`、`SIDE SLUMP`、`DEEPEST HEAD TILT`、`ONE SHOULDER MUCH LOWER` |
| 收束 | `HALF RETREAT`、`ARMS LOWERING`、`SLOW RETURN`、`RISING HALFWAY` |
| 闭合 | `... AGAIN: matching frame 1 so the loop closes`（每套 C6 必写） |

历史验证过的完整六帧（B 版标准，平均质心位移 5.91px）：
`NARROW TALL STANDING` → `HUNCHED SHOULDER GIGGLE` → `BENT DOUBLE AT WAIST` → `THROWN BACKWARD ARMS FLUNG WIDE ONE LEG KICKED UP` → `DEEP SQUAT INTO A BALL` → `STANDING TALL WIPING A TEAR`。

### 峰值去重与跨表情差异

- 全辑 24 条的 C4 峰值姿态要互不撞型，否则两张表情看起来一样。
- 跨套首帧差异目标 ≥10%（96×96 白底合成 + alpha 并集掩膜内 RGB 平均绝对差）。历史项目量化发现 120 组跨表情首帧对比里 20 组差异 <8%，用户直接反馈「几个表情区别不大」。
- 最像的往往是「同站姿 + 同手势 + 无道具」的条目，靠差异化道具和姿势区分。

---

## 5. 道具规格写法

**写规格，不写名字。** 「放大镜」「咖啡杯」四个字交差，模型只能画成色块，而且必然漏掉配色约束导致抠图出洞。

模板：结构 → 材质 → 主色 + 辅色 → 细节件 → 「NO pure white or neutral gray」→ 「same size/color/shape in all six frames」→ 「must read unmistakably as X, not Y」。

历史实测配色保留率（走 `cutout()`）：暖木 `(168,110,62)` / 深蓝 `(60,90,130)` **100% 保留**；浅灰 240 / 近白 250 **被整块抠掉 0%**。判断抠图风险要看「纯白是否与外部白底连通」，不是看纯白面积 —— 被深色封闭在内部的纯白反而可能误测为「保留」。

---

## 6. WorkBuddy ImageGen 调用

**先用 `ToolSearch` 加载 schema，再 `DeferExecuteTool` 调用。** 参数以实际 schema 为准，下表是历史验证值，不要凭记忆硬编码。

| 参数 | 历史验证值 | 说明 |
|---|---|---|
| `size` | `1536x1024` | 3×2 六格，每格 512 |
| `quality` | `high` | |
| `background` | `opaque` | 试过 `transparent` 无效，仍出 RGB 白底 |
| `footnote` | `""` | 试过置空无效，右下角仍可能有淡色水印 |
| `revise` | `false` | 不要让工具改写 prompt |
| `input_fidelity` | `medium` | **`high` 会压制姿态变化**，B 版降到 medium 才拿到大幅剪影 |
| `image1` | `character/character-reference.png` | 每一套都固定同一张基准卡 |
| `output_dir` | `sheets/NN/` | 重做的新图与旧图同目录，导出取 mtime 最新 |

`background: "transparent"` 和 `footnote: ""` 都挡不住工具在整张画布右下角（C6）注入淡色「AI生成 / WORKBUDDY」字样。水印是近白白字压白底，flood-fill 会一并抠掉。**不要用矩形刷白盖水印** —— 会切掉 C6 角色右半边。先验真实导出管线再决定是否重做。

---

## 7. 常见生成漂移与对应 Guard

| 漂移 | Guard |
|---|---|
| 画布铺成连续画面、空格、跨格 | `GRID_LAYOUT` 置顶并首尾重复 |
| 灰底 / 渐变 / 地面阴影 | `CLEAN_SHEET_GUARD` 写死 `#FFFFFF` |
| 道具中途消失或变色 | `PROP_PERSIST_GUARD` |
| 道具纯白被抠没 | 配色约束写进 `prop_spec` |
| 六格同站姿只有脸动 | `MOTION_DRAMATIC` + 具名剪影姿态 + `input_fidelity=medium` |
| 一只胳膊动全身不动 | `STRICT NEGATIVE` 明写禁止 |
| 深度方向动作看不出来 / 丢脸 | 禁用前倾后仰转身，改侧倾 / 肩线 / 臂展 |
| 身份装饰件位置画错 | 四层 `IDENTITY LOCK` 显式否定句 |
| C6 接不回 C1 | 每套 C6 写 `matching frame 1 so the loop closes` |
| AI 乱写中文错字 | 道具页留空白色块，文字走本地 Pillow 叠加 |
