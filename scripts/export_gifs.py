#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 E：把 N 段约 10 秒视频导出为 N 张 240x240 透明动态 GIF。

视频路线（v2.0.0）：每段视频均匀抽 12 帧 → cutout 抠图透明
（默认 erode_px=1）→ frame_240 → 按 12 帧时长编码。
本技能只交付 GIF 本体，不产出缩略图 / 封面 / 图标 / 横幅 / CSV / ZIP 投稿包。
附带产物仅为验收用：逐帧深灰底预览、整体预览 HTML、qa.json。

纯本地、零积分。不引用任何具体角色或固定图片。
抽帧需要系统 ffmpeg / ffprobe（`ffmpeg -version` 能跑即可）。

用法：
  python export_gifs.py --workdir <project>
  python export_gifs.py --workdir <project> --only 01 05 18
  python export_gifs.py --workdir <project> --config path/to/config.json

视频位置：<workdir>/videos/NN.mp4，或 <workdir>/videos/NN/ 目录下最新一个
.mp4（重做版自动生效）。抽出的 12 帧留在 <workdir>/frames/NN/ 供复核。
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

import sticker_lib as lib

DEFAULT_CONFIG = {
    'pack_size': 24,
    'size': 240,
    'char_box': [225, 203],
    'durations': [150, 150, 150, 150, 150, 300, 150, 150, 150, 150, 150, 150],
    'color_steps': [255, 224, 192, 160, 128, 96, 64],
    'limit_main': 340_000,
    'cutout_overrides': {},
    'erode_px': 1,
}

N_FRAMES = 12


def load_config(work: Path, override: str = '') -> dict:
    cfg = dict(DEFAULT_CONFIG)
    p = Path(override) if override else work / 'config.json'
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding='utf-8')))
    return cfg


def find_video(videos: Path, no: int) -> Path | None:
    """支持 videos/NN.mp4，或 videos/NN/ 目录下最新一个 .mp4。"""
    folder = videos / f'{no:02d}'
    if folder.is_dir():
        hits = sorted(folder.glob('*.mp4'), key=lambda p: p.stat().st_mtime)
        if hits:
            return hits[-1]
    flat = videos / f'{no:02d}.mp4'
    return flat if flat.exists() else None


def video_duration(video: Path) -> float:
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                        'format=duration', '-of', 'json', str(video)],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f'ffprobe 读不到时长：{video}：{r.stderr.strip()[:200]}')
    return float(json.loads(r.stdout)['format']['duration'])


def extract_frames(video: Path, outdir: Path, n: int = N_FRAMES) -> list[Path]:
    """在视频全长内均匀抽 n 帧。采样点为 i*(dur-0.5)/(n-1)，留 0.5 秒尾巴余量，
    避免抽到片尾黑帧；第 1 帧取视频开头，第 n 帧接近片尾。"""
    dur = video_duration(video)
    times = [round(i * (dur - 0.5) / (n - 1), 2) for i in range(n)]
    outdir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, t in enumerate(times):
        p = outdir / f'C{i+1:02d}.png'
        r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(t),
                            '-i', str(video), '-frames:v', '1', str(p)],
                           capture_output=True, text=True)
        if r.returncode or not p.exists():
            raise RuntimeError(f'ffmpeg 抽帧失败 C{i+1} @ {t}s：{r.stderr.strip()[:200]}')
        paths.append(p)
    return paths


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

    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise SystemExit('缺 ffmpeg / ffprobe：先装好再跑抽帧（`ffmpeg -version` 能跑即可）。')

    work = Path(args.workdir)
    cfg = load_config(work, args.config)
    videos = work / 'videos'
    gdir = work / 'output' / 'gifs'
    pdir = work / 'output' / 'preview'
    fdir = work / 'frames'
    gdir.mkdir(parents=True, exist_ok=True)
    pdir.mkdir(parents=True, exist_ok=True)

    names = {}
    ep = work / 'entries.json'
    if ep.exists():
        doc = json.loads(ep.read_text(encoding='utf-8'))
        for e in (doc['entries'] if isinstance(doc, dict) else doc):
            names[int(e['no'])] = e.get('text', '')

    pack_size = int(cfg['pack_size'])
    want = {int(s) for s in args.only} if args.only else set(range(1, pack_size + 1))
    overrides = {int(k): v for k, v in (cfg.get('cutout_overrides') or {}).items()}

    reports, gifs, missing = {}, {}, []
    for no in sorted(want):
        video = find_video(videos, no)
        if not video:
            missing.append(no)
            print(f'  {no:02d} MISSING video，跳过')
            continue
        frame_paths = extract_frames(video, fdir / f'{no:02d}')
        kw = dict(overrides.get(no, {}))
        kw.setdefault('erode_px', int(cfg.get('erode_px', 1)))
        tiles = []
        for p in frame_paths:
            cell = Image.open(p).convert('RGB')
            tiles.append(lib.cutout(cell, **kw))
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
                'margins': [b[0], b[1], t.width - b[2], t.height - b[3]] if b else None,
                'no_edge_crop': lib.edge_crop_ok(t),
                'tight_margin': bool(b and min(b[0], b[1], t.width - b[2], t.height - b[3]) < 24),
            })
        reports[no] = {
            'no': no, 'text': names.get(no, ''), 'video': video.name,
            'bytes': nbytes, 'colors': colors,
            'size': qa['size'], 'frames': qa['frames'],
            'unique_frames': qa['unique_frames'], 'loop': qa['loop'],
            'transparency': qa['transparency'], 'blank_frames': qa['blank_frames'],
            'boxes': boxes,
            'all_no_edge_crop': all(x['no_edge_crop'] for x in boxes),
            'pose': lib.pose_metrics(frames),
        }
        gifs[no] = gif
        print(f'  {no:02d} {names.get(no, ""):<6s} {nbytes/1024:5.1f}KB /{colors:3d}色 '
              f'帧{qa["unique_frames"]}/12 质心{reports[no]["pose"]["avg_centroid_shift_px"]}px')

    preview_html(gifs, names, pdir)

    allr = list(reports.values())
    summary = {
        'pack_size': pack_size, 'count': len(reports), 'missing': missing,
        'complete': len(reports) == pack_size and not missing,
        'max_gif_kb': round(max((r['bytes'] for r in allr), default=0) / 1024, 1),
        'all_le_340KB': all(r['bytes'] <= int(cfg['limit_main']) for r in allr),
        'all_240': all(r['size'] == [int(cfg['size'])] * 2 for r in allr),
        'all_12_unique': all(r['unique_frames'] == 12 for r in allr),
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
