#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 A：把「一张任意来源的角色图」变成统一的透明形象基准卡。

支持两种入口（技能定位：不内置任何用户图片）：
  1. 用户提供一张图：--input path/to/image.png
  2. 流程自己生成一张图：先由 WorkBuddy 调用 ImageGen 文生图，把输出路径传给 --input

脚本只做本地归一化：已有 alpha 就直接用；纯白/浅色底就抠成透明；
再等比缩放居中到统一画布，产出 character-reference.png 与 character-card.json 骨架。
不调用任何生成模型、不联网、零积分。

用法：
  python prepare_character.py --input <image> --workdir <project>
  python prepare_character.py --input <image> --workdir <project> --no-cutout
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

import sticker_lib as lib

BASE_SIZE = 973          # 基准卡边长（历史项目实测好用值，可改）
MARGIN = 0.93            # 角色最长边占画布比例，四周留白给抠图/缩放余量


def load_character(path: Path, no_cutout: bool):
    im = Image.open(path).convert('RGBA')
    if no_cutout:
        return im
    has_alpha = im.getchannel('A').getextrema()[0] < 250
    if has_alpha:
        return im
    return lib.cutout(im.convert('RGB'), edge_clear=0)


def normalize(im: Image.Image, size: int = BASE_SIZE) -> Image.Image:
    b = im.getchannel('A').getbbox()
    if not b:
        raise ValueError('抠图后整张全透明 —— 输入图可能不是纯白底，或角色与背景同色；'
                         '请加 --no-cutout，或换一张对比更强的图。')
    im = im.crop(b)
    target = int(size * MARGIN)
    im.thumbnail((target, target), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2))
    return canvas


def preview(base: Image.Image, out: Path):
    for name, bg in (('白底验收.png', (255, 255, 255, 255)),
                     ('深灰底验收.png', lib.DARK + (255,))):
        layer = Image.new('RGBA', base.size, bg)
        layer.alpha_composite(base)
        layer.convert('RGB').save(out / name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True, help='角色图路径（用户提供的，或 ImageGen 生成的）')
    ap.add_argument('--workdir', required=True, help='项目工作目录')
    ap.add_argument('--no-cutout', action='store_true', help='输入图已带透明通道，跳过抠图')
    ap.add_argument('--size', type=int, default=BASE_SIZE)
    ap.add_argument('--name', default='', help='角色名，仅写进卡片备注')
    args = ap.parse_args()

    src = Path(args.input)
    work = Path(args.workdir)
    out = work / 'character'
    out.mkdir(parents=True, exist_ok=True)

    raw = load_character(src, args.no_cutout)
    base = normalize(raw, args.size)
    ref = out / 'character-reference.png'
    base.save(ref)
    preview(base, out)

    card = {
        '_readme': [
            '形象基准卡。identity_lock 必须由 WorkBuddy 用 ViewImage 打开 character-reference.png',
            '逐项看清真实结构后手写，禁止凭文件名或文字描述推断。',
            '四层写法见 references/prompt-guide.md。写错一条会污染全部 24 张。',
        ],
        'reference_image': str(ref).replace('\\', '/'),
        'source_image': str(src).replace('\\', '/'),
        'character_name': args.name,
        'identity_lock': 'TODO: 用 ViewImage 打开基准图，按四层结构写英文身份锁',
        'identity_checks': [],
        'expression_channels': [],
        'known_residuals': [],
        'scale': {'size': args.size, 'margin': MARGIN, 'uniform': True},
        'generation_calls': 0,
    }
    (out / 'character-card.json').write_text(
        json.dumps(card, ensure_ascii=False, indent=2), encoding='utf-8')

    b = base.getchannel('A').getbbox()
    print(json.dumps({
        'reference': str(ref),
        'card': str(out / 'character-card.json'),
        'size': list(base.size),
        'alpha_bbox': list(b),
        'opaque_pct': round(100 * sum(1 for v in base.getchannel('A').getdata() if v >= 128)
                            / (base.width * base.height), 2),
        'next': '用 ViewImage 打开基准图，逐项填写 identity_lock / identity_checks，'
                '写入前先读 references/prompt-guide.md 的 R9 规则',
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
