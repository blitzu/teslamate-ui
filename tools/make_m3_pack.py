"""Genereaza pachetul static/car-m3/*.webp din fotografia de sus a Modelului 3: aceeasi poza, caroseria revopsita in culorile Tesla.
Rulare: python make_m3_pack.py <poza.png> <director_iesire> [--montage out.png]
Vopsea = pixeli luminosi si necolorati din poza (caroseria alba); geamurile, interiorul, farurile si umbrele raman cum sunt."""
import sys, os
import numpy as np
from PIL import Image

TINTS = {'6e757e': '#6e757e', 'aeb6bf': '#aeb6bf', '1c1f23': '#1c1f23', '5b6168': '#5b6168', '1f3f7a': '#1f3f7a', 'b3202b': '#b3202b', '6b1230': '#6b1230'}
W, H = 438, 959


def smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def tint(img, hx):
    a = np.asarray(img.convert('RGBA'), dtype=np.float32) / 255.0
    rgb, al = a[..., :3], a[..., 3:]
    lum = (rgb * np.array([.299, .587, .114], dtype=np.float32)).sum(-1, keepdims=True)
    sat = rgb.max(-1, keepdims=True) - rgb.min(-1, keepdims=True)
    paint = smooth(lum, .34, .62) * (1 - smooth(sat, .10, .28))          # cat de "vopsea alba" e pixelul
    c = np.array([int(hx[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.float32) / 255.0
    shade = np.clip(lum / .90, 0, 1.15)                                    # umbra / lumina din poza (caroseria alba ~0.9)
    body = c * shade
    spec = np.clip((lum - .88) / .12, 0, 1)                                # reflexii puternice: raman luminoase si pe vopsele inchise
    body = body + (1 - c) * spec * .38
    out = rgb * (1 - paint) + np.clip(body, 0, 1) * paint
    return Image.fromarray((np.concatenate([out, al], -1) * 255 + .5).astype(np.uint8), 'RGBA')


def main():
    src, outd = sys.argv[1], sys.argv[2]
    os.makedirs(outd, exist_ok=True)
    base = Image.open(src).convert('RGBA').resize((W, H), Image.LANCZOS)
    res = {'white': base}
    for k, hx in TINTS.items():
        res[k] = tint(base, hx)
    for k, im in res.items():
        im.save(os.path.join(outd, k + '.webp'), 'WEBP', quality=86, method=6, alpha_quality=90)
        print(k, os.path.getsize(os.path.join(outd, k + '.webp')) // 1024, 'KB')
    if '--montage' in sys.argv:
        m = Image.new('RGBA', (W * len(res) // 2, H // 2), (46, 50, 56, 255))
        for i, im in enumerate(res.values()):
            sm = im.resize((W // 2, H // 2), Image.LANCZOS)
            m.alpha_composite(sm, (i * (W // 2), 0))
        m.convert('RGB').save(sys.argv[sys.argv.index('--montage') + 1])


main()
