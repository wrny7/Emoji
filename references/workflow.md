# 完整制作流程

从一张图到 24 张微信动态表情 GIF 的全部阶段、决策点、成本与验收标准。
主流程**只交付 GIF**；§7 是可选的投稿包扩展，非用户明确要求不要做。

---

## 0. 总览与分工

| 阶段 | 性质 | 是否花积分 | 可回滚 | 工作方式 |
|---|---|---|---|---|
| A 环境准备 | 确定性 | 否 | 是 | 跑检查命令 |
| B 形象基准 | 概率性 + 确定性 | 0 或 1 次生图 | 部分 | 先测再定、逐项核图 |
| C 条目与动作设计 | 确定性 | 否 | 是 | 纯文字方案，先确认 |
| D 编译 prompt + 样张 | 概率性 | 1–2 次 | 否 | 1 套验一个变量，清单打勾 |
| E 批量生成 | 概率性 | 约 23 次 | 否 | 逐批生成 + 逐张程序化复核 |
| F 导出 GIF | 确定性 | 否 | 是 | 本地 Pillow，脚本量化 |
| G 验收交付 | 确定性 | 否 | 是 | 数字 + 肉眼双重复核 |

**核心方法论**：确定性任务和概率性任务必须用两套工作方式。
- 确定性（本地脚本）：先测量 → 再设计 → 再实现 → 再 QA；改参数重跑零成本、可回滚。
- 概率性（生成模型）：前置约束锁死输出环境 → 一次只验一个变量 → 样张逐条打勾 → 通过才铺开。生成结果不可回滚，重来要再花钱。**不要把「写清楚了」当成「能控住」。**

历史项目最大的教训就是下午把生成活当本地活做：写完 prompt 直接赌输出，事后打补丁救，越救越烂。

---

## 1. 阶段 A · 环境准备

```bash
python -c "import PIL; print(PIL.__version__)"     # 需要 Pillow
python -m pip install Pillow                        # 缺失时安装
```

- 中文字体：仅当道具需要本地叠字时用到 `C:/Windows/Fonts/msyh.ttc`（商用投稿素材优先用 SIL OFL 授权的 `NotoSansSC-VF.ttf`）。
- 图像生成：WorkBuddy 的 `ImageGen`。**调用前先 `ToolSearch` 加载 schema，再 `DeferExecuteTool` 调用**，参数以实际 schema 为准，不要凭记忆猜。
- 建立项目工作目录，标准结构：

```
<workdir>/
├── character/           # 阶段 B：透明基准卡、验收图、character-card.json
├── entries.json         # 阶段 C：24 条设计稿（从 assets/entries-24.json 复制）
├── config.json          # 可选：体积 / 抠图覆写 / 本地叠字
├── prompts/             # 阶段 D：01.txt … 24.txt（脚本生成）
├── sheets/              # 阶段 E：NN/ 目录，每目录一张 3x2 sprite sheet PNG
│   └── NN/_reject/      # 重做时的旧图归档
└── output/
    ├── gifs/            # 最终交付：01.gif … 24.gif
    ├── preview/         # 逐帧深灰底图、整体预览.html
    ├── check/           # sprite sheet 验收报告
    └── qa.json
```

脚本互相 import，执行时把 `scripts/` 加入 `PYTHONPATH` 或在其目录下运行：

```bash
cd <skill-dir>/scripts
python prepare_character.py --input <图> --workdir <workdir>
```

---

## 2. 阶段 B · 形象基准（两条入口）

### B1 取得一张角色图

| 入口 | 做法 |
|---|---|
| 用户提供 | 直接用用户给的路径。不询问「是不是你本人」，不擅自命名，不静默保存他人照片到技能目录。 |
| 用户不给 | 调用 1 次 ImageGen 文生图生成一张角色立绘。提示词要点：单个完整角色、正面站立、纯白平底背景、无文字无水印无签名、四周留白、全身入镜。把输出路径记为 `--input`。 |

**技能不内置任何图片**，形象基准每次都来自本次输入。用户照片属于隐私，只放在 `<workdir>/` 或临时目录，不要放进技能包、不要上传外部服务、不要发布。

