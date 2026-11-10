#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""表情包导出核心库：白底抠图 / 240 排版 / 透明 GIF 编码 / 量化 QA。

纯本地、零积分。所有阈值都可通过函数参数或项目 config.json 覆写。
不引用任何具体角色、具体图片或固定路径。

依赖：Python 3.9+、Pillow
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

# ---- 默认参数（历史实测值，可用 config.json 覆盖） --------------------------
CELL = 512                 # sprite sheet 每格边长
COLS, ROWS = 3, 2          # 3x2 六格 = 六个动画帧
SIZE = 240                 # 微信主图边长
THUMB = 120                # 缩略图边长
CHAR_BOX = (225, 203)      # 角色在 240 画布内的最大占位（保持角色偏小，不压字）
COLOR_STEPS = [255, 224, 192, 160, 128, 96, 64]
DURATIONS = [350, 250, 250, 450, 250, 350]   # ms，C4 峰值停顿更长
LIMIT_MAIN = 98_000        # 主图 GIF，留 2KB 余量给 100KB 硬线
LIMIT_THUMB = 48_000
LIMIT_COVER = 78_000
LIMIT_ICON = 28_000
LIMIT_BANNER = 78_000
DARK = (58, 64, 74)        # 深色聊天背景，用于检查白边/透明

# 纯白底抠图阈值。改这里之前先读 references/export-pipeline.md 的踩坑章节。
BG_MIN = 228               # 主体区：保守，保护浅色/暖色边缘
BG_MIN_SHADOW = 205        # 底部阴影带：放宽，去掉地面阴影
BG_SPREAD = 18             # 中性判定：通道极差 <= 该值才算背景候选
SHADOW_BAND = 70           # 底部多少行使用宽松阈值
EDGE_CLEAR = 4             # 清掉格子最外几像素（模型会画淡灰接缝）


# ---- 抠图 ------------------------------------------------------------------
def background_candidates(cell, bg_min=BG_MIN, bg_min_shadow=BG_MIN_SHADOW,
                          bg_spread=BG_SPREAD, shadow_band=SHADOW_BAND):
    """返回逐像素字节串：255 = 该像素看起来像影棚纯白背景。

    保守规则保护暖色/彩色边缘；只在底部阴影带放宽以吃掉地面阴影。
    「中性」按通道极差判定，不按亮度 —— 暖米白衣服不能被挖掉。
    """
    r, g, b = cell.convert('RGB').split()
    mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
    mn = ImageChops.darker(ImageChops.darker(r, g), b)
    spread = ImageChops.subtract(mx, mn)
    neutral = spread.point(lambda v: 255 if v <= bg_spread else 0)
    strict = ImageChops.multiply(
        mn.point(lambda v: 255 if v >= bg_min else 0), neutral).tobytes()
    loose = ImageChops.multiply(
        mn.point(lambda v: 255 if v >= bg_min_shadow else 0), neutral).tobytes()
    w, h = cell.size
    cutoff = max(0, h - shadow_band) * w
    return strict[:cutoff] + loose[cutoff:]


def _remove_enclosed_pale_holes(rgba, min_area=12, pale_min=235, pale_spread=15):
    """清掉被深色完全包围的近白封闭块（杯把手内孔、文件夹内孔）。

    flood-fill 从边界够不到这些洞。用严格 min>=235 阈值，绝不碰米白衣服。
    """
    px = rgba.load()
    a = rgba.getchannel('A').load()
    w, h = rgba.size
    pale = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            if a[x, y] >= 128:
                r, g, b = px[x, y][:3]
                if min(r, g, b) >= pale_min and max(r, g, b) - min(r, g, b) <= pale_spread:
                    pale[y * w + x] = 1
    reach = bytearray(w * h)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            i = y * w + x
            if (a[x, y] < 128 or pale[i]) and not reach[i]:
                reach[i] = 1
                q.append(i)
    for y in range(h):
        for x in (0, w - 1):
            i = y * w + x
            if (a[x, y] < 128 or pale[i]) and not reach[i]:
                reach[i] = 1
                q.append(i)
    while q:
        i = q.popleft()
        x, y = i % w, i // w
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h:
                j = ny * w + nx
                if not reach[j] and (a[nx, ny] < 128 or pale[j]):
                    reach[j] = 1
                    q.append(j)
    seen = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if not pale[i] or reach[i] or seen[i]:
                continue
            seen[i] = 1
            qq = deque([i])
            pts = []
            while qq:
                k = qq.popleft()
                cx, cy = k % w, k // w
                pts.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        m = ny * w + nx
                        if not seen[m] and pale[m] and not reach[m]:
                            seen[m] = 1
                            qq.append(m)
            if len(pts) >= min_area:
                for cx, cy in pts:
                    rgba.putpixel((cx, cy), (0, 0, 0, 0))
    return rgba


