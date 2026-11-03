"""Correções manuais dos pinos de baixa confiança de data/locs.json (rodar depois de build_maps.py).

x/y em % do mapa; None tira o pino (o local continua listado no app, sem ponto no mapa).
Conferido nas imagens de scripts/_check/ em 03/11/2026.
"""
import json, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(BASE_DIR, '..', 'data', 'locs.json')

FIX = {
    # Unova: o destaque pegou a caixa de texto; posições pela geografia de Black/White.
    'unova-victory-road': (65.0, 13.0), 'trial-chamber': (65.0, 13.0), 'unova-route-10': (60.0, 18.0),
    'challengers-cave': (49.0, 24.0), 'cold-storage': (31.0, 56.0),
    # Sem posição confiável no mapa-base.
    'galar-rock-peak-ruins': None, 'galar-iron-ruins': None, 'galar-iceberg-ruins': None,
    'terra-cave': None, 'marine-cave': None, 'distortion-world': None,
    'birth-island': None, 'navel-rock': None, 'chargestone-cavern': None, 'hoenn-altering-cave': None, 'poke-pelago': None,
}

with open(P, encoding='utf-8') as f:
    locs = json.load(f)
n = 0
for k, v in FIX.items():
    if k not in locs:
        continue
    locs[k]['x'], locs[k]['y'] = (v if v else (None, None))
    locs[k]['confianca'] = 'manual' if v else 'sem'
    n += 1
# nomes das abas de mapa que o agrupamento automático numerou
IDX = os.path.join(BASE_DIR, '..', 'data', 'maps', 'index.json')
with open(IDX, encoding='utf-8') as f:
    index = json.load(f)
for k, t in {'kalos-2': 'Lumiose City', 'unova-2': 'Blueberry Academy (Terarium)', 'hoenn-2': 'Hoenn (ORAS)',
             'paldea-2': 'Paldea'}.items():
    if k in index:
        index[k]['titulo'] = t
with open(IDX, 'w', encoding='utf-8') as f:
    json.dump(index, f, ensure_ascii=False, indent=1)
# a chave bp:<título> aponta para o mesmo local: recopia depois das correções
for k, v in list(locs.items()):
    if not k.startswith('bp:') and v.get('bp'):
        locs['bp:' + v['bp']] = v
with open(P, 'w', encoding='utf-8') as f:
    json.dump(locs, f, ensure_ascii=False, separators=(',', ':'))
print('corrigidos', n)
