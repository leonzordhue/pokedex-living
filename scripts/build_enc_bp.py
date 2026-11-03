"""Extrai da Bulbapedia os encontros dos jogos que a PokéAPI não cobre e grava data/enc/<versao>.json
no formato de scripts/ENC_SCHEMA.md.

Templates (parâmetros lidos do código-fonte dos templates em 03/11/2026):
  Catch/entryoras    1=nº 2=nome 3=OR 4=AS 5=método 6=nível 7=chance
  Catch/entrybdsp    1=nº 2=nome 3=BD 4=SP 5=método 6=nível all= ou 7/8/9=manhã/dia/noite
  Catch/entry9       1=nº 2=nome 3=S 4=V land/watersurface/underwater/overland/sky 5=nível all= ou morning/day/evening/night
  Catch/entry9/special 1=nº 2=nome 3=S 4=V 5=método(Fixed/Gift/Trade/Tera) 6=nível 7=reaparece
  Catch/entryla      1=nº 2=nome 3=nív.mín 4=nív.máx 5-8=manhã/dia/tarde/noite 9=todo clima ou clear/sun/... alpha=yes
  Catch/entryza      1=nº 2=nome 3=nível 4=dia e noite ou 5/6=dia/noite 7=todo clima ou 8-12=clear/sun/cloudy/rain/fog alpha=yes
Uso: python -I build_enc_bp.py   (cache em scripts/_cache/bp_enc)
"""
import json, os, re, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE_DIR, '_cache', 'bp_enc')
OUT = os.path.join(BASE_DIR, '..', 'data', 'enc')
API = 'https://bulbapedia.bulbagarden.net/w/api.php?format=json&'
UA = {'User-Agent': 'pokedex-living-build/1.0 (personal fan project)'}
os.makedirs(CACHE, exist_ok=True); os.makedirs(OUT, exist_ok=True)

def api(q):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(API + q, headers=UA), timeout=60) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception:
            time.sleep(2 + i * 3)
    raise RuntimeError('falhou: ' + q)

def wikitext(title):
    fn = os.path.join(CACHE, re.sub(r'[^\w.-]+', '_', title) + '.json')
    if os.path.exists(fn):
        with open(fn, encoding='utf-8') as f:
            return json.load(f)
    j = api('action=parse&prop=wikitext|categories&redirects=1&page=' + urllib.parse.quote(title))
    d = {'title': j['parse']['title'], 'w': j['parse']['wikitext']['*'],
         'cats': [c['*'] for c in j['parse'].get('categories', [])]} if 'parse' in j else {'title': title, 'w': '', 'cats': []}
    with open(fn, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False)
    return d

def embedded(tpl):
    out, cont = [], ''
    while True:
        j = api('action=query&list=embeddedin&eilimit=500&einamespace=0&eititle=' + urllib.parse.quote('Template:Catch/' + tpl) + cont)
        out += [p['title'] for p in j['query']['embeddedin']]
        if 'continue' not in j:
            return out
        cont = '&eicontinue=' + urllib.parse.quote(j['continue']['eicontinue'])

# ---------- parser de chamadas de template (com aninhamento) ----------
def calls(text):
    """Gera (posição, nome, posicionais, nomeados) para cada {{...}} de nível superior relevante."""
    i, n = 0, len(text)
    while True:
        i = text.find('{{', i)
        if i < 0:
            return
        depth, j = 0, i
        while j < n:
            if text.startswith('{{', j):
                depth += 1; j += 2
            elif text.startswith('}}', j):
                depth -= 1; j += 2
                if depth == 0:
                    break
            else:
                j += 1
        body = text[i + 2:j - 2]
        parts, buf, d, k = [], '', 0, 0
        while k < len(body):
            if body.startswith('{{', k) or body.startswith('[[', k):
                d += 1; buf += body[k:k + 2]; k += 2; continue
            if body.startswith('}}', k) or body.startswith(']]', k):
                d -= 1; buf += body[k:k + 2]; k += 2; continue
            if body[k] == '|' and d == 0:
                parts.append(buf); buf = ''
            else:
                buf += body[k]
            k += 1
        parts.append(buf)
        name = parts[0].strip()
        pos, named = [], {}
        for p in parts[1:]:
            m = re.match(r'^\s*([A-Za-z][\w ]*?)\s*=(.*)$', p, re.S)
            if m:
                named[m.group(1).strip().lower()] = m.group(2).strip()
            else:
                pos.append(p.strip())
        yield i, name, pos, named
        i = j