### B2 归一化

```bash
python prepare_character.py --input <image> --workdir <workdir>
```

产出 `character/character-reference.png`（透明基准卡）、`白底验收.png`、`深灰底验收.png`、`character-card.json` 骨架。
- 输入已有 alpha 就直接裁 bbox 等比缩放；纯白底则走 `cutout()` 抠成透明。
- 若报错「抠图后整张全透明」，换 `--no-cutout` 或换一张与背景对比更强的图。
- 整体等比缩放，不拉伸、不分块 resize；定版后不再二次缩放。

### B3 核对身份结构（**最容易翻车的一步**）

用 `ViewImage` 打开基准卡，**放大看**，逐项写进 `character-card.json`：

- `identity_lock`：英文四层结构，见 [prompt-guide.md](prompt-guide.md)。
- `identity_checks`：模型容易画错的结构断言，例如「某装饰件架在头顶不遮眼」「某部件是静态装饰不是嘴」「双眼必须完整可见」。
- `expression_channels`：这套形象真正能用来做表情的通道（眼 / 嘴 / 眉 / 脸颊 / 头颈 / 配饰），以及哪些部件必须保持静态。

**绝对禁止凭文件名、文字描述或记忆推断形象结构。** 历史事故：角色戴「黑框墨镜」，凭四个字推断出「眼睛被遮住」，据此把整套 24 条表情系统设计成「墨镜位移 + 装饰件开合」，还写了「瞪眼做不了」的硬约束。用户一句点破——墨镜是架在头顶的装饰，根本不遮眼；真正的嘴另有其物。一个错误前提污染了整节设计和 24 条表情，且写得越细错得越远。

### B4 定版

给用户看基准卡验收图，确认形象。定版后：
- 该 PNG 固定为后续**每一次** ImageGen 的 `image1`。
- 不再改形象。改形象（手型、鞋、比例）等于 24 套图集全部重做，成本约 24 次生图，必须先如实告知。

---

## 3. 阶段 C · 条目与动作设计

1. 复制 `assets/entries-24.json` → `<workdir>/entries.json`。默认 24 条已含完整六帧分解、道具规格、表情、辨识点，可整体替换。
2. 用户没指定文案就直接用默认稿，不逐条请示。用户指定文案时只改 `text` / `name` / `meaning` —— **改文案零成本、不重新生图**，因为本技能交付的 GIF 画面不带名字条；改 `frames` / `prop_spec` 才需要重新生成对应 sheet。
3. 逐条复核六帧设计：
   - 每格至少 **3 个部位**同时变化：躯干 / 重心腿脚 / 头颈 / 双臂双手 / 表情 / 道具。
   - C4 是峰值（最宽或最高剪影），C6 接回 C1 保证循环不跳。
   - **禁用深度方向姿态**：前倾、后仰、转身背对、后退一步。正面 2D 画面里这些几乎不改变剪影，还会把脸转没。改用侧倾、肩线高低、头歪方向、臂展、深蹲、抬腿、踢腿这类改变 2D 外轮廓的姿态名词。
   - 峰值姿态全辑去重，避免两张表情长得像。
4. 构图规则：默认 `full`（全身）。只有语义完全依赖手指精细形态或小道具细节才用 `half`；`scene` 只给宽场景，且必须配 `extra_guard` 把「六格独立成格」写死。
5. 道具规格写结构 / 材质 / 主色辅色 / 小配件 / 「非白非中性灰」。纯白与中性浅灰会被 flood-fill 整块抠掉（实测 0% 保留），浅色件改暖米白、暖橙、深蓝、深棕且色散 > 20。
6. 交付方案文档给用户确认。**任何重生成仍须单独授权。**

### 成本对照（如实告知）

| 变更类型 | 成本 |
|---|---|
| 改表情名称 / 含义词 / 对应文案 | 0 积分，只改数据 |
| 改 1 条动作 / 道具 | 1 次生图，约 5–10 积分 |
| 改形象基准 | 24 套全部重生成，约 120–240 积分 |
| 本地导出 / 抠图 / QA / 叠字 | 0 积分 |

---

