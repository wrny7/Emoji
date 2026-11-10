# wechat-sticker-pack

一张角色图 → 24 张微信动态表情 GIF。

这是一个 **WorkBuddy 专用 Skill**，同时也是一套可独立运行的本地脚本。它把一整套「角色定妆 → 24 条动作设计 → 六格图集生图 → 白底抠图 → 透明 GIF 编码 → 量化验收」的流程固化下来，包含流程文档、事故库和可直接复用的代码。

## 它做什么，不做什么

| 做 | 不做 |
|---|---|
| 用**本次**用户提供的一张图，或现场用 ImageGen 生成的一张图作为唯一形象来源 | ❌ 不内置、不复用、不静默保存任何历史图片或定妆照 |
| 产出 `01.gif` – `24.gif` 共 24 张动态 GIF | ❌ 不做封面、缩略图、聊天页图标、详情页横幅、CSV、上传清单、ZIP 投稿包 |
| 附带逐帧预览、整体预览 HTML、`qa.json` | ❌ 不让 AI 写画面内文字（精确文字走本地字体叠加） |
| 完整流程文档、Prompt Guard、QA 判据、事故库 | ❌ 不绑定任何具体角色 / IP / 项目路径 |

**单张 GIF 硬规格**：`240×240`、透明背景、6 帧且帧帧互异、`loop=0` 无限循环、≤100KB、文件名 `01.gif`–`24.gif`。

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

依赖只有 Pillow。所有脚本都接受 `--workdir <项目目录>`，不写死任何项目路径。

### 额外环境

- Python 3.9+
- 本地中文字体（仅「道具精确文字叠加」需要）：`C:/Windows/Fonts/msyh.ttc`，可在 `config.json` 里改 `font_path`
- 图像生成能力：WorkBuddy 的 `ImageGen`。调用前先用 `ToolSearch` 加载 schema，再 `DeferExecuteTool` 调用，**不要凭记忆猜参数**。历史验证过的参数值见 `references/prompt-guide.md`

## 五步流程

```
A 形象基准（1 张图 → 透明基准卡 + 手写身份锁）
        ↓ 用户确认形象
B 条目与动作设计（默认 24 条，方案先行）
        ↓ 用户确认
C 编译 24 份 prompt → 只生成 1 套样张 → 九项清单打勾
        ↓ 样张通过 + 一次性授权积分
D 批量生成 23 套 → 逐张程序化复核 → 针对性重做
        ↓
E 本地导出 24 张 GIF → QA 全绿 → 深灰底人工复核 → 交付
```

门禁不可跳。用户说「一次性自动做完」时可以把 B/C/D 的确认合并成开头一次总授权，但**方案文档和样张仍要生成留档**。

### 命令速查

```bash
# 准备项目目录
mkdir my-pack && cd my-pack
cp <repo>/assets/entries-24.json entries.json

# A · 形象归一化（--input 是用户给的图或 ImageGen 生成的图）
python <repo>/scripts/prepare_character.py --workdir . --input character.png --name "角色名"
# → character/character-reference.png + character-card.json
# ⚠️ 必须用 ViewImage 打开基准图，逐项手写 identity_lock（四层结构）

# C · 编译 24 份 prompt
python <repo>/scripts/make_prompts.py --workdir .
# → prompts/01.txt … 24.txt
# 先只把 prompts/10.txt 投给 ImageGen，输出到 sheets/10/

# D · 逐张验收图集
python <repo>/scripts/check_sheet.py --workdir . --only 10
python <repo>/scripts/check_sheet.py --workdir .

# E · 导出与 QA
python <repo>/scripts/export_gifs.py --workdir . --only 10   # 单张试跑
python <repo>/scripts/export_gifs.py --workdir .              # 全量 24 张
# → output/gifs/01.gif … 24.gif, output/preview/, output/qa.json
```

局部返修：复制 `assets/config.template.json` 为项目根 `config.json`，用 `cutout_overrides` **按编号**覆写，绝不动全局默认阈值；返修后对全部 GIF 做 sha256 diff 证明只有目标条目变化。

`SKILL.md` 是完整流程的入口；细则见 `references/`：

| 文档 | 内容 |
|---|---|
| `workflow.md` | 五步流程细则、九项样张验收清单、生图调用模板 |
| `platform-spec.md` | 单张 GIF 硬规格；投稿包扩展仅作可选知识 |
| `prompt-guide.md` | 身份锁四层结构、全部 Guard 全文与理由、姿态词库、ImageGen 参数 |
| `export-pipeline.md` | 抠图阈值、编码参数、局部覆写、QA 判据与返修纪律 |
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
│   ├── entries-24.json            # 默认 24 条完整动作设计稿（可整体替换）
│   └── config.template.json       # 体积 / 抠图覆写 / 本地叠字配置模板
├── references/                    # 5 份流程与规则文档
├── scripts/
│   ├── sticker_lib.py             # 抠图 / 排版 / GIF 编码 / 量化 QA 核心库
│   ├── prepare_character.py       # 阶段 A
│   ├── make_prompts.py            # 阶段 C
│   ├── check_sheet.py             # 阶段 D 验收
│   └── export_gifs.py             # 阶段 E 导出
└── tests/
    └── smoke_test.py              # 端到端冒烟测试（纯本地，不联网、零积分）
```

## 测试

```bash
python tests/smoke_test.py
```

冒烟测试会造一张假角色图和 3 张假 `1536×1024` 六格图集，跑通 A → C → D → E 全链路，验证 24 份 prompt 生成、3 张 GIF 的尺寸 / 帧数 / 体积 / 透明度 / 循环 / 帧互异 / 无空白帧 / 无边缘裁切。测试数据在临时目录里，跑完自动清理。

## 成本与隐私

- 全流程约 24 次生图（1 次形象 + 1 次样张 + 23 套图集，重做另算），历史实测约 120–240 积分。**花积分前只确认一次。**
- 本仓库不含任何图片资产。用户提供的角色图、`sheets/`、`character/`、`output/` 全部在 `.gitignore` 里，避免把形象资产误推到公开仓库。
- 改文案只改数据、零成本；改动作要重生成对应图集；改形象等于 24 套全部重做。

## 许可证

MIT。见 [LICENSE](LICENSE)。
