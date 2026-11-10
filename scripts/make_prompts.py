#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 C：把「条目清单 + 形象基准卡」编译成 N 份可直接投喂 ImageGen 的 prompt。

纯本地、零积分。不内置任何具体形象：身份锁全部从 character-card.json 注入。

用法：
  python make_prompts.py --workdir <project>
  python make_prompts.py --workdir <project> --only 01 05 18
  python make_prompts.py --workdir <project> --entries path/to/my-entries.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# ---- 最高优先级：网格独立成格 ----------------------------------------------
# 宽场景 / 远景条目极易被模型画成「一整张连续画面」或留空格、跨格。
# 历史事故：把 WIDE/DISTANT/SIDE-VIEW 写在 prompt 开头就会翻车，
# 把 GRID LAYOUT 提到最高优先级并首尾重复后才稳定。
GRID_LAYOUT = (
    "GRID LAYOUT — HIGHEST PRIORITY. Produce EXACTLY SIX INDEPENDENT 512x512 CELLS "
    "arranged 3 across and 2 down in ONE 1536x1024 canvas. Each cell contains EXACTLY "
    "ONE complete, self-contained picture. NEVER treat the canvas as one continuous scene. "
    "NEVER leave an empty cell. NEVER put two scenes in one cell. NEVER let any object, "
    "character or prop cross a cell border. Cell order: 1 top-left, 2 top-center, "
    "3 top-right, 4 bottom-left, 5 bottom-center, 6 bottom-right. "
    "Keep a clean 24px white margin on all four sides of EVERY cell."
)

CLEAN_SHEET_GUARD = (
    "CLEAN SHEET GUARD — PURE FLAT WHITE #FFFFFF background in every cell. "
    "No gray, no gradient, no floor, no shadow, no horizon, no full-bleed background. "
    "NO grid lines, NO separator lines, NO corner marks. "
    "NO AI-generated text, letters, numbers, name strip, caption bar, watermark, "
    "logo or signature anywhere on the sheet. "
    "NOTE — 'no-caption version' means NO name-caption bar under the sticker, "
    "NOT zero text inside the picture: precise prop text is rendered LOCALLY with a "
    "font AFTER generation, so any prop surface meant to carry text must be drawn as "
    "a perfectly CLEAN BLANK color block with no writing on it."
)

PROP_PERSIST_GUARD = (
    "PROP PERSIST GUARD — Every prop described below is present in ALL SIX frames and "
    "keeps the SAME size, shape, color, count, orientation and position unless the "
    "frame description explicitly says it moves. Props NEVER vanish, NEVER turn into "
    "a different object and NEVER change color between frames. "
    "Props must use warm or dark saturated colors: NO pure white and NO neutral light "
    "gray parts — those get removed by the white-backdrop cutout flood-fill."
)

ACCENT_GUARD = (
    "ACCENT GUARD — Sparkles, sweat drops, stars and glow effects appear ONLY in the "
    "frames explicitly named below, nowhere else."
)

MOTION_DRAMATIC = (
    "CRITICAL — SILHOUETTE MUST BE DRAMATICALLY DIFFERENT IN EVERY FRAME. This is a "
    "physical animation, NOT six near-identical standing portraits with a changed face. "
    "Hip height, head height, foot positions, torso angle and arm span MUST visibly "
    "change between frames. Each pose below is a named, instantly recognizable body shape. "
    "Use FRONTAL 2D silhouette changes only: side lean, shoulder-line slope, head tilt, "
    "arm span, squat, kick, reach. NEVER use depth-direction poses (leaning forward / "
    "leaning backward / turning the back to the viewer / stepping away) — in a frontal "
    "2D drawing they barely change the silhouette and can hide the face."
)

MOTION_STATE = (
    "CRITICAL — THIS IS A SUBTLE STATE / EXPRESSION ANIMATION. All six frames share ONE "
    "stable pose and ONE fixed camera. The animation comes ONLY from real changes in the "
    "face (eyes, pupils, eyebrows, mouth, blush), a tiny breathing rise of the shoulders "
    "and head, and small genuine movements of the hands and props. NEVER slide, scale, "
    "rotate or bob the whole picture to fake motion. NEVER draw six identical frames: "
    "at least THREE facial or hand channels must differ between consecutive frames, "
    "and FRAME 4 must be visibly the strongest."
)

FRAMING = {
    'full': (
        "FULL BODY framing. Character should FILL the cell: about 450-465px tall within "
        "the 512px cell, including both feet in every frame. Keep the SAME character "
        "scale in all six frames."
    ),
    'half': (
        "UPPER-BODY framing from the waist up: head, BOTH hands and all props raised to "
        "chest level and enlarged so fingers and small props stay readable. The cropped "
        "upper body occupies about 430-450px of the 512px cell height, with the head "
        "about 200px tall. The waist is cut by the framing ON PURPOSE. Head, both hands "
        "and every prop must be fully inside the cell. Keep EXACTLY the same framing and "
        "scale in all six frames. Even without legs, torso lean, shoulder height, head "
        "tilt and arm span MUST change between frames."
    ),
    'scene': (
        "WIDE SCENE framing. The character and its props form ONE coherent group occupying "
        "about 400-450px of the 512px cell WIDTH, centered with generous empty white space "
        "around it. The character is deliberately SMALLER than in a standard sticker but "
        "still fully drawn: head, both hands, both feet and every prop inside the cell, "
        "nothing cropped. Keep exactly the same camera angle and scale in all six frames. "
        "NO full-bleed background, NO sea, NO sky, NO horizon, NO ground plane, NO shadow."
    ),
}