## 4. 阶段 D · 编译 prompt 与 1 套样张

### D1 编译

```bash
python make_prompts.py --workdir <workdir>
```

生成 `prompts/01.txt` … `24.txt`。模板已内置全部 Guard，见 [prompt-guide.md](prompt-guide.md)。`identity_lock` 从 `character-card.json` 注入，未填写会直接报错拒绝生成——防止用空身份锁烧积分。

### D2 只出 1 套样张

选 `10`（笑不活了）：纯全身、无道具、幅度最大，一次只验一个变量（角色完整入框 + 全身联动），正是历史翻车的两点。

```bash
python make_prompts.py --workdir <workdir> --only 10   # 可省略，已全量编译
```

调用 ImageGen 一次，`output_dir=sheets/10/`，提示词取 `prompts/10.txt`，`image1` = 基准卡。历史验证参数（以实际 schema 为准）：`size=1536x1024`、`quality=high`、`background=opaque`、`revise=false`、`input_fidelity=medium`、`footnote=""`。

### D3 九项验收清单（逐条打勾，不通过不进 E）

| # | 项 | 判据 |
|---|---|---|
| 1 | 角色四边无裁切 | 六格 bbox 四边留白 ≥24px（<24px 仅记 warning），头手脚完整 |
| 2 | 纯白底 | 六格四角 min 通道 ≥235，无灰底、无渐变、无地面阴影 |
| 3 | 身份结构正确 | 放大核图，逐条比对 `identity_checks` |
| 4 | 无文字无水印 | 右下角诊断；淡色工具水印先验真实抠图管线再决定是否重做 |
| 5 | 6 帧互异 + 循环闭合 | `unique_frames=6`，C6 与 C1 姿态一致 |
| 6 | 全身联动 | 平均质心位移 ≥5px、≥8px 对数 ≥2、轮廓 ≥10% 对数 ≥2；**帧差不能当姿态证据** |
| 7 | 表情有变化 | 至少 3 个表情通道在相邻帧间不同，C4 最强 |
| 8 | 道具跨帧一致 | 六帧全程存在，大小/形状/颜色/数量不变 |
| 9 | 导出达标 | 240×240、6 帧、透明、loop=0、≤100KB |

数值只是辅助。**必须肉眼看逐帧深灰底展开图**，确认「人物确实在动」而不是重渲染噪声。

### D4 常见不通过与解法

- **六格几乎同一站姿、只有脸和一只手变**：把六帧改写成剪影差异极大的具体姿态名词（NARROW TALL STANDING / HUNCHED GIGGLE / BENT DOUBLE / ARMS FLUNG WIDE ONE LEG KICKED UP / DEEP SQUAT / STANDING WIPING A TEAR），明写 `SILHOUETTE MUST BE DRAMATICALLY DIFFERENT IN EVERY FRAME`，`input_fidelity` 降到 `medium`（`high` 会压制姿态变化）。历史实测平均质心 3.66px → 5.91px（+61%）。
- **角色残缺 / 被切**：先判断是「生成就没画全」还是「抠图切掉的」，用 ViewImage 放大逐格看。不要靠降抠图阈值硬救。
- **灰底**：prompt 里没写死纯白。重生成，不要在导出端把 `BG_MIN` 从 228 降到 120 —— 那会把角色浅色部位一起吃掉。

样张通过后，**一次性**告知预计消耗（约 24 次生图 / 120–240 积分）并取得授权。用户说「一次做完」时后续不再逐张请示。

---

## 5. 阶段 E · 批量生成 24 套

1. 逐份把 `prompts/NN.txt` 投给 ImageGen，`output_dir=sheets/NN/`，`image1` 恒定，每套只调一次。
2. 每批生成完立刻跑：

```bash
python check_sheet.py --workdir <workdir>              # 全量
python check_sheet.py --workdir <workdir> --only 02 22   # 只看指定条目
```

检查：1536×1024、四角纯白、无灰格线、无空格（人物消失）、无裁切、道具色六帧连续、右下角水印诊断。报告落在 `output/check/验收.html`。