def cutout(cell, fill_holes=False, erode_px=0, edge_clear=EDGE_CLEAR, **kw):
    """把一张纯白底 RGB 图抠成透明 RGBA。

    fill_holes=True 清封闭白洞；erode_px=1 用形态学腐蚀吃掉轮廓 halo 白边。
    halo 必须靠 erode 清，不能靠降低 bg_min —— 降阈值会同步啃穿浅色衣料。
    """
    w, h = cell.size
    cand = background_candidates(cell, **kw)
    outside = bytearray(w * h)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            i = y * w + x
            if cand[i] and not outside[i]:
                outside[i] = 1
                q.append(i)
    for y in range(h):
        for x in (0, w - 1):
            i = y * w + x
            if cand[i] and not outside[i]:
                outside[i] = 1
                q.append(i)
    while q:
        i = q.popleft()
        x, y = i % w, i // w
        for j in (i - 1, i + 1, i - w, i + w):
            if 0 <= j < w * h and cand[j] and not outside[j]:
                outside[j] = 1
                q.append(j)
    alpha = Image.frombytes('L', (w, h), bytes(255 if v else 0 for v in outside))
    alpha = ImageChops.invert(alpha)
    if erode_px:
        alpha = alpha.filter(ImageFilter.MinFilter(erode_px * 2 + 1))
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.6))
    if edge_clear:
        e = edge_clear
        for box in ((0, 0, w, e), (0, h - e, w, h), (0, 0, e, h), (w - e, 0, w, h)):
            alpha.paste(0, box)
    rgba = cell.convert('RGBA')
    rgba.putalpha(alpha)
    if fill_holes:
        rgba = _remove_enclosed_pale_holes(rgba)
    return rgba


def sheet_tiles(sheet_path, overrides=None, cell=CELL, cols=COLS, rows=ROWS,
                clean_grid=True):
    """读一张 3x2 sprite sheet，切成 6 张透明 RGBA 帧。

    overrides: {条目号: {抠图参数}}，用于局部返修，不改全局默认值。
    """
    im = Image.open(sheet_path).convert('RGB')
    expect = (cols * cell, rows * cell)
    if im.size != expect:
        raise ValueError(f'{Path(sheet_path).name}: 期望 {expect}，实际 {im.size}')
    if clean_grid:
        im = remove_grid_lines(im)
    kw = overrides or {}
    return [cutout(im.crop((c * cell, r * cell, (c + 1) * cell, (r + 1) * cell)), **kw)
            for r in range(rows) for c in range(cols)]


def remove_grid_lines(im, cell=CELL):
    """清掉模型偶尔画在格线位置的淡灰分隔线（纯本地，不用重生成）。"""
    px = im.load()
    w, h = im.size
    cleaned = 0
    for x in list(range(cell - 2, cell + 3)) + list(range(2 * cell - 2, 2 * cell + 3)):
        if not (0 <= x < w):
            continue
        for y in range(h):
            r, g, b = px[x, y][:3]
            if 165 <= min(r, g, b) and max(r, g, b) <= 248 and max(r, g, b) - min(r, g, b) <= 12:
                px[x, y] = (255, 255, 255)
                cleaned += 1
    for y in range(cell - 2, cell + 3):
        if not (0 <= y < h):
            continue
        for x in range(w):
            r, g, b = px[x, y][:3]
            if 165 <= min(r, g, b) and max(r, g, b) <= 248 and max(r, g, b) - min(r, g, b) <= 12:
                px[x, y] = (255, 255, 255)
                cleaned += 1
    return im


