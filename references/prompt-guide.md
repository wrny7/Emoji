# 视频提示词工程

生成活的全部前置约束都在这里。`make_prompts.py` 已把本文的模板与 Guard 固化成代码，本文解释**为什么**这么写，以及需要人工改 prompt 时怎么改。

---

## 1. 输出格式：约 10 秒视频 → 均匀抽 12 帧

每条表情对应一段约 10 秒视频，角色参考图作视频的 image 输入。视频生成后均匀抽 12 帧，按 C1–C12 编码成 GIF。

选视频而不是 12 次单帧生成的原因：一次调用出 12 帧，成本低，且模型在同一次生成里更容易保持角色身份一致、动作连贯。代价是模型倾向输出「同一角色十二个微变体」，大幅姿态会威胁一致性 —— 所以才有 §4 的剪影约束和 §5 的动作原则。

**拆成 12 次单帧生成**可作为兜底（姿态最可控、可逐张筛），但帧间容易出现身份/风格漂移，反而返工且多花成本。优先调视频 prompt。

---

## 2. IDENTITY LOCK 四层结构

`character-card.json` 的 `identity_lock` 由 WorkBuddy 用 ViewImage 打开基准卡**逐项核对后手写**，模板四层自上而下：

```
IDENTITY LOCK — the reference image is the ONLY character, keep it identical in
all twelve frames except pose/expression. Four layers, top to bottom:
(1) [最上层装饰件及其确切位置，以及「绝不在哪」的否定]
(2) [次层装饰件 / 结构件，若是静态装饰必须写死 never opens or changes shape]
(3) FACE: [发型、眼睛的完整可见性与细节、真正的嘴、脸颊、眉]
(4) [颈部配饰、躯干服装、手型、腿脚鞋，以及允许变化的部位]
```

写法要点：
- 用英文短句，每条写「是什么 + 在哪 + 绝不怎样」。模型对否定句敏感，`NEVER over the eyes, never on the nose` 这类双重要比「头顶装饰」有效得多。
- **把容易被误读的结构写成显式否定**。历史项目里模型极易把头顶的装饰件画到眼睛上、把胸前的静态装饰当嘴来开合，所以最终版是四句独立英文锁（以下用一个虚构示例形象演示写法，**本库不带任何形象，形象由使用者自己提供**）：
  - `round ears stay on top of the hood, never cover the eyes`
  - `the star badge on the chest is a fixed decoration, never moves or changes shape`
  - `the real mouth is a small pink oval below the nose`
  - `both round eyes are always fully visible`
- 身份锁和验收清单必须成对出现。写进 prompt 的每一条，`identity_checks` 里都要有对应检查项。
- 抬头可写可不写：`make_prompts.py` 检测到 `IDENTITY LOCK` 开头就原样使用，否则自动补 `IDENTITY LOCK:`。两种写法都不会出现重复标题，不要自己再加一层。
- **颜色以抽帧实测为准**：prompt 里的颜色描述是约束，不是保证。抽出的 12 帧要逐张核对颜色与基准卡是否一致，不一致就重生成视频，不要在抠图端硬调。

---

## 3. 模板 Guard 全文与理由

`make_prompts.py` 的 `TEMPLATE` 由以下块拼成：

### CAMERA_GUARD（固定机位）

```
CAMERA — FIXED camera: no zoom, no pan, no dolly. Full body centered at the
same size and position in every frame. Plain pure-white background, no text,
no watermark, no logo, no other character. The character stays fully inside
the frame with clear white margins on all sides in every frame.
```

**为什么写死**：镜头一动，抽出的 12 帧尺寸 / 位置全漂移，`frame_240` 居中后角色忽大忽小、循环跳帧。固定机位是 12 帧能拼成一只 GIF 的前提。

### PROP_PERSIST_GUARD

每件道具在**十二帧全程存在**，大小 / 形状 / 颜色 / 数量 / 朝向 / 位置不变（帧描述明确写了移动的除外）；不消失、不变物、不变色。**禁止纯白与中性浅灰道具件** —— 白底 flood-fill 抠图会整块吃掉（实测 0% 保留），浅色件改暖米白 / 暖橙 / 深蓝 / 深棕且色散 > 20。

