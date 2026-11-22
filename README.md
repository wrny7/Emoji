# wechat-sticker-pack

一张角色图 → 24 张微信动态表情 GIF。

**通用流程**：上传一张自己的形象图（或现场生成一张）→ 自己定 24 条表情 → 跑这套流程出 24 张动图。形象和表情都由使用者自己定，本库不带任何形象、表情与文案内容，不绑定任何具体角色。

这是一个 **WorkBuddy 专用 Skill**，同时也是一套可独立运行的本地脚本。它把一整套「角色定妆 → 24 条动作设计 → 视频 prompt 编译 → 视频生成 → 均匀抽帧 → 白底抠图 → 透明 GIF 编码 → 量化验收」的流程固化下来，包含流程文档、事故库和可直接复用的代码。

## 它做什么，不做什么

| 做 | 不做 |
|---|---|
| 用**本次**用户提供的一张图，或现场用 ImageGen 生成的一张图作为唯一形象来源 | ❌ 不内置、不复用、不静默保存任何历史图片或定妆照 |
| 产出 `01.gif` – `24.gif` 共 24 张动态 GIF | ❌ 不做封面、缩略图、聊天页图标、详情页横幅、CSV、上传清单、ZIP 投稿包 |
| 附带逐帧预览、整体预览 HTML、`qa.json` | ❌ 不让 AI 写画面内文字（精确文字走本地字体叠加；视频路线不设叠字步骤，动作设计时就避免精确文字） |
| 完整流程文档、Prompt Guard、QA 判据、事故库 | ❌ 不绑定任何具体角色 / IP / 项目路径 |

**单张 GIF 硬规格**：`240×240`、透明背景、12 帧且帧帧互异、帧时长 `[150,150,150,150,150,300,150,150,150,150,150,150]ms`（第 6 帧停 300ms，总 1.95 秒）、`loop=0` 无限循环、≤340KB（微信官方主图上限 500KB，生产安全线 340KB）、文件名 `01.gif`–`24.gif`。

**动作拆解格式**：每条 12 帧，C1 站立起势、C2–C4 展开蓄势、C5–C9 峰值区（核心姿态保持不换，靠表情 / 重心 / 头歪 / 眨眼 / 道具微动填充）、C10–C11 回落、C12 回到 C1，保证循环不跳。

## 安装

### 作为 WorkBuddy Skill（推荐）

把整个目录放到用户级技能目录：

```
C:/Users/<用户名>/.workbuddy-ai/skills/wechat-sticker-pack/
```

Windows 下也可直接复制本仓库内容到该目录。重启会话后，说「做一套微信动态表情」「把这张图做成 24 张表情」即会触发。

`SKILL.md` 带 `agent_created: true`，WorkBuddy 可以后续修改 / 删除这个技能。

### 只跑脚本（不装 Skill）

```bash
python -m pip install -r requirements.txt
```

依赖只有 Pillow；抽帧另需系统 ffmpeg / ffprobe。所有脚本都接受 `--workdir <项目目录>`，不写死任何项目路径。

### 额外环境

- Python 3.9+
- ffmpeg / ffprobe（抽帧用）：`ffmpeg -version` 能跑即可
- 视频生成能力：WorkBuddy 的视频生成（media generation）。每份 prompt 生成一段约 10 秒视频，角色参考图作视频 image 输入
- 本地中文字体（仅旧版 sprite-sheet 路线叠字需要，本路线不用）：`C:/Windows/Fonts/msyh.ttc`，可在 `config.json` 里改 `font_path`

## 五步流程

```
A 形象基准（1 张图 → 透明基准卡 + 手写身份锁）
        ↓ 用户确认形象
B 条目与动作设计（自定 24 条，12 帧分解，方案先行）
        ↓ 用户确认
C 编译 24 份视频 prompt → 只生成 1 条样张视频 → 抽帧验收清单打勾
        ↓ 样张通过 + 一次性授权
D 批量生成 23 条视频 → 逐条抽帧复核 → 针对性重做
        ↓
E 本地抽帧导出 24 张 GIF → QA 全绿 → 深灰底人工复核 → 交付
```

门禁不可跳。用户说「一次性自动做完」时可以把 B/C/D 的确认合并成开头一次总授权，但**方案文档和样张仍要生成留档**。

### 命令速查

