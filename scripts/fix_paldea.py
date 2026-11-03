"""Encaixa o mapa ampliado do centro de Paldea ('paldea') no buraco preto do mapa geral ('paldea-2') e
leva os pinos para o mapa geral. Rodar depois de build_maps.py e antes de apply_overrides.py."""
import json, os, sys
import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE_DIR, '..', 'data')
sys.stdout.reconfigure(encoding='utf-8')

idx_p = os.path.join(DATA, 'maps', 'index.json')
with open(idx_p, encoding='utf-8') as f:
    index = json.load(f)
if 'paldea' not in index or 'paldea-2' not in index:
    sys.exit('nada a fazer')
small = cv2.imread(os.path.join(DATA, index['paldea']['arquivo']))      # centro ampliado
big = cv2.imread(os.path.join(DATA, index['paldea-2']['arquivo']))      # região inteira com buraco
sift = cv2.SIFT_create(8000)
k1, d1 = sift.detectAndCompute(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), None)
k2, d2 = sift.detectAndCompute(cv2.cvtColor(big, cv2.COLOR_BGR2GRAY), None)
m = cv2.BFMatcher().knnMatch(d1, d2, k=2)
good = [a for a, b in m if a.distance < 0.75 * b.distance]
src = np.float32([k1[g.queryIdx].pt for g in good]); dst = np.float32([k2[g.trainIdx].pt for g in good])
M, inl = cv2.estimateAffinePartial2D(src, dst, ransacReprojThreshold=4, maxIters=5000)
print('matches', len(good), 'inliers', int(inl.sum()) if inl is not None else 0, 'escala', None if M is None else np.hypot(M[0, 0], M[1, 0]))
assert M is not None and inl.sum() >= 25, 'registro falhou'
H, W = big.shape[:2]
warp = cv2.warpAffine(small, M, (W, H), flags=cv2.INTER_AREA)
cover = cv2.warpAffine(np.full(small.shape[:2], 255, np.uint8), M, (W, H)) > 0
hole = big.max(axis=2) < 12
fill = hole & cover
big[fill] = warp[fill]
big[hole & ~cover] = (110, 120, 90)  # resto do buraco (fora do recorte): tom neutro
cv2.imwrite(os.path.join(DATA, index['paldea-2']['arquivo']), big, [cv2.IMWRITE_WEBP_QUALITY, 80])
print('pixels preenchidos', int(fill.sum()), 'restantes', int((hole & ~cover).sum()))

with open(os.path.join(DATA, 'locs.json'), encoding='utf-8') as f:
    locs = json.load(f)
sw, sh = index['paldea']['w'], index['paldea']['h']
n = 0
for v in locs.values():
    if v.get('mapa') != 'paldea' or v.get('x') is None:
        continue
    p = M @ np.array([v['x'] * sw / 100, v['y'] * sh / 100, 1])
    v['x'], v['y'] = round(100 * p[0] / W, 1), round(100 * p[1] / H, 1)
    if v.get('bbox'):
        a = M @ np.array([v['bbox'][0] * sw / 100, v['bbox'][1] * sh / 100, 1])
        b = M @ np.array([v['bbox'][2] * sw / 100, v['bbox'][3] * sh / 100, 1])
        v['bbox'] = [round(100 * a[0] / W, 1), round(100 * a[1] / H, 1), round(100 * b[0] / W, 1), round(100 * b[1] / H, 1)]
    v['mapa'] = 'paldea-2'; n += 1
print('pinos movidos', n)
index['paldea-2']['titulo'] = 'Paldea'
os.remove(os.path.join(DATA, index['paldea']['arquivo']))
del index['paldea']
with open(os.path.join(DATA, 'locs.json'), 'w', encoding='utf-8') as f:
    json.dump(locs, f, ensure_ascii=False, separators=(',', ':'))
with open(idx_p, 'w', encoding='utf-8') as f:
    json.dump(index, f, ensure_ascii=False, indent=1)
# checagem
chk = big.copy()
for v in locs.values():
    if v.get('mapa') == 'paldea-2' and v.get('x') is not None:
        x, y = int(v['x'] * W / 100), int(v['y'] * H / 100)
        cv2.circle(chk, (x, y), 5, (160, 0, 255), -1)
        cv2.putText(chk, v['nome'][:22], (x + 6, y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1)
cv2.imwrite(os.path.join(BASE_DIR, '_check', 'paldea-final.png'), chk)
# resto do buraco (fora de qualquer recorte): inpainting para não ficar bloco chapado
m = cv2.dilate((hole & ~cover).astype(np.uint8) * 255, np.ones((5, 5), np.uint8))
cv2.imwrite(os.path.join(DATA, index['paldea-2']['arquivo']), cv2.inpaint(big, m, 25, cv2.INPAINT_TELEA),
            [cv2.IMWRITE_WEBP_QUALITY, 80])