def clean(s):
    s = re.sub(r'\{\{(?:tt|sup/\d|DL)\|([^|}]*)[^}]*\}\}', r'\1', s or '')
    s = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]*)\]\]', r'\1', s)
    s = re.sub(r'\{\{[^{}]*\}\}', '', s)
    s = re.sub(r'<[^>]+>', ' ', s).replace('&nbsp;', ' ').replace("'''", '').replace("''", '')
    return re.sub(r'\s+', ' ', s).strip()

FORMA = {'alolan form': 'alola', 'galarian form': 'galar', 'hisuian form': 'hisui', 'paldean form': 'paldea'}
def form_slug(f):
    f = clean(f).lower()
    return FORMA.get(f, re.sub(r'[^a-z0-9]+', '-', f.replace(' form', '')).strip('-'))

MET = {  # método da Bulbapedia -> (chave, rótulo PT)
    'grass': ('walk', 'Grama'), 'tall grass': ('walk', 'Grama alta'), 'long grass': ('walk', 'Grama alta'), 'cave': ('walk', 'Caverna'),
    'surf': ('surf', 'Surfando'), 'surfing': ('surf', 'Surfando'), 'fish old': ('old-rod', 'Pescar com Old Rod'),
    'fish good': ('good-rod', 'Pescar com Good Rod'), 'fish super': ('super-rod', 'Pescar com Super Rod'),
    'old rod': ('old-rod', 'Pescar com Old Rod'), 'good rod': ('good-rod', 'Pescar com Good Rod'), 'super rod': ('super-rod', 'Pescar com Super Rod'),
    'fishing': ('fishing', 'Pescando'), 'rock smash': ('rock-smash', 'Quebrando pedra (Rock Smash)'), 'sand': ('walk', 'Areia'),
    'dark': ('dark-grass', 'Grama escura'), 'rustling': ('rustling', 'Grama mexendo'), 'dust': ('cave-spots', 'Poeira na caverna'),
    'shadow': ('shadow', 'Sombra voando'), 'rippling': ('surf-spots', 'Água ondulando'), 'rough': ('rough-terrain', 'Terreno acidentado'),
    'horde': ('horde', 'Horda (5 de uma vez)'), 'gift': ('gift', 'Presente de NPC'), 'egg': ('gift-egg', 'Ovo de presente'),
    'only one': ('static', 'Encontro único'), 'fixed': ('static', 'Encontro fixo'), 'trade': ('npc-trade', 'Troca com NPC'),
    'swarm': ('swarm', 'Surto (swarm)'), 'mass outbreak': ('mass-outbreak', 'Surto (mass outbreak)'),
    'poké radar': ('poke-radar', 'Poké Radar'), 'poke radar': ('poke-radar', 'Poké Radar'), 'honey tree': ('honey-tree', 'Árvore com Honey'),
    'honey': ('honey-tree', 'Árvore com Honey'), 'great marsh': ('walk', 'Great Marsh'), 'dexnav': ('dexnav', 'DexNav'),
    'tera': ('tera-raid', 'Pokémon Tera (fixo)'), 'yellow flowers': ('yellow-flowers', 'Flores amarelas'),
    'headbutt': ('headbutt', 'Cabeçada em árvore (Headbutt)'), 'trophy garden': ('walk', 'Trophy Garden (sorteio diário)'),
    'mirage': ('static', 'Mirage spot'), 'soaring': ('soaring', 'Voando (Soaring)'), 'sky': ('overworld-flying', 'No céu'),
    'radio': ('walk', 'Grama (rádio)'), 'backlot': ('walk', 'Trophy Garden (sorteio diário do Mr. Backlot)'), 'dual-slot': ('walk', 'Grama (cartucho no slot GBA)'), 'tree': ('tree-shake', 'Árvore'),
}
def metodo(raw):
    r = clean(raw)
    k = r.lower()
    for key, v in MET.items():
        if k == key or k.startswith(key):
            return v[0], v[1], ('' if k == key else r)
    return re.sub(r'[^a-z0-9]+', '-', k).strip('-') or 'walk', r or 'Encontro', ''