```bash
# 准备项目目录
mkdir my-pack && cd my-pack
cp <repo>/assets/entries-24.json entries.json
# 先把 entries.json 里的 21 条占位换成你自己的 24 条表情定义（模板只含 3 条格式示例）

# A · 形象归一化（--input 是用户给的图或 ImageGen 生成的图）
python <repo>/scripts/prepare_character.py --workdir . --input character.png --name "角色名"
# → character/character-reference.png + character-card.json
# ⚠️ 必须用 ViewImage 打开基准图，逐项手写 identity_lock（四层结构）

# C · 编译 24 份视频 prompt
python <repo>/scripts/make_prompts.py --workdir .
# → prompts/01.txt … 24.txt
# 先只把 prompts/01.txt 拿去生成 1 条约 10 秒视频，存到 videos/01.mp4

# D · 逐条验收视频（抽帧看动作、留白、循环闭合）
# 先抽 1 条看效果，再批量生成其余 23 条视频到 videos/NN.mp4

# E · 导出与 QA
python <repo>/scripts/export_gifs.py --workdir . --only 01   # 单条试跑
python <repo>/scripts/export_gifs.py --workdir .              # 全量 24 条
# → output/gifs/01.gif … 24.gif, output/preview/, output/qa.json
# 抽出的 12 帧留在 frames/NN/ 供复核
```

局部返修：复制 `assets/config.template.json` 为项目根 `config.json`，用 `cutout_overrides` **按编号**覆写，绝不动全局默认阈值；返修后对全部 GIF 做 sha256 diff 证明只有目标条目变化。

`SKILL.md` 是完整流程的入口；细则见 `references/`：

| 文档 | 内容 |
|---|---|
| `workflow.md` | 五步流程细则、样张验收清单、视频生成调用模板 |
| `platform-spec.md` | 单张 GIF 硬规格；投稿包扩展仅作可选知识 |
| `prompt-guide.md` | 身份锁四层结构、视频 prompt 模板、12 帧动作格式、姿态词库 |
| `export-pipeline.md` | 抽帧、抠图阈值、编码参数、局部覆写、QA 判据与返修纪律 |
| `pitfalls.md` | 血泪事故库 + R1–R14 硬规则全文 |

## 目录结构

```
wechat-sticker-pack/
├── SKILL.md                       # Skill 入口：触发条件、五步流程、硬规则、资源索引
├── README.md                      # 本文件
├── LICENSE                        # MIT
├── requirements.txt               # Pillow
├── .gitignore
├── assets/
│   ├── entries-24.json            # 通用模板：3 条格式示例 + 21 条占位，表情由使用者自定
│   └── config.template.json       # 体积 / 抠图覆写配置模板
├── references/                    # 5 份流程与规则文档
├── scripts/
│   ├── sticker_lib.py             # 抠图 / 排版 / GIF 编码 / 量化 QA 核心库
│   ├── prepare_character.py       # 阶段 A
│   ├── make_prompts.py            # 阶段 C：编译 24 份视频 prompt
│   └── export_gifs.py             # 阶段 E：视频抽帧导出 24 张 GIF
└── tests/
    └── smoke_test.py              # 端到端冒烟测试（纯本地，不联网、零积分）
```

## 测试

```bash
python tests/smoke_test.py
```

冒烟测试会造一张假角色图和 12 张假视频帧，跑通 A → C → E 的本地部分，验证 24 份视频 prompt 生成、3 张 GIF 的尺寸 / 帧数 / 体积 / 透明度 / 循环 / 帧互异 / 无空白帧 / 无边缘裁切。视频生成与 ffmpeg 抽帧不在测试覆盖内。测试数据在临时目录里，跑完自动清理。

## 成本与隐私

- 全流程约 24 次视频生成（1 次形象 + 1 条样张 + 23 条批量，重做另算）。**花积分前只确认一次。**
- 本仓库不含任何图片资产。用户提供的角色图、`videos/`、`frames/`、`character/`、`output/` 全部在 `.gitignore` 里，避免把形象资产误推到公开仓库。
- 改文案只改数据、零成本；改动作要重生成对应视频；改形象等于 24 条视频全部重做。

## 版本说明

- v2.1.0（2026-11-22）：通用化。`entries-24.json` 改为通用模板（3 条格式示例 + 21 条占位），形象与表情均由使用者自定；文档里特定角色的写法示例全部换成中性示例；仓库不含任何形象资产与特定角色内容。
- v2.0.0（2026-11-22）：视频路线。12 帧拆解、≤340KB，替代 v1 的 3×2 六格 sprite-sheet 路线（6 帧、≤100KB）。旧路线文件 `check_sheet.py` 已删除；`sticker_lib.py` 的图集切分函数已移除；`entries-24.json` 由 6 帧机械转换为 12 帧。
- v1（2026-11-10）：初版，sprite-sheet 路线。历史教训见 `references/pitfalls.md`。

## 许可证

MIT。见 [LICENSE](LICENSE)。