### MOTION_DRAMATIC（动作型）

```
CRITICAL — SILHOUETTE MUST BE DRAMATICALLY DIFFERENT IN EVERY FRAME. This is a
physical animation, NOT twelve near-identical standing portraits with a changed face.
Hip height, head height, foot positions, torso angle and arm span MUST visibly
change between frames. Each frame below is a named, instantly recognizable body shape.
Forward lean and stepping are allowed as long as the face stays fully visible and
the character stays fully inside the frame. A run-in from far away must STOP at
normal full-body size — the character must NEVER fill the frame or become a close-up
at any moment.
```

**为什么前倾 / 迈步可以写**：视频是真 3D 运动，前倾、迈步、转身都有真实的剪影和透视变化，不像正面 2D 图集里几乎看不出来。旧版 sprite-sheet 路线禁深度方向姿态，是那个路线的限制，**不要带到视频路线来**。唯一红线：脸必须全程可见、角色必须全程完整在画面内。

### MOTION_STATE（状态 / 表情 / 道具叙事型）

十二帧共用一个稳定姿势和固定机位，动画只来自脸（眼 / 瞳 / 眉 / 嘴 / 脸颊）、肩头轻微呼吸起伏、手与道具的真实小动作。**禁止整体平移 / 缩放 / 旋转 / 上下浮动伪造动作**；相邻帧至少 3 个表情或手部通道不同，峰值区（C5–C9）最强。

状态型的量化验收线要单独定，不能套动作型的质心位移判据 —— 手势恒定类靠「手势恒定 + 脸变化」表达，质心几乎不动是设计使然。

### MOTION_PRINCIPLES（动作原则，2026-11-22 定版）

- **突出重点动作**：每条只讲一个核心动作，写清、写大、拿稳。
- 正常的身体协调动作可以有（点头、迈步、重心移动、配饰跟随摆动）。
- **不要加与含义无关的多余动作**：凑数的转圈、跳跃、挥手、道具只会稀释辨识度。
- 手势类条目：手势本身是前景，放大、拿稳、脸是配角。
- 留白比例全套一致：角色在 240 画布内最大占位 225×203；跑近类动作远处起步小、跑近才到正常尺寸，最大时全身完整在画面内、四周都有白边。

### STRICT NEGATIVE

禁整体平移缩放旋转伪造动作、禁十二格同站姿、禁「一只胳膊动其余全身不动」、禁裁头手脚道具、禁缺肢或多肢、禁额外角色、禁未点名的道具、禁纯白或中性灰道具件、禁灰底或彩色底、禁 AI 文字 / 数字 / 名字条 / 字幕条 / 水印 / 签名、**C12 必须干净接回 C1**。

---

## 4. 十二帧姿态格式

### 帧段结构（C1–C12）

| 帧段 | 角色 | 要点 |
|---|---|---|
| **C1** | 站立起势 | 全身站正，双臂垂身侧，眼平视。**每条都从这里起** |
| **C2–C4** | 展开 / 蓄势 | 手臂抬起、道具出现或到位、身体开始动、表情开始起。C4 已接近峰值姿态 |
| **C5–C9** | **峰值区（5 帧）** | 核心姿态**保持不换**，靠表情 / 重心 / 头歪 / 眨眼 / 道具微动填充。这是 12 帧的关键——峰值是**一段**，不是一个定格帧 |
| **C10–C11** | 回落 | 手臂放下、身体回正、表情回收 |
| **C12** | 回 C1 | 站姿与 C1 一致，保证 `loop=0` 循环不跳 |

> 和旧版最大的差别：旧稿写「C4 单帧峰值、C5–C6 回落」是错的。交付成品逐帧拆开看，C5–C9 这 5 帧都在峰值姿态上做微变化，C10 才开始收。照旧稿做出来会「塌得太快」。

**六维记号**：T 躯干 / L 重心腿脚 / H 头颈 / A 双臂双手 / F 表情 / P 道具。每格至少 3 维相对上一格变化。

### 姿态词库

写 `frames` 时直接用**英文具名姿态名词**，不要写相对角度（「前倾 12°」模型执行不了），要写能改变外轮廓的剪影。