AMB = [('land', 'walk', 'Andando (terra)'), ('watersurface', 'surf', 'Na superfície da água'),
       ('underwater', 'underwater', 'Debaixo d\'água'), ('overland', 'overworld', 'No mapa (perto do chão)'), ('sky', 'overworld-flying', 'Voando no céu')]
HORAS = [('morning', 'Manhã'), ('day', 'Dia'), ('evening', 'Tarde'), ('night', 'Noite')]
CLIMA_LA = [('clear', 'Céu limpo'), ('sun', 'Sol'), ('cloudy', 'Nublado'), ('rain', 'Chuva'), ('thunderstorm', 'Tempestade'),
            ('snow', 'Neve'), ('blizzard', 'Nevasca'), ('fog', 'Neblina')]
CLIMA_ZA = ['Céu limpo', 'Sol', 'Nublado', 'Chuva', 'Neblina']
OK = lambda v: bool(v) and clean(v) not in ('', '✘', '0', '0%', 'no', 'No', '-', '—')

CTX_PT = {'first partner pokémon': 'Inicial', 'gift pokémon': 'Presente', 'gift': 'Presente', 'horde encounter': 'Horda',
          'base encounters': '', 'special encounters': '', 'trade': 'Troca', 'in-game trade': 'Troca',
          'swarm': 'Surto', 'poké radar': 'Poké Radar', 'great marsh': 'Great Marsh', 'trophy garden': 'Trophy Garden',
          'honey tree': 'Árvore com Honey', 'fossil': 'Fóssil', 'fossils': 'Fóssil', 'legendary pokémon': 'Lendário',
          'roaming pokémon': 'Errante', 'egg': 'Ovo', 'static encounter': 'Encontro fixo', 'static encounters': 'Encontro fixo',
          'visible encounters': 'Visível no mapa', 'hidden encounters': 'Escondido', 'dexnav': 'DexNav',
          'after national dex': 'Depois da Dex Nacional', 'after obtaining national dex': 'Depois da Dex Nacional',
          'post-game': 'Pós-jogo', 'special': 'Especial', 'first visit': 'Primeira visita', 'after hall of fame': 'Depois do Hall of Fame', 'mass outbreak': 'Surto'}
def ctx_pt(c):
    """Rótulo de seção da tabela em português; descarta cores/biomas de uma palavra (land, snow, south...)."""
    if not c or re.fullmatch(r'[a-z]+', c) or c.lower() in ('pokémon', 'wild pokémon'):
        return ''
    return CTX_PT.get(c.lower(), c)

UMA_VEZ = ('one', 'only one', 'only once', 'once')
def chance(v):
    v = clean(v).rstrip('%')
    return 'Uma vez' if v.lower() in UMA_VEZ else ('' if v in ('✔', '✘') else v)

def num(p):
    m = re.search(r'\d+', p or '')
    return str(int(m.group())) if m else None

