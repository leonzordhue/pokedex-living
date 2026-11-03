"""Gera data/avail.json e data/areas.json para TODOS os jogos de scripts/games.json.

Status por espécie (até o teto nacional do jogo):
  w             selvagem / presente / troca com NPC no próprio jogo
  e:<id>        evoluindo a espécie <id>, obtível no jogo
  o:<id>        chocando ovo de <id> (só jogos com Day Care/Nursery/Picnic; não vale para o grupo "no-eggs")
  v:<jogos>     sai em outra versão do mesmo grupo de troca (trocar)
  t:<jogos>     não sai aqui, mas dá para transferir dos jogos listados (Time Capsule, Pal Park, Bank, HOME...)
  m             mítico: só evento
  x             não existe neste jogo
Fontes: CSVs da PokéAPI (scripts/_csv) para src=api; data/enc/<jogo>.json (Bulbapedia) para src=bp.
"""
import csv, json, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(BASE_DIR, '_csv')
DATA = os.path.join(BASE_DIR, '..', 'data')

with open(os.path.join(BASE_DIR, 'games.json'), encoding='utf-8') as f:
    GAMES = json.load(f)

# Grupos de troca direta (mesma geração e compatíveis entre si).
TROCA = [['red', 'blue', 'yellow'], ['gold', 'silver', 'crystal'],
         ['ruby', 'sapphire', 'emerald', 'firered', 'leafgreen'],
         ['diamond', 'pearl', 'platinum', 'heartgold', 'soulsilver'],
         ['black', 'white', 'black-2', 'white-2'], ['x', 'y', 'omega-ruby', 'alpha-sapphire'],
         ['sun', 'moon', 'ultra-sun', 'ultra-moon'], ['lets-go-pikachu', 'lets-go-eevee'],
         ['sword', 'shield'], ['brilliant-diamond', 'shining-pearl'], ['legends-arceus'],
         ['scarlet', 'violet'], ['legends-za']]
GRUPO = {g: grp for grp in TROCA for g in grp}
# De quais jogos dá para TRAZER Pokémon para cada jogo (transferência de mão única ou HOME).
HOME = ['sword', 'shield', 'brilliant-diamond', 'shining-pearl', 'legends-arceus', 'scarlet', 'violet', 'legends-za']
def origem(g):
    gen = GAMES[g]['gen']
    if g in HOME:  # HOME recebe de outros jogos HOME, Let's Go e do Pokémon Bank (gen 6 e 7)
        return [h for h in HOME if h not in GRUPO[g]] + [k for k, v in GAMES.items() if v['gen'] in (6, 7)]
    if g.startswith('lets-go'):
        return []                                   # só aceita Pokémon GO
    if gen == 2:
        return ['red', 'blue', 'yellow']            # Time Capsule
    if gen == 3:
        return []
    if gen == 7:                                    # Bank (gen 6) + Transporter (Virtual Console gen 1/2)
        return [k for k, v in GAMES.items() if v['gen'] in (1, 2, 6)]
    return [k for k, v in GAMES.items() if v['gen'] == gen - 1 and not k.startswith('lets-go')]  # Pal Park, Poké Transfer, Bank

def rows(name):
    with open(os.path.join(CSV, name + '.csv'), encoding='utf-8') as f:
        return list(csv.DictReader(f))

ver_id = {r['identifier']: int(r['id']) for r in rows('versions')}
sp = {int(r['id']): r for r in rows('pokemon_species')}
poke2sp = {int(r['id']): int(r['species_id']) for r in rows('pokemon')}
parent = {s: int(r['evolves_from_species_id']) for s, r in sp.items() if r['evolves_from_species_id']}
children = {}
for c, p in parent.items():
    children.setdefault(p, []).append(c)
no_eggs = {int(r['species_id']) for r in rows('pokemon_egg_groups') if r['egg_group_id'] == '15'}

enc_rows = rows('encounters')
enc = {}
for r in enc_rows:
    enc.setdefault(int(r['version_id']), set()).add(poke2sp[int(r['pokemon_id'])])

def bp_file(g):
    p = os.path.join(DATA, 'enc', g + '.json')
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as f:
        return json.load(f)