def soften_bottom(tile, fade=28):
    """半身构图底边做柔化，避免硬切腰线（设计上故意裁腰，不是裁切事故）。"""
    t = tile.copy()
    a = t.getchannel('A').load()
    w, h = t.size
    for y in range(h - fade, h):
        k = (h - y) / fade
        for x in range(w):
            a[x, y] = int(a[x, y] * k)
    return t


# ---- 排版与编码 -------------------------------------------------------------
def frame_240(tile, size=SIZE, char_box=CHAR_BOX, top_align=False, text_y=207):
    """把 512 格缩到 240 透明画布。

    top_align=True 用于「带名字条」版：角色顶部对齐，给下方文字留空间。
    默认居中，用于无名字条版。
    """
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    t = tile.copy()
    t.thumbnail(char_box, Image.Resampling.LANCZOS)
    x = (size - t.width) // 2
    y = 0 if top_align else (size - t.height) // 2
    canvas.alpha_composite(t, (x, y))
    return canvas


def encode_gif(frames, path, durations=DURATIONS, size=SIZE,
               color_steps=COLOR_STEPS, limit=LIMIT_MAIN):
    """自适应调色板编码透明 GIF，自动挑能塞进体积上限的最高色数。

    返回 (bytes, colors)。transparency=255 + disposal=2 + loop=0 是微信动态表情的
    必要组合；白底 matte 只用于生成调色板，不会被写进透明像素。
    """
    path = Path(path)
    for colors in color_steps:
        strip = Image.new('RGB', (size * len(frames), size), 'white')
        for j, im in enumerate(frames):
            strip.paste(im, (size * j, 0), im.getchannel('A'))
        palette = strip.quantize(colors=colors)
        indexed = []
        for im in frames:
            matte = Image.new('RGB', im.size, 'white')
            matte.paste(im, mask=im.getchannel('A'))
            ind = matte.quantize(palette=palette, dither=Image.Dither.NONE)
            ind.paste(255, mask=im.getchannel('A').point(lambda a: 255 if a < 128 else 0))
            indexed.append(ind)
        indexed[0].save(path, save_all=True, append_images=indexed[1:],
                        duration=durations, loop=0, disposal=2,
                        optimize=False, transparency=255)
        if path.stat().st_size <= limit:
            return path.stat().st_size, colors
    raise ValueError(f'{path.name}: 降到最低色数仍超过 {limit} 字节，需精简画面或减少帧')


def save_png_fit(img, path, limit):
    """PNG 压到指定字节上限，先 optimize，再逐档降色（alpha 单独保留）。"""
    path = Path(path)
    img.save(path, optimize=True)
    if path.stat().st_size <= limit:
        return path.stat().st_size
    if img.mode == 'RGBA':
        alpha = img.getchannel('A')
        for colors in (255, 192, 128, 96, 64):
            p = img.convert('RGB').quantize(colors=colors).convert('RGBA')
            p.putalpha(alpha)
            p.save(path, optimize=True)
            if path.stat().st_size <= limit:
                return path.stat().st_size
    else:
        for colors in (255, 192, 128, 96, 64):
            img.quantize(colors=colors).save(path, optimize=True)
            if path.stat().st_size <= limit:
                return path.stat().st_size
    raise ValueError(f'{path.name}: 无法压到 {limit} 字节以内')


# ---- 量化 QA ----------------------------------------------------------------
def inspect_gif(path, size=SIZE):
    """检查真实 GIF：帧数/互异/循环/透明/空白帧。

    注意：用 ImageSequence.Iterator 时第 0 帧是 P 模式，后续帧会变 RGBA 且丢失
    info['transparency']。所以必须在 seek/迭代前先 dict(im.info) 保存。
    blank_frames 判据是「不透明占比 <2%」，占比是 0~1 不是百分数。
    """
    from PIL import ImageSequence
    with Image.open(path) as im:
        info = dict(im.info)
        dim, n = im.size, im.n_frames
        frames = [f.convert('RGBA') for f in ImageSequence.Iterator(im)]
    opaque = [sum(1 for a in f.getchannel('A').getdata() if a >= 128) / (size * size)
              for f in frames]
    return {
        'bytes': Path(path).stat().st_size, 'size': list(dim), 'frames': n,
        'unique_frames': len({f.tobytes() for f in frames}),
        'loop': info.get('loop'), 'transparency': info.get('transparency'),
        'opaque_pct': [round(v * 100, 1) for v in opaque],
        'blank_frames': [i + 1 for i, v in enumerate(opaque) if v < 0.02],
    }