def parse_page(page, tpl):
    """Devolve lista de (versao, registro) da página para o template dado."""
    w, title = page['w'], page['title']
    heads = [(m.start(), clean(m.group(2))) for m in re.finditer(r'^(=+)\s*(.*?)\s*\1\s*$', w, re.M)]
    out, ctx = [], ''
    for pos, name, P, N in calls(w):
        low = name.lower().replace('_', ' ')
        if low.startswith('catch/div'):
            lab = [clean(x) for x in P if len(clean(x)) > 2]
            ctx = lab[-1] if lab else ctx
            continue
        if low.startswith('catch/header'):
            ctx = ''
            continue
        if low != 'catch/' + tpl:
            continue
        sec = ''
        for hp, ht in heads:
            if hp < pos:
                sec = ht
        n = num(P[0] if P else '')
        if not n:
            continue
        g = lambda i: P[i] if len(P) > i else ''
        base = {'_sid': n, 'loc': 'bp:' + title, 'form': form_slug(N['form']) if N.get('form') else '', 'cs': [], 'nota': ''}
        if N.get('alpha') == 'yes':
            base['cs'].append('Alpha')
        if N.get('note'):
            base['nota'] = clean(N['note'])[:160]
        c = ctx_pt(ctx)
        if c:
            base['cs'].append(c)
        recs = []
        if tpl in ('entryoras', 'entrybdsp'):
            vers = (['omega-ruby', 'alpha-sapphire'] if tpl == 'entryoras' else ['brilliant-diamond', 'shining-pearl'])
            m, mpt, extra = metodo(g(4))
            r = dict(base, m=m, mpt=mpt, lv=clean(g(5)))
            if extra and extra.lower() != mpt.lower():
                r['cs'] = r['cs'] + [extra]
            if tpl == 'entryoras':
                r['ch'] = clean(g(6)).rstrip('%')
            elif N.get('all'):
                r['ch'] = clean(N['all']).rstrip('%')
            else:
                rates = [clean(g(i)) for i in (6, 7, 8)]
                r['ch'] = '/'.join(x.rstrip('%') for x in rates if x)
                r['cs'] = r['cs'] + [h for h, v in zip(['Manhã', 'Dia', 'Noite'], rates) if OK(v)] if not all(OK(v) for v in rates) else r['cs']
            for v, flag in zip(vers, (g(2), g(3))):
                if flag.lower() == 'yes':
                    recs.append((v, r))
        elif tpl == 'entry9':
            amb = [a for a in AMB if (N.get(a[0], '').lower() == 'yes')]
            m, mpt = (amb[0][1], ' / '.join(a[2] for a in amb)) if amb else ('walk', 'Selvagem')
            r = dict(base, m=m, mpt=mpt, lv=clean(g(4)))
            if N.get('all'):
                r['ch'] = clean(N['all']).rstrip('%')
            else:
                hs = [(lab, N.get(k, g(5))) for k, lab in HORAS]
                if not all(OK(v) for _, v in hs):
                    r['cs'] = r['cs'] + [lab for lab, v in hs if OK(v)]
                r['ch'] = '/'.join(sorted({clean(v).rstrip('%') for _, v in hs if OK(v)}))
            if N.get('group'):
                r['nota'] = (r['nota'] + ' ' if r['nota'] else '') + f"Aparece em grupo ({clean(N['group'])}%)."
            for v, flag in zip(['scarlet', 'violet'], (g(2), g(3))):
                if flag.lower() == 'yes':
                    recs.append((v, r))
        elif tpl == 'entry9/special':
            raw = g(4) or 'Fixed'
            m, mpt, extra = metodo(raw)
            if raw.lower() == 'tera' and N.get('teratype'):
                mpt = f"Pokémon Tera fixo (tipo {clean(N['teratype'])})"
            if raw.lower() == 'trade' and N.get('tradename'):
                mpt = f"Troca com NPC (entregue {clean(N['tradename'])})"
            r = dict(base, m=m, mpt=mpt, lv=clean(g(5)), ch='Uma vez' if 'no' in clean(g(6)).lower() else clean(g(6)))
            for v, flag in zip(['scarlet', 'violet'], (g(2), g(3))):
                if flag.lower() == 'yes':
                    recs.append((v, r))
        elif tpl == 'entryla':
            alpha_lv = clean(g(3))
            r = dict(base, m='walk', mpt='Selvagem' + (' (perto, ‡)' if N.get('nearby') == 'yes' else ''), lv=clean(g(2)))
            if alpha_lv and alpha_lv not in ('—', '-', '✘'):
                r['cs'] = r['cs'] + ['Alpha: Nv. ' + alpha_lv]
            if N.get('all'):
                r['ch'] = clean(N['all']).rstrip('%')
            else:
                hs = [(lab, N.get(k, g(4 + i))) for i, (k, lab) in enumerate(HORAS)]
                if not all(OK(v) for _, v in hs):
                    r['cs'] = r['cs'] + [lab for lab, v in hs if OK(v)]
            if not clean(g(8)):
                cl = [(lab, N.get(k, '')) for k, lab in CLIMA_LA]
                if any(OK(v) for _, v in cl) and not all(OK(v) for _, v in cl if v.lower() != 'na'):
                    r['cs'] = r['cs'] + [lab for lab, v in cl if OK(v) and v.lower() != 'na']
            if sec and sec.lower() not in ('pokémon', 'wild pokémon'):
                r['cs'] = r['cs'] + [sec]
            recs.append(('legends-arceus', r))
        elif tpl == 'entryza':
            r = dict(base, m='wild-zone', mpt='Selvagem (Wild Zone)' if 'Wild Zone' in title else 'Selvagem', lv=clean(g(2)))
            if not clean(g(3)):
                hs = [('Dia', N.get('day', g(4))), ('Noite', N.get('night', g(5)))]
                if not all(OK(v) for _, v in hs):
                    r['cs'] = r['cs'] + [lab for lab, v in hs if OK(v)]
            if not clean(g(6)):
                cl = [(lab, g(7 + i)) for i, lab in enumerate(CLIMA_ZA)]
                if any(OK(v) for _, v in cl) and not all(OK(v) for _, v in cl):
                    r['cs'] = r['cs'] + [lab for lab, v in cl if OK(v)]
            if sec and sec.lower() not in ('pokémon',):
                r['cs'] = r['cs'] + [sec]
            recs.append(('legends-za', r))
        out += recs
    return out