NEGATIVE = (
    "STRICT NEGATIVE: NO sliding, scaling, rotating or tilting the whole picture as fake "
    "motion — all movement must come from real joints and real body parts. "
    "No six identical standing poses. No one-arm-only animation while the rest of the "
    "body stays frozen. No cropped head, hands, feet or props. No missing or duplicated "
    "limbs. No extra characters. No props other than the ones described. "
    "No pure-white or neutral-gray prop parts. No gray or colored background. "
    "NO AI-written text, letters, numbers, name strip, caption bar, watermark, logo or "
    "signature anywhere. FRAME 6 MUST loop cleanly back to FRAME 1."
)

TEMPLATE = """{grid}

{clean}

{framing}

{motion}
{frames}

FACE / EXPRESSION: {face} Six DIFFERENT faces, never the same face repeated. Use the
expression channels listed in the identity card; any part that is a FIXED ORNAMENT must
stay STATIC and never act.

{prop}

{prop_guard}

{accent}

{identity}

{negative}

FINAL REMINDER — SIX INDEPENDENT 512x512 CELLS, EACH ONE COMPLETE PICTURE, PURE WHITE
BACKGROUND, NO BORDER CROSSING, NO EMPTY CELL, NO GRID LINES, NO TEXT, NO WATERMARK.
"""


def build(entry: dict, card: dict) -> str:
    frames = entry.get('frames') or []
    if len(frames) != 6:
        raise ValueError(f"条目 {entry.get('no')} 需要正好 6 帧描述，实际 {len(frames)}")
    lines = '\n'.join(f'FRAME {i+1} — {t}' for i, t in enumerate(frames))
    prop = entry.get('prop_spec') or 'PROP DETAIL — NO PROPS AT ALL. The hands and body alone carry the meaning.'
    if entry.get('extra_guard'):
        prop += '\n\n' + entry['extra_guard']
    motion = MOTION_STATE if entry.get('motion') == 'state' else MOTION_DRAMATIC
    identity = (card.get('identity_lock') or '').strip()
    if not identity or identity.startswith('TODO'):
        raise ValueError('character-card.json 的 identity_lock 还没填。'
                         '先用 ViewImage 打开基准图逐项核对该写什么，见 R9。')
    # prompt-guide.md 的四层模板自带 "IDENTITY LOCK — ..." 抬头；若原样抄进
    # character-card.json，这里再加一次标题就会重复，反而稀释最高优先级约束。
    # 两种情况都接受：自带抬头就原样用，没有就补一个。
    if not identity.upper().startswith('IDENTITY LOCK'):
        identity = 'IDENTITY LOCK:\n' + identity
    return TEMPLATE.format(
        grid=GRID_LAYOUT, clean=CLEAN_SHEET_GUARD,
        framing=FRAMING.get(entry.get('composition', 'full'), FRAMING['full']),
        motion=motion, frames=lines,
        face=entry.get('face', 'Expression changes progressively across the six frames.'),
        prop=prop, prop_guard=PROP_PERSIST_GUARD, accent=ACCENT_GUARD,
        identity=identity, negative=NEGATIVE,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workdir', required=True)
    ap.add_argument('--entries', default='')
    ap.add_argument('--only', nargs='*', default=[])
    args = ap.parse_args()

    work = Path(args.workdir)
    entries_path = Path(args.entries) if args.entries else work / 'entries.json'
    card_path = work / 'character' / 'character-card.json'
    if not entries_path.exists():
        raise SystemExit(f'缺条目清单：{entries_path}（从 assets/entries-24.json 复制）')
    if not card_path.exists():
        raise SystemExit(f'缺形象卡：{card_path}（先跑 prepare_character.py）')

    doc = json.loads(entries_path.read_text(encoding='utf-8'))
    card = json.loads(card_path.read_text(encoding='utf-8'))
    entries = doc['entries'] if isinstance(doc, dict) else doc
    out = work / 'prompts'
    out.mkdir(parents=True, exist_ok=True)

    want = {s.zfill(2) for s in args.only}
    written = []
    for e in entries:
        no = f"{int(e['no']):02d}"
        if want and no not in want:
            continue
        text = build(e, card)
        p = out / f'{no}.txt'
        p.write_text(text, encoding='utf-8')
        written.append(str(p))
    print(json.dumps({'count': len(written), 'prompts_dir': str(out),
                      'files': written[:5], 'note': '逐份投入 ImageGen，image1 固定为 character-reference.png'},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
