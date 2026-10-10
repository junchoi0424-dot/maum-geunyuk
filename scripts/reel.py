#!/usr/bin/env python3
"""posts.json의 글 하나를 9:16 텍스트 릴스(mp4)로 만든다.

  python3 scripts/reel.py 011            → reels/011.mp4
  python3 scripts/reel.py 011 --still    → 마지막 장면 미리보기 PNG만
  python3 scripts/reel.py 011 --hook "정체기, 사실 좋은 신호예요" --tag C   → reels/011_C.mp4 (후킹 A/B 테스트용)

구성: 0초 후킹(캡션 첫 줄) → 1초부터 문장 한 줄씩 등장 → 저장 유도 + 핸들
첫 장(single/cover) 문장을 쓰며, *강조*는 라임색으로 표시한다.
배경음은 저작권 걱정 없게 직접 합성한 잔잔한 패드 + 줄 등장 효과음.
"""
import json
import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = Path.home() / "Library/Fonts"
W, H, FPS = 1080, 1920, 30
BG, FG, DIM, ACCENT = (28, 28, 28), (242, 239, 232), (138, 135, 128), (198, 242, 78)
HANDLE = "@maum.geunyuk"

LINE_START, LINE_GAP, FADE = 1.0, 0.9, 0.35  # 초
HOLD_AFTER = 3.2


def font(weight, size):
    return ImageFont.truetype(str(FONTS / f"Pretendard-{weight}.otf"), size)


F_HOOK = font("Bold", 50)
F_LINE = font("ExtraBold", 84)
F_SMALL = font("SemiBold", 40)
F_BRAND = font("Bold", 36)


def parse(line):
    """'버티는 *힘*이' → [('버티는 ', False), ('힘', True), ('이', False)]"""
    parts, on = [], False
    for i, chunk in enumerate(line.split("*")):
        if chunk:
            parts.append((chunk, on))
        on = not on
    return parts


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def draw_rich(img, parts, cy, fnt, alpha, dy):
    d = ImageDraw.Draw(img)
    total = sum(d.textlength(t, font=fnt) for t, _ in parts)
    x = (W - total) / 2
    for t, hi in parts:
        c = ACCENT if hi else FG
        col = tuple(int(BG[k] + (c[k] - BG[k]) * alpha) for k in range(3))
        d.text((x, cy + dy), t, font=fnt, fill=col, anchor="lm")
        x += d.textlength(t, font=fnt)


def blend(c, a):
    return tuple(int(BG[k] + (c[k] - BG[k]) * a) for k in range(3))


def build(post):
    slide = post["slides"][0]
    lines = [l for l in slide["text"].split("\n")]
    hook = post["caption"].split("\n")[0].strip()
    n_text = sum(1 for l in lines if l.strip())
    end_lines = LINE_START + (n_text - 1) * LINE_GAP + FADE
    duration = end_lines + HOLD_AFTER
    return hook, lines, duration


def frame(t, hook, lines, duration):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 브랜드 (상단 UI 아래)
    d.text((W / 2, 400), "마음근육", font=F_BRAND, fill=ACCENT, anchor="mm")

    # 후킹: 0~0.3초 등장
    a = ease(t / 0.3)
    if a > 0:
        tw = d.textlength(hook, font=F_HOOK)
        pad_x, h = 44, 104
        cx, cy = W / 2, 660 + (1 - a) * 20
        box = [cx - tw / 2 - pad_x, cy - h / 2, cx + tw / 2 + pad_x, cy + h / 2]
        d.rounded_rectangle(box, radius=h / 2, outline=blend(ACCENT, a), width=4)
        d.text((cx, cy), hook, font=F_HOOK, fill=blend(ACCENT, a), anchor="mm")

    # 본문: 한 줄씩
    lh = 128
    block = len(lines) * lh
    top = 1080 - block / 2 + lh / 2
    k = 0
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        start = LINE_START + k * LINE_GAP
        k += 1
        p = ease((t - start) / FADE)
        if p <= 0:
            continue
        draw_rich(img, parse(line), top + i * lh, F_LINE, p, (1 - p) * 28)

    # 마무리: 저장 유도 + 핸들
    end_lines = LINE_START + (k - 1) * LINE_GAP + FADE
    q = ease((t - end_lines - 0.6) / 0.5)
    if q > 0:
        cta = "힘들 때 다시 꺼내 보세요" if "저장" in hook else "저장해두고 힘들 때 꺼내 보세요"
        d.text((W / 2, 1490), cta, font=F_SMALL, fill=blend(DIM, q), anchor="mm")
        d.text((W / 2, 1560), HANDLE, font=F_SMALL, fill=blend(ACCENT, q), anchor="mm")
    return img


def audio(path, duration, n_lines):
    sr = 48000
    t = np.arange(int(sr * duration)) / sr
    # 잔잔한 패드 (A단조 계열), 천천히 올라왔다 끝에서 사라짐
    notes = [110.0, 164.81, 220.0, 261.63, 329.63]
    pad = sum(np.sin(2 * math.pi * f * t + i) * (0.5 if i < 2 else 0.3) for i, f in enumerate(notes))
    pad *= 0.6 + 0.4 * np.sin(2 * math.pi * 0.25 * t)  # 느린 흔들림
    env = np.minimum(1, t / 1.2) * np.minimum(1, (duration - t) / 1.0)
    out = pad * env * 0.06
    # 줄 등장 효과음 (부드러운 플럭)
    for k in range(n_lines + 1):
        s = 0.0 if k == 0 else LINE_START + (k - 1) * LINE_GAP
        idx = int(s * sr)
        tt = np.arange(int(sr * 0.6)) / sr
        f = 880.0 if k == 0 else 659.25
        pl = np.sin(2 * math.pi * f * tt) * np.exp(-tt * 9) * 0.18
        seg = out[idx: idx + len(pl)]
        seg += pl[: len(seg)]
    out = np.clip(out, -1, 1)
    stereo = (np.stack([out, out], axis=1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(stereo.tobytes())


def main():
    args = sys.argv[1:]
    pid = args[0]
    opt = lambda k: args[args.index(k) + 1] if k in args else None
    posts = {p["id"]: p for p in json.loads((ROOT / "posts.json").read_text())}
    post = posts[pid]
    hook, lines, duration = build(post)
    hook = opt("--hook") or hook
    name = f"{pid}_{opt('--tag')}" if opt("--tag") else pid
    outdir = ROOT / "reels"
    outdir.mkdir(exist_ok=True)

    if "--still" in sys.argv:
        frame(duration - 0.1, hook, lines, duration).save(outdir / f"{name}_still.png")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        n = int(duration * FPS)
        for i in range(n):
            frame(i / FPS, hook, lines, duration).save(tmp / f"{i:04d}.png")
        wav = tmp / "a.wav"
        audio(wav, duration, sum(1 for l in lines if l.strip()))
        out = outdir / f"{name}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(tmp / "%04d.png"),
            "-i", str(wav), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out),
        ], check=True)
    print(f"✓ {out} ({duration:.1f}초)")


if __name__ == "__main__":
    main()