def pose_metrics(frames):
    """逐帧 alpha 质心 + 轮廓 bbox，区分「真实姿态变化」与「重渲染噪声」。

    帧差只能证明画面变了，不能证明人物在动：脸和单只手变化也会拉高帧差。
    质心位移和轮廓宽高变化才是姿态证据。
    """
    raw = []
    for f in frames:
        a = f.getchannel('A')
        px = a.load()
        sx = sy = sw = 0
        for y in range(f.height):
            for x in range(f.width):
                v = px[x, y]
                if v:
                    sx += x * v
                    sy += y * v
                    sw += v
        b = a.getbbox()
        raw.append({'cx': sx / sw, 'cy': sy / sw,
                    'w': b[2] - b[0], 'h': b[3] - b[1]})
    moves = []
    for i in range(len(raw) - 1):
        p, q = raw[i], raw[i + 1]
        moves.append({
            'pair': f'C{i+1}->C{i+2}',
            'centroid_shift_px': round(((q['cx'] - p['cx']) ** 2 + (q['cy'] - p['cy']) ** 2) ** 0.5, 2),
            'width_change_pct': round(100 * (q['w'] - p['w']) / p['w'], 1),
            'height_change_pct': round(100 * (q['h'] - p['h']) / p['h'], 1),
        })
    return {
        'per_frame': [{k: round(v, 1) for k, v in d.items()} for d in raw],
        'adjacent': moves,
        'max_centroid_shift_px': max(m['centroid_shift_px'] for m in moves),
        'avg_centroid_shift_px': round(sum(m['centroid_shift_px'] for m in moves) / len(moves), 2),
        'pairs_over_8px': sum(1 for m in moves if m['centroid_shift_px'] >= 8),
        'pairs_shape_over_10pct': sum(
            1 for m in moves if max(abs(m['width_change_pct']), abs(m['height_change_pct'])) >= 10),
    }


def region_diff(frames, split=110):
    """相邻帧平均绝对灰度差，按头/身分区（辅助诊断，不能当姿态证据）。"""
    greys = []
    for f in frames:
        matte = Image.new('RGB', f.size, 'white')
        matte.paste(f, mask=f.getchannel('A'))
        greys.append(matte.convert('L'))
    out = []
    for i in range(len(greys) - 1):
        d = ImageChops.difference(greys[i], greys[i + 1])
        head = d.crop((0, 0, f.width, split)).histogram()
        body = d.crop((0, split, f.width, f.height)).histogram()
        hm = sum(k * v for k, v in enumerate(head)) / (f.width * split)
        bm = sum(k * v for k, v in enumerate(body)) / (f.width * (f.height - split))
        out.append({'pair': f'C{i+1}->C{i+2}', 'head': round(hm, 2), 'body': round(bm, 2)})
    return out


def edge_crop_ok(tile, band=2):
    """只有最外 2px 出现实体不透明像素才算真裁切。

    半身构图故意裁腰，旧版 full_in_frame 会把它误判为失败。
    """
    a = tile.getchannel('A').load()
    w, h = tile.size
    for y in range(h):
        for x in list(range(band)) + list(range(w - band, w)):
            if a[x, y] >= 200:
                return False
    for x in range(w):
        for y in list(range(band)) + list(range(h - band, h)):
            if a[x, y] >= 200:
                return False
    return True


def strip_dark(tiles, path, cell=160, dark=DARK):
    """六帧铺在深色背景上，供肉眼检查白边/透明/缺块。"""
    from PIL import Image
    out = Image.new('RGB', (COLS * cell, ROWS * cell), dark)
    for i, t in enumerate(tiles):
        r, c = divmod(i, COLS)
        small = t.resize((cell, cell), Image.Resampling.LANCZOS)
        layer = Image.new('RGBA', (cell, cell), dark + (255,))
        layer.alpha_composite(small)
        out.paste(layer.convert('RGB'), (c * cell, r * cell))
    out.save(path)