TPLS = ['entryoras', 'entrybdsp', 'entry9', 'entry9/special', 'entryla', 'entryza']
DLC_CAT = {'Kitakami_locations': 'teal-mask', 'Blueberry_Academy_locations': 'indigo-disk',
           'Hyperspace_Lumiose_locations': 'mega-dimension'}
# Categoria de locais de cada jogo -> versões; e nomes que aparecem nos títulos de seção / legendas.
GAME_CAT = {'Omega_Ruby_and_Alpha_Sapphire_locations': ['omega-ruby', 'alpha-sapphire'],
            'Brilliant_Diamond_and_Shining_Pearl_locations': ['brilliant-diamond', 'shining-pearl'],
            'Legends:_Arceus_locations': ['legends-arceus'], 'Scarlet_and_Violet_locations': ['scarlet', 'violet'],
            'Kitakami_locations': ['scarlet', 'violet'], 'Blueberry_Academy_locations': ['scarlet', 'violet'],
            'Legends:_Z-A_locations': ['legends-za'], 'Hyperspace_Lumiose_locations': ['legends-za']}
SEC_GAME = [('omega ruby', ['omega-ruby', 'alpha-sapphire']), ('alpha sapphire', ['omega-ruby', 'alpha-sapphire']),
            ('brilliant diamond', ['brilliant-diamond', 'shining-pearl']), ('shining pearl', ['brilliant-diamond', 'shining-pearl']),
            ('legends: arceus', ['legends-arceus']), ('scarlet', ['scarlet', 'violet']), ('violet', ['scarlet', 'violet']),
            ('teal mask', ['scarlet', 'violet']), ('indigo disk', ['scarlet', 'violet']), ('z-a', ['legends-za']),
            ('mega dimension', ['legends-za'])]
