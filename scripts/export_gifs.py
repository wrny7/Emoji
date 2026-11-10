#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 D：把 N 张 3x2 sprite sheet 导出为 N 张 240x240 透明动态 GIF。

本技能只交付 GIF 本体，不产出缩略图 / 封面 / 图标 / 横幅 / CSV / ZIP 投稿包。
附带产物仅为验收用：逐帧深灰底预览、整体预览 HTML、qa.json。

纯本地、零积分。不引用任何具体角色或固定图片。

用法：
  python export_gifs.py --workdir <project>
  python export_gifs.py --workdir <project> --only 01 05 18
  python export_gifs.py --workdir <project> --config path/to/config.json
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import sticker_lib as lib

DEFAULT_CONFIG = {
    'pack_size': 24,
    'size': 240,
    'char_box': [225, 203],
    'durations': [350, 250, 250, 450, 250, 350],
    'color_steps': [255, 224, 192, 160, 128, 96, 64],
    'limit_main': 98_000,
    'cutout_overrides': {},
    'prop_text_overlay': {},
    'font_path': 'C:/Windows/Fonts/msyh.ttc',
}


def load_config(work: Path, override: str = '') -> dict:
    cfg = dict(DEFAULT_CONFIG)
    p = Path(override) if override else work / 'config.json'
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding='utf-8')))
    return cfg


def find_sheet(sheets: Path, no: int) -> Path | None:
    """支持 sheets/NN/*.png（取最新一张，重做版自动生效）或 sheets/NN.png。"""
    folder = sheets / f'{no:02d}'
    if folder.is_dir():
        hits = sorted(folder.glob('*.png'), key=lambda p: p.stat().st_mtime)
        if hits:
            return hits[-1]
    flat = sheets / f'{no:02d}.png'
    return flat if flat.exists() else None


def overlay_text(tiles, spec, font_path):
    """按帧在本地叠精确文字（不经过 AI）。在 512 格阶段叠，缩放后仍清晰。

    spec: {"words": ["今天", null, "今天", "明天", "明天", "今天"],
           "box": [180, 300, 360, 415],  # 512 格内的相对坐标
           "size": 44, "color": "#30415B"}
    """
    words = spec.get('words') or []
    box = spec.get('box')
    if not box or len(box) != 4:
        raise ValueError('prop_text_overlay 需要 box: [x0,y0,x1,y1]（512 格内坐标）')
    size = spec.get('size', 44)
    color = spec.get('color', '#30415B')
    try:
        font = ImageFont.truetype(font_path, size)
    except OSError:
        font = ImageFont.load_default()
    drawn = []
    out = []
    for i, t in enumerate(tiles):
        word = words[i] if i < len(words) else None
        t = t.copy()
        if word:
            d = ImageDraw.Draw(t)
            bb = d.textbbox((0, 0), word, font=font)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            x = box[0] + (box[2] - box[0] - tw) // 2 - bb[0]
            y = box[1] + (box[3] - box[1] - th) // 2 - bb[1]
            d.text((x, y), word, font=font, fill=color)
            drawn.append(i + 1)
        out.append(t)
    return out, {'words': words, 'box': box, 'drawn_frames': drawn,
                 'font': str(font_path), 'mode': 'local-pillow'}