3. 不合格的**针对性重做**，旧图移到 `sheets/NN/_reject/`。常见重做原因：灰格线、道具跨帧消失、人物消失、六格同站姿、格子空白。
4. 宽场景 / 远景条目的高频事故：把 `WIDE / DISTANT / SIDE-VIEW` 写在 prompt 开头，模型会把整张画布当连续画面铺，出现空格、跨格重排、半截道具。解法：把 `GRID LAYOUT — 六个独立 512 方格、每格恰好一幅完整独立场景、禁空格/禁一格两景/禁跨格` 提到最高优先级并首尾重复；道具精简到 4 件以内。
5. **工具水印**：ImageGen 会在整张画布右下角（即 C6）注入淡色「AI生成 / WORKBUDDY」字样。水印通常是近白（min≈242–249、低色散）压在纯白底上，`cutout()` 的 flood-fill 会整片吃掉。**先验一遍真实导出管线再决定是否重做**，多数不需要花积分。
6. 记住：`check_sheet.py` 的 `grid_line_suspect` 有误报可能（半身人物下缘的灰像素分三段落在三列），放大复核后再判断，本地 `remove_grid_lines()` 清理即可。

---

## 6. 阶段 F/G · 导出与验收

```bash
python export_gifs.py --workdir <workdir>
python export_gifs.py --workdir <workdir> --only 01 05 18   # 局部返修
```

产物：`output/gifs/01.gif` … `24.gif`、`output/preview/NN-逐帧.png`、`output/preview/整体预览.html`、`output/qa.json`。

QA 全绿标准：

```
complete=true   count=24   missing=[]
all_240 / all_le_100KB / all_6_unique / all_loop_0 / all_transparent
all_no_blank_frame / all_no_edge_crop  全 true
```

最后用 ViewImage 看深灰底整体预览，人工复核深色模式下有无白边、角色有无透明缺块。**QA 数字不能替代肉眼复核**——历史项目里 QA 全绿但深色模式下 5 张有白边，是用户发现的。

交付时只报 GIF 目录与 QA 结论，不夸大动感或精细度，如实说明残留限制（例如「宽场景条目未达严格侧视平躺」「指缝只数到 2 个指峰」）。

### 局部返修纪律

1. 只在 `config.json` 的 `cutout_overrides` 按编号覆写，**绝不动全局默认阈值**。历史事故：全局把 `BG_MIN` 从 228 降到 200，48 个文件全变、5 张米白衣服被挖穿，被迫整体回退。
2. halo 白边用 `erode_px=1` 形态学腐蚀清；封闭白洞（杯把手圆孔）用 `fill_holes=True` 清。这是两类独立问题，两种独立后处理。
3. 浅色衣服被底部宽松阴影带啃出透明缺口 → `{"bg_min":244,"bg_min_shadow":244,"shadow_band":0}`。缺口连到画面边界，用「内部洞」检测查不出来，要直接看指定区域的 alpha 计数。
4. 返修后对全部 GIF 做 sha256 diff，证明只有目标条目变化。改名 / 改数据类需求不碰图，也应做到 byte-identical。

---

## 7. 可选扩展 · 微信投稿包（默认不做）

只有用户明确说「要能上传微信表情开放平台 / 要投稿包」时才做。主流程到此为止。

需要补齐：缩略图 120×120 PNG ≤50KB（取各主图首帧）、封面 240×240 透明 PNG ≤80KB、聊天页图标 50×50 透明 PNG、详情页横幅 750×400 ≤80KB 且画面无文字/非透明非纯白底、`命名对照表.csv`、`上传清单.md`、ZIP 打包。

专辑规则：只支持 16 或 24 张（官方建议 24）、主图缩略图按 `01`–`24` 一一对应、4×6 布局、一套内全部动态或全部静态、表情名称 ≤8 汉字无标点、含义词 ≤4 汉字且同套不重复。

**「无字版」口径**：指画面下方不叠加表情名称字幕条，**不是画面内零文字**。道具上的文字（如台历「今天 / 明天」）允许存在，由本地字体精准叠加、不经过 AI。禁止的是 AI 乱画的水印、落款、名称条。

完整规格见 [platform-spec.md](platform-spec.md)。
