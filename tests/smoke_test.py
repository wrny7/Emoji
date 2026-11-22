# -*- coding: utf-8 -*-
"""端到端冒烟测试：纯本地、不联网、零积分。

视频路线（v2.0.0）：造假角色图 + 12 张假视频帧（位置/宽度逐帧不同），
跑通 A → C → E 的本地部分，验证 24 份视频 prompt、GIF 尺寸/帧数/体积/
透明度/循环/帧互异/空白帧/裁切。视频生成本身由 agent 的视频生成能力执行，
不在本测试里；抽帧（ffmpeg 部分）也不在测试覆盖内。

    python tests/smoke_test.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
ASSETS = ROOT / 'assets'
CHECK_KEYS = ('all_240', 'all_le_340KB', 'all_12_unique', 'all_loop_0',
              'all_transparent', 'all_no_blank_frame', 'all_no_edge_crop')

sys.path.insert(0, str(SCRIPTS))
import sticker_lib as lib


def run(work: Path, script: str, *args: str) -> None:
    cmd = [sys.executable, str(SCRIPTS / script), '--workdir', str(work), *args]
    p = subprocess.run(cmd, cwd=str(SCRIPTS), capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if p.returncode:
        print(p.stdout[-1200:])
        print('STDERR:', p.stderr[-1500:])
        raise SystemExit(f'{script} FAILED rc={p.returncode}')
    print(f'  OK  {script} {" ".join(args)}')


def make_fake_character(path: Path) -> None:
    """白底 + 一个暖橙角色，用作阶段 A 的输入。"""
    im = Image.new('RGB', (800, 800), 'white')
    d = ImageDraw.Draw(im)
    d.ellipse((250, 120, 550, 420), fill=(238, 196, 120))
    d.rounded_rectangle((290, 400, 510, 700), radius=60, fill=(238, 196, 120))
    d.ellipse((310, 200, 360, 250), fill=(60, 90, 130))
    d.ellipse((440, 200, 490, 250), fill=(60, 90, 130))
    im.save(path)


def make_fake_frames() -> list:
    """12 张假视频帧：角色位置/宽度逐帧不同 → 12 帧互异且质心有位移。

    注意第 1 帧与第 12 帧不能画成完全一样，否则 unique_frames 会如实报 11/12。
    """
    frames = []
    for i in range(12):
        im = Image.new('RGB', (512, 512), 'white')
        d = ImageDraw.Draw(im)
        cx = 256 + [0, -30, 35, 60, -50, 18, 45, -20, 55, -40, 25, 10][i]
        half = [110, 125, 100, 150, 95, 135, 140, 105, 145, 100, 130, 115][i]
        d.ellipse((cx - half, 150, cx + half, 460), fill=(238, 196, 120))
        d.rounded_rectangle((cx - 70, 320, cx + 70, 470), radius=20,
                            fill=(60, 90, 130))
        frames.append(im)
    return frames


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='sticker-smoke-') as tmp:
        work = Path(tmp)
        char_path = work / 'fake-character.png'
        make_fake_character(char_path)

        (work / 'entries.json').write_text(
            (ASSETS / 'entries-24.json').read_text(encoding='utf-8'),
            encoding='utf-8')

        # 阶段 A：形象归一化
        run(work, 'prepare_character.py', '--input', str(char_path))
        card_path = work / 'character' / 'character-card.json'
        card = json.loads(card_path.read_text(encoding='utf-8'))
        card['identity_lock'] = (
            'IDENTITY LOCK: (1) A single warm-cream round character with no headwear. '
            '(2) Two large blue eyes always fully visible, no glasses over the eyes. '
            '(3) A small rosy oval is the real mouth; no beak, no animating the mouth shape. '
            '(4) Blue scarf at the neck, warm-cream egg-shaped body, both hands and feet visible.'
        )
        card['identity_checks'] = ['eyes fully visible', 'no headwear over eyes']
        card['expression_channels'] = ['eyes', 'mouth', 'brows']
        card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2),
                             encoding='utf-8')

        # 阶段 C：编译 24 份视频 prompt
        run(work, 'make_prompts.py')
        prompts = sorted((work / 'prompts').glob('*.txt'))
        assert len(prompts) == 24, f'prompt 数量 {len(prompts)} != 24'
        first = prompts[0].read_text(encoding='utf-8')
        assert first.count('IDENTITY LOCK') == 1, '身份锁标题重复'
        assert 'FRAME 12' in first and 'FRAME 1' in first, '缺 12 帧描述'

        # 阶段 E：本地导出（用假视频帧代替真实视频抽帧）
        gdir = work / 'output' / 'gifs'
        pdir = work / 'output' / 'preview'
        gdir.mkdir(parents=True, exist_ok=True)
        pdir.mkdir(parents=True, exist_ok=True)
        reports, gifs = {}, {}
        for no in (1, 10, 18):
            tiles = [lib.cutout(f, erode_px=1) for f in make_fake_frames()]
            frames = [lib.frame_240(t) for t in tiles]
            gif = gdir / f'{no:02d}.gif'
            nbytes, colors = lib.encode_gif(frames, gif)
            qa = lib.inspect_gif(gif)
            lib.strip_dark(tiles, pdir / f'{no:02d}-逐帧.png')
            reports[no] = {'no': no, 'bytes': nbytes, 'colors': colors, **qa,
                           'all_no_edge_crop': all(lib.edge_crop_ok(t) for t in tiles),
                           'pose': lib.pose_metrics(frames)}
            gifs[no] = gif
            print(f'  OK  {no:02d}.gif 240x240 / {qa["unique_frames"]} 帧 / '
                  f'{nbytes / 1024:.1f}KB / {colors}色')

        qa_summary = {
            'count': len(reports), 'missing': [],
            'complete': len(reports) == 3,
            'all_le_340KB': all(r['bytes'] <= 340_000 for r in reports.values()),
            'all_240': all(r['size'] == [240, 240] for r in reports.values()),
            'all_12_unique': all(r['unique_frames'] == 12 for r in reports.values()),
            'all_loop_0': all(r['loop'] == 0 for r in reports.values()),
            'all_transparent': all(r['transparency'] == 255 for r in reports.values()),
            'all_no_blank_frame': all(not r['blank_frames'] for r in reports.values()),
            'all_no_edge_crop': all(r['all_no_edge_crop'] for r in reports.values()),
        }
        for key in CHECK_KEYS:
            assert qa_summary[key] is True, f'QA 未通过: {key}'
        for p in gifs.values():
            with Image.open(p) as im:
                assert im.size == (240, 240), f'{p.name} 尺寸 {im.size}'
                assert im.n_frames == 12, f'{p.name} 帧数 {im.n_frames}'
            assert p.stat().st_size <= 340_000, f'{p.name} 超限'

        print(f'\nSMOKE TEST PASSED — {len(prompts)} prompts, {len(gifs)} GIFs, '
              f'{len(CHECK_KEYS)} QA checks all green')


if __name__ == '__main__':
    main()
