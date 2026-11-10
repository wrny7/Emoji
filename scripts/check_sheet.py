#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成后验收：逐张 sprite sheet 查格线 / 白底 / 入框 / 道具色连续 / 右下角水印。

生图是概率性任务，必须先逐张程序化复核再进导出管线。
输出 JSON 报告 + 六格放大图 + HTML 索引。纯本地、零积分。

用法：
  python check_sheet.py --workdir <project>
  python check_sheet.py --workdir <project> --only 01 05 18
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from PIL import Image, ImageDraw

import sticker_lib as lib

CW = lib.CELL
SEAMS_X = tuple(x for base in (CW, 2 * CW) for x in (base - 1, base, base + 1))
SEAMS_Y = (CW - 1, CW, CW + 1)


def is_gray_line(px):
    r, g, b = px[:3]
    return 165 <= min(r, g, b) and max(r, g, b) <= 248 and max(r, g, b) - min(r, g, b) <= 12


def color_bin(r, g, b):
    mx, mn = max(r, g, b), min(r, g, b)
    if mn >= 226:
        return 'white'
    if mx - mn < 26 and mx < 115:
        return 'black'
    if b > r + 22 and b > g + 8 and mx - mn > 34:
        return 'blue'
    if b > r + 12 and b > g + 5 and mx < 155 and mx - mn > 15:
        return 'blue'
    if r > g + 18 and g > b + 12 and mx - mn > 30:
        return 'brown'
    if r > 175 and g > 120 and b < 130 and mx - mn > 55:
        return 'yellow'
    if r > g + 30 and r > b + 30 and mx - mn > 45:
        return 'rosy'
    return 'other'


def analyze(path: Path, no: str) -> dict:
    im = Image.open(path).convert('RGB')
    w, h = im.size
    px = im.load()
    rep = {'no': no, 'file': path.name, 'size': [w, h],
           'size_ok': (w, h) == (3 * CW, 2 * CW)}

    seam = {}
    for x in SEAMS_X:
        if 0 <= x < w:
            seam[f'x{x}'] = sum(1 for y in range(h) if is_gray_line(px[x, y]))
    for y in SEAMS_Y:
        if 0 <= y < h:
            seam[f'y{y}'] = sum(1 for x in range(w) if is_gray_line(px[x, y]))
    rep['seam_gray_px'] = seam
    rep['grid_line_suspect'] = bool(seam) and max(seam.values()) > 300

    cells = []
    for row in range(2):
        for col in range(3):
            idx = row * 3 + col + 1
            x0, y0 = col * CW, row * CW
            tile = im.crop((x0, y0, x0 + CW, y0 + CW))
            tp = tile.load()
            bins = {}
            minx, miny, maxx, maxy, nonwhite = CW, CW, -1, -1, 0
            for y in range(CW):
                for x in range(CW):
                    c = color_bin(*tp[x, y][:3])
                    bins[c] = bins.get(c, 0) + 1
                    if c != 'white':
                        nonwhite += 1
                        minx, miny = min(minx, x), min(miny, y)
                        maxx, maxy = max(maxx, x), max(maxy, y)
            cells.append({
                'frame': idx, 'nonwhite_px': nonwhite,
                'bbox': [minx, miny, maxx, maxy] if maxx >= 0 else None,
                'margins': [minx, miny, CW - 1 - maxx, CW - 1 - maxy] if maxx >= 0 else None,
                'blue': bins.get('blue', 0), 'brown': bins.get('brown', 0),
                'yellow': bins.get('yellow', 0), 'rosy': bins.get('rosy', 0),
                'black': bins.get('black', 0),
            })
    rep['cells'] = cells
    for key in ('blue', 'brown', 'yellow', 'rosy'):
        rep[f'frames_with_{key}'] = sum(1 for c in cells if c[key] >= 120)

    # 整张画布右下角是工具水印高发区；低值说明水印是白字压白底，会被抠图吃掉
    corner = 0
    for y in range(max(0, h - 70), h):
        for x in range(max(0, w - 150), w):
            if color_bin(*px[x, y][:3]) != 'white':
                corner += 1
    rep['corner_nonwhite_bottom_right'] = corner

    # 空格 / 人物消失是最严重的生成事故，必须硬卡
    rep['empty_cells'] = [c['frame'] for c in cells
                          if c['nonwhite_px'] < CW * CW * 0.05]
    # 四角应接近纯白
    corners = [px[2, 2], px[w - 3, 2], px[2, h - 3], px[w - 3, h - 3]]
    rep['corner_min_channel'] = min(min(c) for c in corners)
    rep['white_backdrop_ok'] = rep['corner_min_channel'] >= 235
    return rep