| 用途 | 可用词 |
|---|---|
| 窄高基线 | `NARROW TALL STANDING`、`NARROW UPRIGHT`、`ARMS DOWN, HEAD LEVEL` |
| 压缩变矮 | `HUNCHED SHOULDER GIGGLE`、`DEEP SQUAT INTO A BALL`、`BENT DOUBLE AT WAIST`、`KNEES BUCKLING` |
| 最宽峰值 | `ARMS FLUNG WIDE ONE LEG KICKED UP`、`BOTH ARMS UP IN A WIDE V`、`FULL REACH`、`MAXIMUM OPEN HAND`、`ARMS FULLY WRAPPED FORWARD` |
| 不对称 | `ONE-EYE PRESS, ASYMMETRICAL`、`SIDE SLUMP`、`DEEPEST HEAD TILT`、`ONE SHOULDER MUCH LOWER` |
| 收束 | `HALF RETREAT`、`ARMS LOWERING`、`SLOW RETURN`、`RISING HALFWAY` |
| 闭合 | `... AGAIN: matching frame 1 so the loop closes`（每套 C12 必写） |

### 峰值去重与跨表情差异

- 全辑 24 条的峰值区核心姿态要互不撞型，否则两张表情看起来一样。
- 跨套首帧差异目标 ≥10%（96×96 白底合成 + alpha 并集掩膜内 RGB 平均绝对差）。历史项目量化发现 120 组跨表情首帧对比里 20 组差异 <8%，用户直接反馈「几个表情区别不大」。
- 最像的往往是「同站姿 + 同手势 + 无道具」的条目，靠差异化道具和姿势区分。

---

## 5. 道具规格写法

**写规格，不写名字。** 「放大镜」「咖啡杯」四个字交差，模型只能画成色块，而且必然漏掉配色约束导致抠图出洞。

模板：结构 → 材质 → 主色 + 辅色 → 细节件 → 「NO pure white or neutral gray」→ 「same size/color/shape in all twelve frames」→ 「must read unmistakably as X, not Y」。

历史实测配色保留率（走 `cutout()`）：暖木 `(168,110,62)` / 深蓝 `(60,90,130)` **100% 保留**；浅灰 240 / 近白 250 **被整块抠掉 0%**。判断抠图风险要看「纯白是否与外部白底连通」，不是看纯白面积 —— 被深色封闭在内部的纯白反而可能误测为「保留」。

---

## 6. 视频生成调用

角色参考图作视频的 image 输入，约 10 秒一段。调用前先确认视频生成工具的实际参数（以工具 schema 为准），不要凭记忆硬编码。以下为通用约束，工具参数各家不同：

- image 输入：`character/character-reference.png`（定版基准卡，每一条都固定同一张）
- 时长：约 10 秒（抽 12 帧用；太短则采样点过密、动作展不开）
- 机位：固定（prompt 里写死，见 §3 CAMERA_GUARD）
- 背景：纯白平底，无文字无水印
- 输出：`videos/NN.mp4`，重做的新视频与旧视频同目录、取最新

---

## 7. 常见生成漂移与对应 Guard

| 漂移 | Guard |
|---|---|
| 镜头推近 / 角色忽大忽小 | `CAMERA_GUARD` 写死固定机位 |
| 灰底 / 渐变 / 地面阴影 | prompt 写死 `#FFFFFF` 纯白平底 |
| 道具中途消失或变色 | `PROP_PERSIST_GUARD` |
| 道具纯白被抠没 | 配色约束写进 `prop_spec` |
| 十二帧同站姿只有脸动 | `MOTION_DRAMATIC` + 具名剪影姿态 |
| 一只胳膊动全身不动 | `STRICT NEGATIVE` 明写禁止 |
| 跑近冲过头成大头特写 | 跑近必须停在正常全身尺寸；或改从画面侧面斜着跑进来 |
| 身份装饰件位置画错 | 四层 `IDENTITY LOCK` 显式否定句 |
| C12 接不回 C1 | 每套 C12 写 `matching frame 1 so the loop closes` |
| AI 乱写中文错字 | 动作设计时避免精确文字；视频路线没有本地叠字步骤 |
| 屏幕 / 发光道具的光打到脸上 | 发光道具写死「光不照到脸上」或改用深色不发光的道具 |