OTHER_GAMES = ('red', 'blue', 'yellow', 'gold', 'silver', 'crystal', 'ruby and sapphire', 'emerald', 'firered', 'leafgreen',
               'diamond and pearl', 'platinum', 'heartgold', 'soulsilver', 'black', 'white', 'x and y', 'sun', 'moon',
               "let's go", 'sword', 'shield', 'generation')
GAME_HEADS = {'omega ruby and alpha sapphire', 'brilliant diamond and shining pearl', 'legends: arceus', 'scarlet and violet',
              'the teal mask', 'the indigo disk', 'legends: z-a', 'mega dimension', 'ruby and sapphire', 'emerald',
              'diamond and pearl', 'platinum', 'x and y', 'sun and moon', 'ultra sun and ultra moon', 'sword and shield'}
VGEN = {'omega-ruby': 6, 'alpha-sapphire': 6, 'brilliant-diamond': 8, 'shining-pearl': 8, 'legends-arceus': 8,
        'scarlet': 9, 'violet': 9, 'legends-za': 9}
VER_WORD = {'omega ruby': 'omega-ruby', 'alpha sapphire': 'alpha-sapphire', 'brilliant diamond': 'brilliant-diamond',
            'shining pearl': 'shining-pearl', 'scarlet': 'scarlet', 'violet': 'violet'}

def cat_members(cat):
    out, cont = [], ''
    while True:
        j = api('action=query&list=categorymembers&cmnamespace=0&cmlimit=500&cmtitle=' + urllib.parse.quote('Category:' + cat) + cont)
        out += [p['title'] for p in j['query']['categorymembers']]
        if 'continue' not in j:
            return out
        cont = '&cmcontinue=' + urllib.parse.quote(j['continue']['cmcontinue'])

def specials(page):
    """Blocos {{Pokémon|ndex=..|pokemon=..|level=..}} (lendários, presentes, fixos) por seção de jogo."""
    w, title = page['w'], page['title']
    page_games = sorted({v for c in page['cats'] for k, vs in GAME_CAT.items() if c == k for v in vs})
    heads = [(m.start(), clean(m.group(2)).lower()) for m in re.finditer(r'^(=+)\s*(.*?)\s*\1\s*$', w, re.M)]
    h2 = [(m.start(), clean(m.group(2)).lower()) for m in re.finditer(r'^(={2,3})\s*([^=].*?)\s*\1\s*$', w, re.M)]
    out = []
    for pos, name, P, N in calls(w):
        if name.strip().lower() not in ('pokémon', 'pokemon') or not N.get('ndex'):
            continue
        # só seções de Pokémon/encontros (fora de "Trainers", "Items"...) e fora dos times de treinador ({{Party}})
        top = next((h for hp, h in reversed(h2) if hp < pos), '')
        if not re.search(r'pokémon|pokemon|encounter', top) or 'trainer' in top:
            continue
        if w.rfind('{{Party', 0, pos) > w.rfind('{{Party/end', 0, pos):
            continue
        hs = [h for hp, h in heads if hp < pos]
        if hs and re.search(r'mandatory|cannot be caught|uncatchable', hs[-1]):
            continue  # batalhas obrigatórias que não dá para capturar
        game = None
        for h in reversed(hs):
            # só títulos que são nome de jogo ("Pokémon Omega Ruby...", "Scarlet and Violet", "Generation VI");
            # "Crystal tree" ou "Scarlet Bog" são lugares, não jogos
            if not (h.startswith('pokémon ') or h.startswith('generation ') or h in GAME_HEADS):
                continue
            hit = [vs for key, vs in SEC_GAME if key in h]
            if hit:
                game = hit[0]; break
            gm = re.search(r'generation ([ivx]+)\b', h)
            if gm:  # "Generation VI" etc.: os jogos desta página daquela geração
                gen = {'vi': 6, 'viii': 8, 'ix': 9}.get(gm.group(1), 0)
                game = [v for v in page_games if VGEN.get(v) == gen]; break
            if any(o in h for o in OTHER_GAMES):
                game = []; break
        if game is None:
            game = page_games if len(set(GAME_CAT.get(c, [''])[0] for c in page['cats'] if c in GAME_CAT)) == 1 else []
        if not game:
            continue
        cap = clean(N.get('caption', ''))
        only = [v for word, v in VER_WORD.items() if word in cap.lower()]
        vers = [v for v in game if not only or v in only]
        n = num(N['ndex'])
        if not n:
            continue
        r = {'_sid': n, 'loc': 'bp:' + title, 'form': form_slug(N['form']) if N.get('form') else '',
             'm': 'static', 'mpt': 'Encontro especial (fixo/presente)', 'lv': clean(N.get('level', '')), 'ch': 'Uma vez',
             'cs': [], 'nota': cap[:160] if cap and cap.lower() not in VER_WORD else ''}
        sec = next((h for h in reversed(hs) if not any(k in h for k, _ in SEC_GAME) and not any(o in h for o in OTHER_GAMES)), '')
        sec = ctx_pt(sec) if sec not in ('special encounters', 'pokémon') else ''
        if sec:
            r['cs'].append(sec[0].upper() + sec[1:])
        out += [(v, r) for v in vers]
    return out

