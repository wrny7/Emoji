#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 C：把「条目清单 + 形象基准卡」编译成 N 份视频 prompt。

视频路线（v2.0.0）：每份 prompt 对应一段约 10 秒视频，角色参考图作视频
的 image 输入，固定机位、纯白底、12 帧动作分解（C1 站立、C2–C4 蓄势、
C5–C9 峰值区微变、C10–C11 回落、C12 回到 C1），循环闭合。
编译本身纯本地、零积分；视频生成由 agent 的视频生成能力执行，不在本脚本里。

用法：
  python make_prompts.py --workdir <project>
  python make_prompts.py --workdir <project> --only 01 05 18
  python make_prompts.py --workdir <project> --entries path/to/my-entries.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# ---- 通用拍摄约束：固定机位 + 纯白底 + 循环闭合 ------------------------------
CAMERA_GUARD = (
    "CAMERA — FIXED camera: no zoom, no pan, no dolly. Full body centered at the "
    "same size and position in every frame. Plain pure-white background, no text, "
    "no watermark, no logo, no other character. The character stays fully inside "
    "the frame with clear white margins on all sides in every frame."
)

PROP_PERSIST_GUARD = (
    "PROP PERSIST GUARD — Every prop described below is present in ALL TWELVE frames "
    "and keeps the SAME size, shape, color, count, orientation and position unless "
    "the frame description explicitly says it moves. Props NEVER vanish, NEVER turn "
    "into a different object and NEVER change color between frames. Props must use "
    "warm or dark saturated colors: NO pure white and NO neutral light gray parts — "
    "those get removed by the white-backdrop cutout flood-fill."
)

MOTION_DRAMATIC = (
    "MOTION — DRAMATIC. This is a physical animation, NOT twelve near-identical "
    "standing portraits with a changed face. Hip height, head height, foot positions, "
    "torso angle and arm span MUST visibly change between frames. Each frame below is "
    "a named, instantly recognizable body shape. Forward lean and stepping are allowed "
    "as long as the face stays fully visible and the character stays fully inside the "
    "frame. A run-in from far away must STOP at normal full-body size — the character "
    "must NEVER fill the frame or become a close-up at any moment."
)

MOTION_STATE = (
    "MOTION — SUBTLE STATE / EXPRESSION ANIMATION. All twelve frames share ONE stable "
    "pose and ONE fixed camera. The animation comes ONLY from real changes in the face "
    "(eyes, pupils, eyebrows, mouth, blush), a tiny breathing rise of the shoulders "
    "and head, and small genuine movements of the hands and props. NEVER slide, scale, "
    "rotate or bob the whole picture to fake motion. NEVER draw twelve identical frames: "
    "at least THREE facial or hand channels must differ between consecutive frames, "
    "and the PEAK ZONE (frames 5-9) must be visibly the strongest."
)

MOTION_PRINCIPLES = (
    "MOTION PRINCIPLES — Highlight the KEY action; normal body-coordination movement "
    "is welcome, but NEVER add random extra actions that do not serve the meaning. "
    "For gesture stickers, the gesture itself is the foreground: make it big, hold it "
    "steady, keep the face secondary. Keep the same whitespace/margins across the whole "
    "set (character max 225x203 inside the 240 canvas)."
)

NEGATIVE = (
    "STRICT NEGATIVE: NO sliding, scaling, rotating or tilting the whole picture as fake "
    "motion — all movement must come from real joints and real body parts. "
    "No twelve identical standing poses. No one-arm-only animation while the rest of the "
    "body stays frozen. No cropped head, hands, feet or props. No missing or duplicated "
    "limbs. No extra characters. No props other than the ones described. "
    "No pure-white or neutral-gray prop parts. No gray or colored background. "
    "NO AI-written text, letters, numbers, name strip, caption bar, watermark, logo or "
    "signature anywhere. FRAME 12 MUST match FRAME 1 exactly so the loop closes with "
    "no jump."
)

TEMPLATE = """{identity}

VIDEO PROMPT — {no} {text}
A single continuous shot of about 10 seconds, smooth loopable motion.

{camera}

{motion}
{principles}
{frames}

FACE / EXPRESSION: {face} Twelve DIFFERENT faces across the frames, never the same face repeated. Use the
expression channels listed in the identity card; any part that is a FIXED ORNAMENT must
stay STATIC and never act.

{prop}

{prop_guard}

{negative}

FINAL REMINDER — FIXED CAMERA, FULL BODY, PURE WHITE BACKGROUND, NO TEXT, NO WATERMARK,
FRAME 12 MATCHES FRAME 1 SO THE LOOP CLOSES.
"""


def build(entry: dict, card: dict) -> str:
    frames = entry.get('frames') or []
    if len(frames) != 12:
        raise ValueError(f"条目 {entry.get('no')} 需要正好 12 帧描述，实际 {len(frames)}")
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
        identity=identity, no=f"{int(entry['no']):02d}",
        text=entry.get('text', ''),
        camera=CAMERA_GUARD, motion=motion, principles=MOTION_PRINCIPLES,
        frames=lines,
        face=entry.get('face', 'Expression changes progressively across the twelve frames.'),
        prop=prop, prop_guard=PROP_PERSIST_GUARD, negative=NEGATIVE,
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
                      'files': written[:5],
                      'note': '每份 prompt 生成一段约 10 秒视频，角色参考图作视频 image 输入；'
                              '再用 export_gifs.py 抽 12 帧导出'},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