def preview_html(gifs, names, out: Path, size=160):
    cards = []
    for no in sorted(gifs):
        label = html.escape(names.get(no, str(no)))
        cards.append(
            f'<div class="c"><a href="../gifs/{no:02d}.gif" target="_blank">'
            f'<img src="../gifs/{no:02d}.gif" width="{size}" height="{size}"></a>'
            f'<div class="t">{no:02d} · {label}</div></div>')
    doc = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
           '<title>动态表情预览</title>'
           '<style>body{background:#f4f6f8;color:#30415b;font:14px/1.6 system-ui,'
           '"Microsoft YaHei";margin:24px}h1{font-size:20px}.g{display:grid;'
           'grid-template-columns:repeat(6,1fr);gap:14px;max-width:1120px}'
           '.c{background:#3a404a;border-radius:10px;padding:8px;text-align:center}'
           '.c img{display:block;margin:auto;border-radius:6px}.t{color:#e8eef5;'
           'margin-top:6px;font-size:12px}</style>'
           f'<h1>动态表情预览 · {len(gifs)} 张（深色底检查白边）</h1>'
           '<div class="g">' + ''.join(cards) + '</div></html>')
    (out / '整体预览.html').write_text(doc, encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workdir', required=True)
    ap.add_argument('--config', default='')
    ap.add_argument('--only', nargs='*', default=[])
    args = ap.parse_args()

    work = Path(args.workdir)
    cfg = load_config(work, args.config)
    sheets = work / 'sheets'
    gdir = work / 'output' / 'gifs'
    pdir = work / 'output' / 'preview'
    gdir.mkdir(parents=True, exist_ok=True)
    pdir.mkdir(parents=True, exist_ok=True)

    names = {}
    compositions = {}
    ep = work / 'entries.json'
    if ep.exists():
        doc = json.loads(ep.read_text(encoding='utf-8'))
        for e in (doc['entries'] if isinstance(doc, dict) else doc):
            no = int(e['no'])
            names[no] = e.get('text', '')
            compositions[no] = e.get('composition', 'full')

    pack_size = int(cfg['pack_size'])
    want = {int(s) for s in args.only} if args.only else set(range(1, pack_size + 1))
    overrides = {int(k): v for k, v in (cfg.get('cutout_overrides') or {}).items()}
    overlays = cfg.get('prop_text_overlay') or {}

    reports, gifs, missing = {}, {}, []
    for no in sorted(want):
        sheet = find_sheet(sheets, no)
        if not sheet:
            missing.append(no)
            print(f'  {no:02d} MISSING sheet，跳过')
            continue
        tiles = lib.sheet_tiles(sheet, overrides=overrides.get(no, {}))
        if compositions.get(no) in ('half', 'scene'):
            tiles = [lib.soften_bottom(t) for t in tiles]
        overlay_info = None
        if str(no) in overlays:
            tiles, overlay_info = overlay_text(tiles, overlays[str(no)], cfg['font_path'])

        frames = [lib.frame_240(t, size=int(cfg['size']),
                                char_box=tuple(cfg['char_box'])) for t in tiles]
        gif = gdir / f'{no:02d}.gif'
        nbytes, colors = lib.encode_gif(
            frames, gif, durations=cfg['durations'], size=int(cfg['size']),
            color_steps=cfg['color_steps'], limit=int(cfg['limit_main']))
        qa = lib.inspect_gif(gif, size=int(cfg['size']))
        lib.strip_dark(tiles, pdir / f'{no:02d}-逐帧.png')
        boxes = []
        for t in tiles:
            b = t.getchannel('A').getbbox()
            boxes.append({
                'bbox': list(b) if b else None,
                'margins': [b[0], b[1], lib.CELL - b[2], lib.CELL - b[3]] if b else None,
                'no_edge_crop': lib.edge_crop_ok(t),
                'tight_margin': bool(b and min(b[0], b[1], lib.CELL - b[2], lib.CELL - b[3]) < 24),
            })
        reports[no] = {
            'no': no, 'text': names.get(no, ''), 'sheet': sheet.name,
            'bytes': nbytes, 'colors': colors,
            'size': qa['size'], 'frames': qa['frames'],
            'unique_frames': qa['unique_frames'], 'loop': qa['loop'],
            'transparency': qa['transparency'], 'blank_frames': qa['blank_frames'],
            'boxes': boxes,
            'all_no_edge_crop': all(x['no_edge_crop'] for x in boxes),
            'pose': lib.pose_metrics(frames),
            'prop_text_overlay': overlay_info,
        }
        gifs[no] = gif
        print(f'  {no:02d} {names.get(no, ""):<6s} {nbytes/1024:5.1f}KB /{colors:3d}色 '
              f'帧{qa["unique_frames"]}/6 质心{reports[no]["pose"]["avg_centroid_shift_px"]}px')

    preview_html(gifs, names, pdir)

    allr = list(reports.values())
    summary = {
        'pack_size': pack_size, 'count': len(reports), 'missing': missing,
        'complete': len(reports) == pack_size and not missing,
        'max_gif_kb': round(max((r['bytes'] for r in allr), default=0) / 1024, 1),
        'all_le_100KB': all(r['bytes'] <= int(cfg['limit_main']) for r in allr),
        'all_240': all(r['size'] == [int(cfg['size'])] * 2 for r in allr),
        'all_6_unique': all(r['unique_frames'] == 6 for r in allr),
        'all_loop_0': all(r['loop'] == 0 for r in allr),
        'all_transparent': all(r['transparency'] == 255 for r in allr),
        'all_no_blank_frame': all(not r['blank_frames'] for r in allr),
        'all_no_edge_crop': all(r['all_no_edge_crop'] for r in allr),
        'tight_margin_items': [r['no'] for r in allr
                               if any(x['tight_margin'] for x in r['boxes'])],
        'items': [reports[k] for k in sorted(reports)],
    }
    (work / 'output' / 'qa.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    print('\n=== QA ===')
    print(json.dumps({k: v for k, v in summary.items() if k != 'items'},
                     ensure_ascii=False, indent=2))
    print('GIF 输出目录:', gdir)


if __name__ == '__main__':
    main()