def wild(g):
    G = GAMES[g]
    if G['src'] == 'bp':
        d = bp_file(g)
        return {int(k) for k in d['enc']} if d else set()
    s = set()
    for v in G['ver']:
        s |= enc.get(ver_id.get(v, -1), set())
    return s

def closure(g):
    G = GAMES[g]; nat = G['nat']
    how = {s: 'w' for s in wild(g) if s <= nat}
    changed = True
    while changed:
        changed = False
        for s in list(how):
            for c in children.get(s, []):
                if c <= nat and c not in how:
                    how[c] = f'e:{s}'; changed = True
            p = parent.get(s)
            if G['ovo'] and p and p <= nat and p not in how and s not in no_eggs:
                how[p] = f'o:{s}'; changed = True
    return how

CL = {g: closure(g) for g in GAMES}
# Jogos da era HOME só aceitam as espécies que existem no próprio jogo: aproximado pela união das dex regionais.
dex_id = {r['identifier']: r['id'] for r in rows('pokedexes')}
in_dex = {}
for r in rows('pokemon_dex_numbers'):
    in_dex.setdefault(r['pokedex_id'], set()).add(int(r['species_id']))
EXISTE = {g: set().union(*(in_dex.get(dex_id.get(d, ''), set()) for d in GAMES[g]['dex'])) | set(CL[g])
          for g in GAMES if g in HOME and g not in ('brilliant-diamond', 'shining-pearl')}
out = {}
for g, G in GAMES.items():
    res = {}
    for s in range(1, G['nat'] + 1):
        if s in CL[g]:
            res[s] = CL[g][s]; continue
        sib = [GAMES[o]['nome'] for o in GRUPO[g] if o != g and s in CL[o]]
        if sib:
            res[s] = 'v:' + ', '.join(sib); continue
        tr = [GAMES[o]['nome'] for o in origem(g) if s in CL[o]]
        if g in EXISTE and s not in EXISTE[g]:
            tr = []
        if tr:
            res[s] = 't:' + ', '.join(tr)
        elif sp[s]['is_mythical'] == '1':
            res[s] = 'm'
        else:
            res[s] = 'x'
    out[g] = res
    c = {}
    for v in res.values():
        c[v[0]] = c.get(v[0], 0) + 1
    print(f'{g:18} {c}')

with open(os.path.join(DATA, 'avail.json'), 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
with open(os.path.join(DATA, 'games.json'), 'w', encoding='utf-8') as f:
    json.dump(GAMES, f, ensure_ascii=False, separators=(',', ':'))

# área (slug PokéAPI) -> local, e locais com encontro em cada jogo
loc_slug = {int(r['id']): r['identifier'] for r in rows('locations')}
area_slug, area_loc = {}, {}
for r in rows('location_areas'):
    l = loc_slug[int(r['location_id'])]
    a = f"{l}-{r['identifier']}" if r['identifier'] else f'{l}-area'
    area_slug[int(r['id'])] = a
    area_loc[a] = l
vid2game = {}
for g, G in GAMES.items():
    for v in G['ver']:
        if v in ver_id:
            vid2game.setdefault(ver_id[v], []).append(g)
game_locs = {g: set() for g in GAMES}
for r in enc_rows:
    for g in vid2game.get(int(r['version_id']), []):
        if GAMES[g]['src'] == 'api':
            game_locs[g].add(area_loc[area_slug[int(r['location_area_id'])]])
for g, G in GAMES.items():
    if G['src'] == 'bp':
        d = bp_file(g)
        game_locs[g] = set(d['locais']) if d else set()
with open(os.path.join(DATA, 'areas.json'), 'w', encoding='utf-8') as f:
    json.dump({'area': area_loc, 'jogo': {g: sorted(s) for g, s in game_locs.items()}}, f, separators=(',', ':'))

# auto-teste
assert out['black'][642].startswith('v:')  # Thundurus: exclusivo de White
assert out['y'][716].startswith('v:') and 'X' in out['y'][716]
assert out['crystal'][1].startswith('t:') or out['crystal'][1] in ('w',) or out['crystal'][1].startswith('v:')
assert out['red'][151] == 'm'
print('ok')