def main():
    pages = {t: embedded(t) for t in TPLS}
    cat_pages = sorted({p for c in GAME_CAT for p in cat_members(c)})
    titles = sorted({p for v in pages.values() for p in v} | set(cat_pages))
    with ThreadPoolExecutor(4) as ex:
        data = dict(zip(titles, ex.map(wikitext, titles)))
    res = {}
    for t, plist in pages.items():
        for p in plist:
            for v, r in parse_page(data[p], t):
                res.setdefault(v, []).append(r)
    for p in titles:
        for v, r in specials(data[p]):
            res.setdefault(v, []).append(r)
    stamp = time.strftime('%Y-%m-%d')
    by_title = {d['title']: d for d in data.values()}
    final = {}
    for v, rows in res.items():
        locais, enc, seen = {}, {}, set()
        for r in rows:
            key = json.dumps(r, sort_keys=True, ensure_ascii=False)
            if key in seen:
                continue
            seen.add(key)
            rec = {k: val for k, val in r.items() if k != '_sid'}
            rec['ch'] = chance(rec.get('ch', ''))
            rec['cs'] = [c for c in dict.fromkeys(rec['cs']) if c]
            enc.setdefault(r['_sid'], []).append(rec)
            loc = r['loc']
            if loc not in locais:
                cats = by_title.get(loc[3:], {}).get('cats', [])
                dlc = next((d for c in cats for k, d in DLC_CAT.items() if k.replace(' ', '_') in c), '')
                locais[loc] = {'nome': loc[3:], 'regiao': '', 'dlc': dlc}
        final[v] = {'versao': v, 'fonte': f'Bulbapedia (CC BY-NC-SA), extraído em {stamp}', 'locais': locais, 'enc': enc}
        with open(os.path.join(OUT, v + '.json'), 'w', encoding='utf-8') as f:
            json.dump(final[v], f, ensure_ascii=False, separators=(',', ':'))
        print(f'{v:18} {len(enc):4} espécies  {len(locais):4} locais  {len(seen):5} linhas')
    return final

def selftest(F):
    sp = lambda v, n: str(n) in F[v]['enc']
    assert sp('omega-ruby', 383) and sp('alpha-sapphire', 382), 'Groudon/Kyogre'
    assert sp('brilliant-diamond', 396) and sp('brilliant-diamond', 399), 'Starly/Bidoof'
    assert sp('scarlet', 187) and sp('scarlet', 915), 'Hoppip/Lechonk'
    assert sp('legends-arceus', 399) and sp('legends-arceus', 396), 'Bidoof/Starly'
    assert any(r['form'] == 'hisui' for r in F['legends-arceus']['enc'].get('58', [])), 'Growlithe de Hisui'
    assert sp('legends-za', 13) and sp('legends-za', 16), 'Weedle/Pidgey'
    print('auto-teste ok')

if __name__ == '__main__':
    selftest(main())
