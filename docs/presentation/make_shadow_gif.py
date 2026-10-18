import glob, math, re, sys
from datetime import datetime, timedelta
import numpy as np, tifffile
from PIL import Image, ImageDraw, ImageFont
src = open('/mnt/project-files/building/window_sun/window_sun.py', encoding='utf-8').read()
g = {'math': math, 'timedelta': timedelta, 'datetime': datetime}
exec(src[src.index('def sun_pos'):src.index('class Surface')], g)
sun_pos = g['sun_pos']
FONT = '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'
files = sorted(glob.glob('/mnt/project-files/Shadow_20251021_*_LST.tif'))
LIT = np.array([246, 241, 228]); SH = np.array([52, 63, 92]); NOD = np.array([255, 255, 255])
def colorize(frac, nod):
    rgb = (SH[None, None] + (LIT - SH)[None, None] * frac[..., None]).astype(np.uint8)
    rgb[nod] = NOD
    return rgb
full, zoom = [], []
C_col, C_row = int((201539.8 - 198064.0534) / 2), int((558651.1157 - 556482.3) / 2)
for f in files:
    hhmm = re.search(r'_(\d{4})_LST', f).group(1)
    t = datetime(2025, 10, 21, int(hhmm[:2]), int(hhmm[2:]))
    alt, az = sun_pos(t, 37.606, 127.018)
    a = tifffile.imread(f).astype(np.float32)
    nod = a < -1
    a[nod] = 1
    H, W = a.shape; k = 4
    h2, w2 = H // k, W // k
    frac = a[:h2 * k, :w2 * k].reshape(h2, k, w2, k).mean(axis=(1, 3))
    full.append((colorize(frac, nod[:h2 * k:k, :w2 * k:k]), t, alt, az))
    r0, c0 = C_row - 225, C_col - 350
    z = a[r0:r0 + 450, c0:c0 + 700]
    zoom.append((colorize(z, nod[r0:r0 + 450, c0:c0 + 700]), t, alt, az))
    print(hhmm, round(alt, 1), round(az, 1), round(1 - a[~nod].mean(), 3), flush=True)

def frame(rgb, t, alt, az, title, scale, bar_m, px_m):
    img = Image.fromarray(rgb)
    if scale != 1:
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.NEAREST)
    top = 70
    out = Image.new('RGB', (img.width, img.height + top), (255, 255, 255))
    out.paste(img, (0, top))
    d = ImageDraw.Draw(out)
    fb = ImageFont.truetype(FONT, 26); fs = ImageFont.truetype(FONT, 17)
    d.text((16, 10), t.strftime('2025년 10월 21일  %H:%M'), font=fb, fill=(30, 38, 48))
    d.text((16, 44), f'{title} · 태양 고도 {max(alt,0):.0f}° · 방위각 {az:.0f}°', font=fs, fill=(74, 88, 102))
    # sun direction arrow (compass, top right)
    cx, cy, R = out.width - 52, top + 52, 34
    d.ellipse((cx - R, cy - R, cx + R, cy + R), fill=(255, 255, 255), outline=(150, 160, 170), width=2)
    d.text((cx - 5, cy - R - 2), 'N', font=ImageFont.truetype(FONT, 13), fill=(74, 88, 102))
    ex, ey = cx + R * 0.8 * math.sin(math.radians(az)), cy - R * 0.8 * math.cos(math.radians(az))
    d.line((cx, cy, ex, ey), fill=(232, 150, 46), width=4)
    d.ellipse((ex - 7, ey - 7, ex + 7, ey + 7), fill=(232, 150, 46))
    # scale bar + legend (bottom left)
    L = int(bar_m / px_m * scale); y = out.height - 26
    d.rectangle((14, y - 34, 26 + max(L, 200), y + 14), fill=(255, 255, 255))
    d.line((20, y, 20 + L, y), fill=(30, 38, 48), width=4)
    d.text((24 + L, y - 10), f'{bar_m if bar_m < 1000 else bar_m // 1000}{"m" if bar_m < 1000 else "km"}', font=fs, fill=(30, 38, 48))
    d.rectangle((20, y - 28, 36, y - 14), fill=tuple(SH)); d.text((42, y - 31), '그림자', font=fs, fill=(30, 38, 48))
    d.rectangle((110, y - 28, 126, y - 14), fill=tuple(LIT), outline=(150, 150, 150)); d.text((132, y - 31), '햇빛', font=fs, fill=(30, 38, 48))
    return out

def save(frames, path, **kw):
    ims = [frame(*f, **kw) for f in frames]
    pal = [im.convert('P', palette=Image.ADAPTIVE, colors=128) for im in ims]
    dur = [500] * len(pal); dur[-1] = 1500
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=dur, loop=0, optimize=True)
    ims[len(ims) // 2].save(path.replace('.gif', '_12시.png'))
save(full, 'shadow_seongbuk.gif', title='성북구 전체 (UMEP, 30분 간격)', scale=1, bar_m=1000, px_m=8)
save(zoom, 'shadow_gileum.gif', title='길음뉴타운 주변 확대', scale=1.3, bar_m=200, px_m=2)
