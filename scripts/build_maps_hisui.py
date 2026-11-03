"""Mapas de Hisui (Legends: Arceus) por área. Rodar depois de build_maps.py e antes de apply_overrides.py.

Os arquivos "Hisui <Sublocal> Map.png" da Bulbapedia são prints do mapa de cada área (Obsidian Fieldlands etc.)
com o sublocal destacado. Agrupa por área (param location= do infobox), tira a mediana como mapa-base
da área e calcula o centroide da diferença de cada sublocal.
"""
import io, json, os, re, sys, time, urllib.parse, urllib.request
import numpy as np
from PIL import Image
from scipy import ndimage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE_DIR, '..', 'data')
CACHE = os.path.join(BASE_DIR, '_cache', 'hisui')
os.makedirs(CACHE, exist_ok=True)
UA = {'User-Agent': 'pokedex-living-build/1.0 (personal fan project)'}
AREAS = ['Obsidian Fieldlands', 'Crimson Mirelands', 'Cobalt Coastlands', 'Coronet Highlands', 'Alabaster Icelands']
sys.stdout.reconfigure(encoding='utf-8')

def get(url, raw=False):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                b = r.read()
                return b if raw else json.loads(b.decode('utf-8'))
        except Exception:
            time.sleep(2 + 3 * i)
    return None

def wikitext(t):
    fn = os.path.join(BASE_DIR, '_cache', 'bp_enc', re.sub(r'[^\w.-]+', '_', t) + '.json')
    if os.path.exists(fn):
        with open(fn, encoding='utf-8') as f:
            return json.load(f)['w']
    j = get('https://bulbapedia.bulbagarden.net/w/api.php?format=json&action=parse&prop=wikitext&redirects=1&page=' + urllib.parse.quote(t))
    return j['parse']['wikitext']['*'] if j and 'parse' in j else ''

def area_of(t):
    m = re.search(r'^\|\s*location\s*=\s*(.*)$', wikitext(t), re.M)
    v = m.group(1) if m else ''
    return next((a for a in AREAS if a in v), None)

def img(fileTitle):
    fn = os.path.join(CACHE, re.sub(r'[^\w.-]+', '_', fileTitle) + '.png')
    if not os.path.exists(fn):
        j = get('https://archives.bulbagarden.net/w/api.php?format=json&action=query&prop=imageinfo&iiprop=url&iiurlwidth=960&titles='
                + urllib.parse.quote(fileTitle))
        pages = (j or {}).get('query', {}).get('pages', {})
        info = next(iter(pages.values()), {}).get('imageinfo') if pages else None
        if not info:
            return None
        b = get(info[0].get('thumburl') or info[0]['url'], raw=True)
        if not b:
            return None
        Image.open(io.BytesIO(b)).convert('RGB').save(fn)
    return Image.open(fn).convert('RGB')

def main():
    with open(os.path.join(DATA, 'locs.json'), encoding='utf-8') as f:
        locs = json.load(f)
    with open(os.path.join(DATA, 'maps', 'index.json'), encoding='utf-8') as f:
        index = json.load(f)
    hisui = {k: v for k, v in locs.items() if v.get('mapa') == 'hisui' or ('legends-arceus' in v.get('versoes', []) and k.startswith('bp:'))}
    grupos = {}
    for k, v in hisui.items():
        t = v.get('bp') or k[3:]
        a = t if t in AREAS else area_of(t)
        im = None if t in AREAS else (img(f'File:Hisui {t} Map.png') or img(f'File:{t} Map.png'))
        v['_area'] = a
        for kk in ('mapa', 'x', 'y', 'bbox'):
            v.pop(kk, None)
        v['confianca'] = 'sem'
        if a and im is not None:
            grupos.setdefault(a, []).append((k, np.asarray(im.resize((960, round(960 * im.height / im.width))), dtype=np.int16)))
    index.pop('hisui', None)
    for a, membros in grupos.items():
        H = min(m.shape[0] for _, m in membros)
        arr = np.stack([m[:H] for _, m in membros])
        base = np.median(arr, axis=0).astype(np.int16)
        key = 'hisui-' + a.split()[0].lower()
        Image.fromarray(base.astype(np.uint8)).save(os.path.join(DATA, 'maps', key + '.webp'), 'WEBP', quality=80)
        index[key] = {'arquivo': f'maps/{key}.webp', 'w': 960, 'h': H, 'titulo': 'Hisui - ' + a}
        for k, m in membros:
            d = np.abs(m[:H] - base).sum(axis=2) > 90
            d = ndimage.binary_opening(d, iterations=2)
            lab, n = ndimage.label(d)
            if not n:
                continue
            sizes = ndimage.sum(d, lab, range(1, n + 1))
            big = lab == (int(np.argmax(sizes)) + 1)
            ys, xs = np.nonzero(big)
            frac = big.mean()
            v = locs[k]
            v.update(mapa=key, x=round(100 * xs.mean() / 960, 1), y=round(100 * ys.mean() / H, 1),
                     bbox=[round(100 * xs.min() / 960, 1), round(100 * ys.min() / H, 1),
                           round(100 * xs.max() / 960, 1), round(100 * ys.max() / H, 1)],
                     confianca='alta' if 0.0005 < frac < 0.15 else 'baixa')
        print(a, len(membros), 'sublocais')
    for v in locs.values():
        v.pop('_area', None)
    for k, v in list(locs.items()):  # recopia aliases bp:
        if not k.startswith('bp:') and v.get('bp'):
            locs['bp:' + v['bp']] = v
    with open(os.path.join(DATA, 'locs.json'), 'w', encoding='utf-8') as f:
        json.dump(locs, f, ensure_ascii=False, separators=(',', ':'))
    with open(os.path.join(DATA, 'maps', 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    p = os.path.join(DATA, 'maps', 'hisui.webp')
    if os.path.exists(p):
        os.remove(p)
    # checagem visual
    from PIL import ImageDraw
    for key in [k for k in index if k.startswith('hisui-')]:
        im = Image.open(os.path.join(DATA, index[key]['arquivo'])).convert('RGB')
        dr = ImageDraw.Draw(im)
        for v in locs.values():
            if v.get('mapa') == key and v.get('x') is not None:
                x, y = v['x'] * im.width / 100, v['y'] * im.height / 100
                dr.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(255, 0, 160))
                dr.text((x + 6, y - 6), v['nome'], fill=(0, 0, 0))
        im.save(os.path.join(BASE_DIR, '_check', key + '.png'))

if __name__ == '__main__':
    main()
