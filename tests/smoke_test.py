# -*- coding: utf-8 -*-
"""端到端冒烟测试：纯本地、不联网、零积分。

造假角色图 + 3 张假 1536x1024 六格图集，跑通 A → C → D → E，
验证 24 份 prompt、GIF 尺寸/帧数/体积/透明度/循环/帧互异/空白帧/裁切。

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
CHECK_KEYS = ('all_240', 'all_le_100KB', 'all_6_unique', 'all_loop_0',
              'all_transparent', 'all_no_blank_frame', 'all_no_edge_crop')


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


def make_fake_sheet(path: Path) -> None:
    """3x2 六格，每格角色位置/宽度都不同 → 6 帧互异且质心有位移。

    注意第 1 帧与第 6 帧不能画成完全一样，否则 unique_frames 会如实报 5/6。
    """
    sheet = Image.new('RGB', (1536, 1024), 'white')
    d = ImageDraw.Draw(sheet)
    for i in range(6):
        r, c = divmod(i, 3)
        x0, y0 = c * 512, r * 512
        cx = 256 + [0, -30, 35, 60, -50, 18][i]
        half = [110, 125, 100, 150, 95, 135][i]
        d.ellipse((x0 + cx - half, y0 + 150, x0 + cx + half, y0 + 460),
                  fill=(238, 196, 120))
        d.rounded_rectangle((x0 + cx - 70, y0 + 320, x0 + cx + 70, y0 + 470),
                            radius=20, fill=(60, 90, 130))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='sticker-smoke-') as tmp:
        work = Path(tmp)
        char_path = work / 'fake-character.png'
        make_fake_character(char_path)
        for no in (1, 10, 18):
            make_fake_sheet(work / 'sheets' / f'{no:02d}' / 'sheet.png')

        (work / 'entries.json').write_text(
            (ASSETS / 'entries-24.json').read_text(encoding='utf-8'),
            encoding='utf-8')

        # 阶段 A
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

        # 阶段 C / D / E
        run(work, 'make_prompts.py')
        run(work, 'check_sheet.py', '--only', '01', '10', '18')
        run(work, 'export_gifs.py', '--only', '01', '10', '18')

        # 产物校验
        qa = json.loads((work / 'output' / 'qa.json').read_text(encoding='utf-8'))
        prompts = sorted((work / 'prompts').glob('*.txt'))
        gifs = sorted((work / 'output' / 'gifs').glob('*.gif'))

        assert len(prompts) == 24, f'prompt 数量 {len(prompts)} != 24'
        assert len(gifs) == 3, f'GIF 数量 {len(gifs)} != 3'
        assert [p.name for p in gifs] == ['01.gif', '10.gif', '18.gif']
        assert qa['count'] == 3 and qa['missing'] == []

        # 身份锁抬头不能重复（自带抬头 / 不带抬头两种情况）
        first = prompts[0].read_text(encoding='utf-8')
        assert first.count('IDENTITY LOCK') == 1, '身份锁标题重复'

        for key in CHECK_KEYS:
            assert qa[key] is True, f'QA 未通过: {key}'
        for p in gifs:
            with Image.open(p) as im:
                assert im.size == (240, 240), f'{p.name} 尺寸 {im.size}'
                assert im.n_frames == 6, f'{p.name} 帧数 {im.n_frames}'
            assert p.stat().st_size <= 98_000, f'{p.name} 超限'
            print(f'  OK  {p.name} 240x240 / 6 帧 / '
                  f'{p.stat().st_size / 1024:.1f}KB')

        print(f'\nSMOKE TEST PASSED — {len(prompts)} prompts, {len(gifs)} GIFs, '
              f'{len(CHECK_KEYS)} QA checks all green')


if __name__ == '__main__':
    main()