def board(im: Image.Image, rep: dict, path: Path):
    out = Image.new('RGB', (3 * 400, 2 * 424), '#F2F2F2')
    d = ImageDraw.Draw(out)
    for i, c in enumerate(rep['cells']):
        row, col = divmod(i, 3)
        tile = im.crop((col * CW, row * CW, (col + 1) * CW, (row + 1) * CW))
        out.paste(tile.resize((400, 400), Image.Resampling.LANCZOS),
                  (col * 400, row * 424))
        m = c['margins']
        d.text((col * 400 + 8, row * 424 + 404),
               f"C{i+1}  margins={m}  blue={c['blue']} brown={c['brown']} "
               f"yellow={c['yellow']} nonwhite={c['nonwhite_px']}", fill='#111111')
    out.save(path)


def find_sheet(sheets: Path, no: str) -> Path | None:
    folder = sheets / no.zfill(2)
    if folder.is_dir():
        hits = sorted(folder.glob('*.png'), key=lambda p: p.stat().st_mtime)
        if hits:
            return hits[-1]
    flat = sheets / f'{no.zfill(2)}.png'
    return flat if flat.exists() else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workdir', required=True)
    ap.add_argument('--only', nargs='*', default=[])
    args = ap.parse_args()

    work = Path(args.workdir)
    sheets = work / 'sheets'
    out = work / 'output' / 'check'
    out.mkdir(parents=True, exist_ok=True)

    nos = [s.zfill(2) for s in args.only] if args.only else \
          [p.name.zfill(2) for p in sorted(sheets.iterdir())
           if p.is_dir() and p.stem.isdigit()] if sheets.exists() else []
    if not nos:
        raise SystemExit(f'没找到 sprite sheet：{sheets}')

    reports = []
    for no in nos:
        p = find_sheet(sheets, no)
        if not p:
            print(f'{no}: NO SHEET')
            continue
        rep = analyze(p, no)
        board(Image.open(p).convert('RGB'), rep, out / f'check_{no}.png')
        (out / f'check_{no}.json').write_text(
            json.dumps(rep, ensure_ascii=False, indent=2), encoding='utf-8')
        reports.append(rep)
        print(f"{no}: size_ok={rep['size_ok']} white_ok={rep['white_backdrop_ok']} "
              f"grid={rep['grid_line_suspect']} empty={rep['empty_cells']} "
              f"corner={rep['corner_nonwhite_bottom_right']} "
              f"margins={[c['margins'] for c in rep['cells']]}")

    cards = '\n'.join(
        f'<div class="card"><h3>{html.escape(r["no"])} · {html.escape(r["file"])}</h3>'
        f'<img src="check_{r["no"]}.png"><pre>' + html.escape(json.dumps({
            k: r[k] for k in ('size_ok', 'white_backdrop_ok', 'grid_line_suspect',
                              'empty_cells', 'corner_nonwhite_bottom_right',
                              'frames_with_blue', 'frames_with_brown',
                              'frames_with_yellow', 'frames_with_rosy')
        }, ensure_ascii=False, indent=1)) + '</pre></div>'
        for r in reports)
    (out / '验收.html').write_text(
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>sprite sheet 验收</title>'
        '<style>body{background:#fff;color:#222;font:14px/1.6 system-ui;margin:24px}'
        '.card{margin-bottom:32px;border:1px solid #ddd;padding:12px;border-radius:8px}'
        'img{width:100%;max-width:1200px;display:block}pre{background:#f6f6f6;padding:10px}</style>'
        '<h1>Sprite sheet 验收</h1>' + cards + '</html>', encoding='utf-8')
    print('报告:', out / '验收.html')


if __name__ == '__main__':
    main()
