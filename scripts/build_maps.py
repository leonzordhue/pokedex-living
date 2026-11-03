"""Gera mapas de regiao, coordenadas dos locais e fotos para a Pokedex Living.

Fontes: CSVs da PokeAPI (locais/encontros), Bulbapedia (wikitext do infobox) e
Bulbagarden Archives (imagens "<Regiao> <Local> Map.png", com o local destacado).
Mapa-base = mediana pixel a pixel das imagens de um mesmo grupo; o destaque de
cada local e a diferenca contra essa base.

Uso: python -I build_maps.py      (reexecutavel; tudo que vem da rede fica em _cache/)
Saidas: ../data/maps/*.webp, ../data/maps/index.json, ../data/photos/*.webp,
        ../data/locs.json, _check/*.png (conferencia visual), _check/relatorio.json
"""
import csv, hashlib, io, json, math, os, re, sys, time, urllib.parse, urllib.request, warnings
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE_DIR)
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(BASE_DIR, "_cache")
CHECK = os.path.join(BASE_DIR, "_check")
for d in (CACHE, CHECK, os.path.join(CACHE, "http"), os.path.join(CACHE, "csv"),
          os.path.join(DATA, "maps"), os.path.join(DATA, "photos")):
    os.makedirs(d, exist_ok=True)
sys.stdout.reconfigure(encoding="utf-8")

UA = "pokedex-living-build/1.0 (personal fan project)"
BP = "https://bulbapedia.bulbagarden.net/w/api.php"
AR = "https://archives.bulbagarden.net/w/api.php"
CSV_URL = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/"
WORKERS = 4

# versao PokeAPI -> chave da foto (geracao 1..8 ou visual do jogo: frlg, hgss, oras, bdsp...), de scripts/games.json
with open(os.path.join(BASE_DIR, "games.json"), encoding="utf-8") as _f:
    GAMES = json.load(_f)
_k = lambda v: int(v) if str(v).isdigit() else v
VERSOES = {v: _k(g["foto"]) for g in GAMES.values() if g["src"] == "api" for v in g["ver"]}
REGIOES = {1: "Kanto", 2: "Johto", 3: "Hoenn", 4: "Sinnoh", 5: "Unova", 6: "Kalos", 7: "Alola", 8: "Galar",
           9: "Hisui", 10: "Paldea"}
GEN_REGIAO = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: "la", 10: "sv"}  # local sem encontro: foto do jogo da regiao
# jogos extraidos da Bulbapedia (data/enc/<jogo>.json): regiao padrao dos locais
BP_REGIAO = {"omega-ruby": "Hoenn", "alpha-sapphire": "Hoenn", "brilliant-diamond": "Sinnoh", "shining-pearl": "Sinnoh",
             "legends-arceus": "Hisui", "scarlet": "Paldea", "violet": "Paldea", "legends-za": "Kalos"}
# param do infobox por geracao + sufixos aceitos no nome do arquivo como 2a opcao
FOTO_PARAM = {1: "imageI", 2: "imageII", 3: "imageIII", 4: "imageIV", 5: "imageV",
              6: "imageVI", 7: "imageVII", 8: "imageVIII"}
FOTO_SUFIXO = {1: ["RBY", "RB", "Y"], 2: ["GSC", "C", "GS"], 3: ["E", "RSE", "RS"],
               4: ["Pt", "DPPt", "DP"], 5: ["BW", "B2W2"], 6: ["XY"], 7: ["USUM", "SM"],
               8: ["SwSh"], "frlg": ["FRLG"], "hgss": ["HGSS"], "b2w2": ["B2W2"], "oras": ["ORAS"],
               "sm": ["SM"], "lgpe": ["PE", "LGPE"], "bdsp": ["BDSP"], "la": ["LA", "PLA"], "sv": ["SV"],
               "za": ["ZA", "PLZA"]}


# ---------------------------------------------------------------- rede + cache
def http_get(url):
    path = os.path.join(CACHE, "http", hashlib.sha1(url.encode()).hexdigest())
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    for tent in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            tmp = path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(body)
            os.replace(tmp, path)
            return body
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 + 4 * tent)
        except Exception:
            time.sleep(2 + 4 * tent)
    print("  FALHA rede:", url[:160])
    return None


def api(host, **params):
    params.update(format="json", formatversion="2")
    body = http_get(host + "?" + urllib.parse.urlencode(params))
    return json.loads(body) if body else {}


def pmap(fn, items):
    with ThreadPoolExecutor(WORKERS) as ex:
        return list(ex.map(fn, items))


def chunks(seq, n=50):
    return [seq[i:i + n] for i in range(0, len(seq), n)]


def norm_title(t):
    t = t.replace("_", " ").strip()
    return t[:1].upper() + t[1:]


# ---------------------------------------------------------------- 1. locais
def ler_csv(nome):
    path = os.path.join(CACHE, "csv", nome + ".csv")
    if not os.path.exists(path):
        body = http_get(CSV_URL + nome + ".csv")
        with open(path, "wb") as f:
            f.write(body)
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def carregar_locais():
    vid = {int(r["id"]): r["identifier"] for r in ler_csv("versions")}
    area_loc = {int(r["id"]): int(r["location_id"]) for r in ler_csv("location_areas")}
    nomes = {int(r["location_id"]): r["name"] for r in ler_csv("location_names") if r["local_language_id"] == "9"}
    enc = defaultdict(set)  # location_id -> {versao}
    for r in ler_csv("encounters"):
        v = vid.get(int(r["version_id"]))
        if v in VERSOES:
            enc[area_loc[int(r["location_area_id"])]].add(v)
    locs = {}
    for r in ler_csv("locations"):
        lid, reg = int(r["id"]), int(r["region_id"] or 0)
        if reg in REGIOES or lid in enc:
            locs[r["identifier"]] = {"id": lid, "regiao": REGIOES.get(reg, ""), "nome": nomes.get(lid, r["identifier"]),
                                     "versoes": sorted(enc.get(lid, ()))}
    return locs


# ---------------------------------------------------------------- 2. paginas Bulbapedia
def candidatos_titulo(loc):
    nome, reg = loc["nome"], loc["regiao"]
    m = re.match(r"^(?:Sea )?Route (\d+)$", nome)
    if m and reg:
        return [f"{reg} Route {m.group(1)}"]
    c = [nome]
    if reg:
        c += [f"{nome} ({reg})", f"{reg} {nome}"]
    return c


def buscar_paginas(titulos):
    """titulo pedido -> (titulo final, wikitext) ou None."""
    out = {}
    for lote in chunks(sorted(set(titulos))):
        d = api(BP, action="query", prop="revisions", rvprop="content", rvslots="main",
                redirects="1", titles="|".join(lote)).get("query", {})
        ren = {x["from"]: x["to"] for x in d.get("normalized", [])}
        red = {x["from"]: x["to"] for x in d.get("redirects", [])}
        pags = {p["title"]: p for p in d.get("pages", [])}
        for t in lote:
            f = ren.get(t, t)
            f = red.get(f, f)
            f = f.split("#")[0]
            p = pags.get(f)
            if p and not p.get("missing") and p.get("revisions"):
                out[t] = (f, p["revisions"][0]["slots"]["main"]["content"])
            else:
                out[t] = None
    return out


def eh_disambig(txt):
    return bool(re.search(r"\{\{\s*\w*disambig", txt[:3000], re.I))


def infobox(txt):
    """Params do primeiro infobox (|chave=valor por linha)."""
    m = re.search(r"\{\{[^{}|]*infobox", txt, re.I)
    if not m:
        return {}
    bloco = txt[m.start(): m.start() + 6000]
    fim = bloco.find("\n}}")
    bloco = bloco[: fim if fim > 0 else len(bloco)]
    p = {}
    for k, v in re.findall(r"^\|\s*([\w ]+?)\s*=\s*(.*?)\s*$", bloco, re.M):
        p.setdefault(k, v)
    return p


def resolver_titulos(locs):
    cands = {s: candidatos_titulo(l) for s, l in locs.items()}
    pags = buscar_paginas([t for c in cands.values() for t in c])
    pendentes = []
    for s, l in locs.items():
        for t in cands[s]:
            r = pags.get(t)
            if r and not eh_disambig(r[1]):
                l["bp"], l["_wt"] = r
                break
        else:
            pendentes.append(s)
    # fallback: busca textual
    def busca(s):
        l = locs[s]
        q = f'{l["nome"]} {l["regiao"]}'.strip()
        d = api(BP, action="query", list="search", srsearch=q, srlimit="5", srnamespace="0")
        return s, [x["title"] for x in d.get("query", {}).get("search", [])]
    res = pmap(busca, pendentes)
    pags2 = buscar_paginas([t for _, ts in res for t in ts])
    nome_n = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
    for s, ts in res:
        l = locs[s]
        for t in ts:
            r = pags2.get(t)
            # so aceita se o nome do local aparece no titulo (evita casar com pagina errada)
            if r and not eh_disambig(r[1]) and nome_n(l["nome"]) in nome_n(r[0]):
                l["bp"], l["_wt"] = r
                l["bp_via_busca"] = True
                break


# ---------------------------------------------------------------- 3. imagens do Archives
def imageinfo(arquivos, largura):
    """'File:X.png' -> {'url','w','h'} (url = miniatura quando maior que largura)."""
    out = {}
    for lote in chunks(sorted(set(arquivos))):
        d = api(AR, action="query", prop="imageinfo", iiprop="url|size", iiurlwidth=str(largura),
                redirects="1", titles="|".join(lote)).get("query", {})
        ren = {x["from"]: x["to"] for x in d.get("normalized", [])}
        red = {x["from"]: x["to"] for x in d.get("redirects", [])}
        pags = {p["title"]: p for p in d.get("pages", [])}
        for t in lote:
            f = red.get(ren.get(t, t), ren.get(t, t))
            p = pags.get(f)
            if p and p.get("imageinfo"):
                ii = p["imageinfo"][0]
                out[t] = {"url": ii.get("thumburl") or ii["url"], "w": ii["width"], "h": ii["height"]}
    return out


def limpar_arquivo(v):
    # resolve os templates mais comuns nos nomes de foto (estacao de Unova, hora do dia)
    v = re.sub(r"<!--.*?-->", "", v).replace("{{CurrUnovaSeason}}", "Spring")
    v = re.sub(r"\{\{#(?:time|expr):[^{}]*\}\}", "", v)
    v = re.sub(r"\{\{#switch:[^{}]*\}\}", lambda m: (re.search(r"=([^|{}]*)", m.group(0)) or [None, ""])[1].strip(), v)
    v = re.sub(r"\{\{!\}\}.*|\|.*", "", v).strip()
    v = re.sub(r"^\[\[(?:File|Image):", "", v, flags=re.I).strip("[] ")
    return v if re.search(r"\.(png|jpe?g|gif|webp)$", v, re.I) else ""


def baixar_img(url):
    b = http_get(url) if url else None
    if not b:
        return None
    try:
        return Image.open(io.BytesIO(b)).convert("RGB")
    except Exception:
        return None


# ---------------------------------------------------------------- 4. mapas
def assinatura(img):
    return np.asarray(img.resize((64, 40), Image.BILINEAR).convert("L"), dtype=np.float32)


def agrupar(itens, limiar=8):
    """itens: [(slug, img)] -> lista de grupos [[slug,...]] de imagens quase identicas (mesmo enquadramento)."""
    grupos = []  # (assinatura do 1o membro, tamanho, [slugs])
    for s, img in itens:
        a = assinatura(img)
        melhor, dmin = None, 1e9
        for g in grupos:
            dist = float(np.abs(a - g[0]).mean())
            if dist < dmin:
                melhor, dmin = g, dist
        if melhor is not None and dmin < limiar:
            melhor[1].append(s)
        else:
            grupos.append((a, [s]))
    return [g[1] for g in grupos]


def mascara_destaque(arr, base, valido=None):
    d = np.abs(arr.astype(np.int16) - base.astype(np.int16)).max(axis=2)
    m = d > 60
    if valido is not None:
        m &= valido
    m[:3, :] = m[-3:, :] = False  # moldura muda entre arquivos
    m[:, :3] = m[:, -3:] = False
    h, w = m.shape
    if w >= 500:  # mapas grandes: abre a mascara para tirar ruido de compressao/antialias
        k = np.ones((3, 3), np.uint8)
        m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, k) > 0
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    if n > 2:  # mantem so as manchas relevantes (o destaque), descarta respingos
        areas = st[1:, cv2.CC_STAT_AREA]
        keep = np.nonzero(areas >= max(3, 0.15 * areas.max()))[0] + 1
        m = np.isin(lab, keep)
    return m


def medir(m):
    """Mascara -> (centro (x,y), bbox (x0,y0,x1,y1)) em pixels do quadro, e fracao da area."""
    h, w = m.shape
    n = int(m.sum())
    frac = n / (h * w)
    if n == 0:
        return None, frac
    ys, xs = np.nonzero(m)
    return ((xs.mean() + .5, ys.mean() + .5), (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)), frac


SIFT = cv2.SIFT_create(nfeatures=5000)


def feats(arr):
    g = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    f = max(1, int(round(700 / g.shape[1])))  # pixel art pequena: amplia antes do SIFT
    if f > 1:
        g = cv2.resize(g, None, fx=f, fy=f, interpolation=cv2.INTER_NEAREST)
    kp, des = SIFT.detectAndCompute(g, None)
    return np.float32([k.pt for k in kp]).reshape(-1, 2) / f, des


def registrar(src, dst, dmask=None, fdst=None):
    """Similaridade 2x3 que leva src -> dst, ou None. Validada pela diferenca de cor na sobreposicao."""
    ps, ds = feats(src)
    pd, dd = fdst or feats(dst)
    if ds is None or dd is None or len(ds) < 8 or len(dd) < 8:
        return None
    bons = [p[0] for p in cv2.BFMatcher().knnMatch(ds, dd, k=2) if len(p) == 2 and p[0].distance < .75 * p[1].distance]
    if len(bons) < 10:
        return None
    M, inl = cv2.estimateAffinePartial2D(ps[[b.queryIdx for b in bons]], pd[[b.trainIdx for b in bons]],
                                         method=cv2.RANSAC, ransacReprojThreshold=max(1.5, dst.shape[1] / 400))
    if M is None or int(inl.sum()) < 10:
        return None
    esc = math.hypot(M[0, 0], M[1, 0])
    if not (.25 < esc < 4) or abs(math.degrees(math.atan2(M[1, 0], M[0, 0]))) > 1.5:
        return None
    h, w = src.shape[:2]
    Mi = cv2.invertAffineTransform(M)
    dm = np.full(dst.shape[:2], 255, np.uint8) if dmask is None else dmask.astype(np.uint8) * 255
    valido = cv2.warpAffine(dm, Mi, (w, h), flags=cv2.INTER_NEAREST) > 0
    if valido.mean() < .15:
        return None
    wd = cv2.warpAffine(dst, Mi, (w, h), flags=cv2.INTER_NEAREST)
    if np.median(np.abs(wd.astype(np.int16) - src.astype(np.int16)).max(axis=2)[valido]) > 30:
        return None
    return M


class Tela:
    """Mapa-base montado (mosaico) a partir das bases dos grupos que se encaixam."""
    MAX = 6000

    def __init__(self, gid, arr, regiao):
        self.img, self.mask, self.regiao = arr.copy(), np.ones(arr.shape[:2], bool), regiao
        self.T = {gid: np.float64([[1, 0, 0], [0, 1, 0]])}
        self._f = None

    def f(self):
        if self._f is None:
            self._f = feats(self.img)
        return self._f

    def add(self, gid, arr, M):
        h, w = arr.shape[:2]
        cs = np.float64([[0, 0, 1], [w, 0, 1], [0, h, 1], [w, h, 1]]) @ M.T
        H, W = self.mask.shape
        px, py = int(max(0, -math.floor(cs[:, 0].min()))), int(max(0, -math.floor(cs[:, 1].min())))
        nx, ny = int(max(W, math.ceil(cs[:, 0].max())) + px), int(max(H, math.ceil(cs[:, 1].max())) + py)
        if nx > self.MAX or ny > self.MAX:
            return False
        sh = np.float64([[0, 0, px], [0, 0, py]])
        if (px, py, nx, ny) != (0, 0, W, H):
            img, m = np.zeros((ny, nx, 3), np.uint8), np.zeros((ny, nx), bool)
            img[py:py + H, px:px + W], m[py:py + H, px:px + W] = self.img, self.mask
            self.img, self.mask = img, m
            self.T = {k: v + sh for k, v in self.T.items()}
        M = M + sh
        wi = cv2.warpAffine(arr, M, (nx, ny), flags=cv2.INTER_NEAREST)
        wm = cv2.warpAffine(np.full((h, w), 255, np.uint8), M, (nx, ny), flags=cv2.INTER_NEAREST) > 0
        novo = wm & ~self.mask
        self.img[novo] = wi[novo]
        self.mask |= wm
        self.T[gid] = M
        self._f = None
        return True


def tag_local(l):
    vs = set(l["versoes"])
    if vs and all(v.startswith("the-isle-of-armor") for v in vs):
        return "isle-of-armor"
    if vs and all(v.startswith("the-crown-tundra") for v in vs):
        return "crown-tundra"
    return re.sub(r"[^a-z0-9]+", "-", (l.get("regiao_bp") or l["regiao"] or "outro").lower()).strip("-")


# nome do mapa quando a tela contem o local-ancora (ilhas de Alola sao mapas separados)
ANCORAS = {"melemele": "iki-town", "akala": "heahea-city", "ula-ula": "malie-city", "poni": "seafolk-village"}
TITULOS = {"isle-of-armor": "Isle of Armor", "crown-tundra": "Crown Tundra", "sevii-islands": "Sevii Islands",
           "melemele": "Alola - Melemele", "akala": "Alola - Akala", "ula-ula": "Alola - Ula'ula", "poni": "Alola - Poni"}


def achar_arquivos_mapa(locs):
    cand = {}
    for s, l in locs.items():
        if "bp" not in l:
            continue
        p = l["_ib"]
        reg = re.sub(r"[\[\]]", "", p.get("region", "")).split("|")[-1].strip() or l["regiao"]
        l["regiao_bp"] = reg
        c = []
        mp = limpar_arquivo(p.get("map", ""))
        if mp and not mp.lower().startswith("none."):
            c.append("File:" + mp)
        c += [f"File:{reg} {l['bp']} Map.png", f"File:{l['bp']} Map.png"]
        cand[s] = [norm_title(x) for x in c]
    info = imageinfo([x for c in cand.values() for x in c], 960)
    alvo = {}
    for s, c in cand.items():
        x = next((x for x in c if x in info), None)
        if x:
            alvo[s], locs[s]["_mapfile"] = info[x], x
    # fallback: arquivos "... Map.png" usados na pagina renderizada
    falta = [s for s in cand if s not in alvo]

    def imgs_pagina(s):
        d = api(BP, action="query", prop="images", imlimit="max", titles=locs[s]["bp"])
        ims = [i["title"] for p in d.get("query", {}).get("pages", []) for i in p.get("images", [])]
        ims = [i for i in ims if i.endswith(" Map.png") and not re.search(r"icon|Sprite|Town Map|Glitch", i)]
        bp = locs[s]["bp"]
        ims.sort(key=lambda i: (bp not in i, not i.startswith("File:" + locs[s]["regiao_bp"])))
        return s, ims[:1]
    extra = {s: ims[0] for s, ims in pmap(imgs_pagina, falta) if ims}
    info2 = imageinfo(list(extra.values()), 960)
    for s, f in extra.items():
        if f in info2:
            alvo[s], locs[s]["_mapfile"] = info2[f], f
    print(f"  mapas destacados encontrados: {len(alvo)} de {len(cand)} (fallback: {len(extra)})")
    return alvo


def gerar_mapas(locs):
    alvo = achar_arquivos_mapa(locs)
    imgs = dict(zip(alvo, pmap(lambda s: baixar_img(alvo[s]["url"]), list(alvo))))
    imgs = {s: im for s, im in imgs.items() if im is not None and im.width >= 100}
    grupos = sorted(agrupar(list(imgs.items())), key=len, reverse=True)

    # 4a. base de cada grupo (mediana) e destaque de cada membro no quadro do grupo
    bases, soltos, quadro = {}, [], {}  # quadro[slug] = (gid ou None, M local->tela depois)
    for gid, g in enumerate(grupos):
        if len(g) < 3:
            soltos += g
            continue
        tam = Counter(imgs[s].size for s in g).most_common(1)[0][0]
        arrs = {s: np.asarray(imgs[s] if imgs[s].size == tam else imgs[s].resize(tam, Image.NEAREST)) for s in g}
        bases[gid] = (np.median(np.stack(list(arrs.values())), axis=0).astype(np.uint8),
                      Counter(locs[s]["regiao"] for s in g).most_common(1)[0][0], g)
        for s in g:
            locs[s]["_med"] = medir(mascara_destaque(arrs[s], bases[gid][0]))
            quadro[s] = (gid, tam)

    # 4b. mosaico: encaixa as bases dos grupos umas nas outras (mesma regiao PokeAPI)
    telas, pend = [], sorted(bases, key=lambda g: len(bases[g][2]), reverse=True)
    while pend:
        prog = True
        while prog:
            prog = False
            for gid in list(pend):
                arr, reg, _ = bases[gid]
                for t in telas:
                    if t.regiao != reg:
                        continue
                    M = registrar(arr, t.img, t.mask, t.f())
                    if M is not None and t.add(gid, arr, M):
                        pend.remove(gid)
                        prog = True
                        break
        if pend:
            gid = pend.pop(0)
            telas.append(Tela(gid, bases[gid][0], bases[gid][1]))
    print(f"  grupos: {len(bases)} -> telas: {len(telas)}; imagens soltas: {len(soltos)}")

    # 4c. imagens soltas: registra direto numa tela e compara com ela
    for s in soltos:
        arr = np.asarray(imgs[s])
        ordem = sorted(telas, key=lambda t: t.regiao != locs[s]["regiao"])
        for t in ordem:
            M = registrar(arr, t.img, t.mask, t.f())
            if M is None:
                continue
            h, w = arr.shape[:2]
            Mi = cv2.invertAffineTransform(M)
            wb = cv2.warpAffine(t.img, Mi, (w, h), flags=cv2.INTER_NEAREST)
            val = cv2.warpAffine(t.mask.astype(np.uint8) * 255, Mi, (w, h), flags=cv2.INTER_NEAREST) > 0
            locs[s]["_med"] = medir(mascara_destaque(arr, wb, val))
            locs[s]["_M"], locs[s]["_tela"] = M, t
            break

    # 4c'. soltas que nao encaixaram (ex.: Crown Tundra, cada arquivo um enquadramento):
    # mosaico entre elas; base = mediana por pixel das que cobrem cada ponto
    pend, novas = [s for s in soltos if "_tela" not in locs[s]], []
    while pend:
        prog = True
        while prog:
            prog = False
            for s in list(pend):
                arr = np.asarray(imgs[s])
                for t in novas:
                    if t.regiao != locs[s]["regiao"]:
                        continue
                    M = registrar(arr, t.img, t.mask, t.f())
                    if M is not None and t.add(s, arr, M):
                        pend.remove(s)
                        prog = True
                        break
        if pend:
            s = pend.pop(0)
            novas.append(Tela(s, np.asarray(imgs[s]), locs[s]["regiao"]))
    novas = [t for t in novas if len(t.T) >= 3]  # menos que 3 recortes: mediana nao apaga o destaque
    for t in novas:
        t.soltas = True
        H, W = t.mask.shape
        out = np.zeros((H, W, 3), np.uint8)
        t.cov = np.zeros((H, W), np.uint8)  # quantos recortes cobrem cada pixel
        for y0 in range(0, H, 128):
            y1 = min(H, y0 + 128)
            pilha = []
            for s, M in t.T.items():
                M2 = M.copy()
                M2[1, 2] -= y0
                a = np.asarray(imgs[s])
                wi = cv2.warpAffine(a, M2, (W, y1 - y0), flags=cv2.INTER_NEAREST).astype(np.float32)
                wm = cv2.warpAffine(np.full(a.shape[:2], 255, np.uint8), M2, (W, y1 - y0), flags=cv2.INTER_NEAREST) > 0
                wi[~wm] = np.nan
                pilha.append(wi)
            with np.errstate(all="ignore"), warnings.catch_warnings():
                warnings.simplefilter("ignore")
                out[y0:y1] = np.nan_to_num(np.nanmedian(np.stack(pilha), axis=0)).astype(np.uint8)
            t.cov[y0:y1] = np.minimum(255, (~np.isnan(np.stack(pilha)[..., 0])).sum(axis=0))
        t.img = out
        for s, M in t.T.items():
            arr = np.asarray(imgs[s])
            h, w = arr.shape[:2]
            Mi = cv2.invertAffineTransform(M)
            wb = cv2.warpAffine(t.img, Mi, (w, h), flags=cv2.INTER_NEAREST)
            locs[s]["_med"] = medir(mascara_destaque(arr, wb))
            locs[s]["_M"], locs[s]["_tela"] = M, t
    print(f"  telas montadas com imagens soltas: {len(novas)} ({sum(len(t.T) for t in novas)} imagens)")
    telas += novas

    # 4d. nomes, arquivos e coordenadas em % da tela
    index, usadas = {}, set()
    for t in telas:
        if getattr(t, "soltas", False):
            membros = list(t.T)
        else:
            membros = [s for gid in t.T for s in bases[gid][2]] + [s for s in soltos if locs[s].get("_tela") is t]
        k = next((n for n, a in ANCORAS.items() if a in membros), None)
        if not k:
            k = Counter(tag_local(locs[s]) for s in membros).most_common(1)[0][0]
        base_k, i = k, 2
        while k in usadas:
            k, i = f"{base_k}-{i}", i + 1
        usadas.add(k)
        H, W = t.mask.shape
        im = Image.fromarray(t.img)
        if max(W, H) > 1600:
            im = im.resize((round(W * 1600 / max(W, H)), round(H * 1600 / max(W, H))), Image.LANCZOS)
        im.save(os.path.join(DATA, "maps", f"{k}.webp"), "WEBP", quality=80, method=6)
        index[k] = {"arquivo": f"maps/{k}.webp", "w": im.width, "h": im.height,
                    "titulo": (TITULOS.get(base_k) or base_k.replace("-", " ").title()) + (f" ({i - 1})" if k != base_k else "")}
        for s in membros:
            l = locs[s]
            M = l.get("_M")
            if M is None:
                gid, tam = quadro[s]
                M = t.T[gid]
                fw, fh = tam
            else:
                fh, fw = np.asarray(imgs[s]).shape[:2]
            r, frac = l["_med"]
            l["mapa"], l["_frac"] = k, round(frac, 5)
            if not r:
                l["confianca"] = "baixa"
                continue
            (cx, cy), (x0, y0, x1, y1) = r
            P = np.float64([[cx, cy, 1], [x0, y0, 1], [x1, y1, 1]]) @ M.T
            l["x"], l["y"] = round(100 * P[0, 0] / W, 1), round(100 * P[0, 1] / H, 1)
            l["bbox"] = [round(100 * P[1, 0] / W, 1), round(100 * P[1, 1] / H, 1),
                         round(100 * P[2, 0] / W, 1), round(100 * P[2, 1] / H, 1)]
            bw = (x1 - x0) * (y1 - y0) / (fw * fh)
            area = (l["bbox"][2] - l["bbox"][0]) * (l["bbox"][3] - l["bbox"][1]) / 1e4
            cobre = t.cov[min(H - 1, int(P[0, 1])), min(W - 1, int(P[0, 0]))] if hasattr(t, "cov") else 9
            # destaque minusculo/enorme, caixa > 10% do mapa ou ponto coberto por < 3 recortes (mediana nao confiavel)
            rotulo = (x1 - x0) / fw > .25 and (y1 - y0) / fh < .2  # faixa larga e baixa = caixa de texto de print do jogo
            l["confianca"] = ("alta" if 0.00005 < frac < 0.12 and bw < 0.4 and area < 0.10 and cobre >= 3 and not rotulo
                              else "baixa")
    # mesma caixa vinda de >= 3 arquivos de mapa diferentes = diferenca de enquadramento, nao destaque
    arqs = defaultdict(set)
    for l in locs.values():
        if "bbox" in l:
            arqs[(l["mapa"], tuple(l["bbox"]))].add(l.get("_mapfile"))
    for l in locs.values():
        b = l.get("bbox")
        if b and len(arqs[(l["mapa"], tuple(b))]) >= 3 and (b[2] - b[0]) * (b[3] - b[1]) >= 500:
            l["confianca"] = "baixa"
    return index


# ---------------------------------------------------------------- 5. fotos
def escolher_foto(p, gen):
    v = limpar_arquivo(p.get(FOTO_PARAM.get(gen, "-"), ""))
    if v:
        return v
    for k, val in p.items():  # arquivo com sufixo da geracao/jogo em qualquer param image*
        f = limpar_arquivo(val) if k.lower().startswith("image") else ""
        if f and any(re.search(rf"[ _]{suf}\.\w+$", f) for suf in FOTO_SUFIXO[gen]):
            return f
    # jogo com visual proprio (frlg, oras...): sem foto propria, deixa o app cair na geracao
    return limpar_arquivo(p.get("image", "")) if isinstance(gen, int) or gen in ("la", "sv", "za") else ""


def gerar_fotos(locs):
    pedidos = {}  # (slug, gen) -> File:
    for s, l in locs.items():
        if "bp" not in l:
            continue
        gens = sorted({VERSOES.get(v) or GAMES[v]["foto"] for v in l["versoes"]}, key=str)
        gens = [_k(g) for g in gens]
        if not gens:
            reg = next((i for i, n in REGIOES.items() if n == l["regiao"]), None)
            gens = [GEN_REGIAO[reg]] if reg else []
        for g in gens:
            f = escolher_foto(l["_ib"], g)
            if f:
                pedidos[(s, g)] = norm_title("File:" + f)
    info = imageinfo(list(pedidos.values()), 320)
    feitos = {}  # File: -> caminho relativo (mesma foto em 2 geracoes = 1 arquivo)

    def baixar(item):
        (s, g), f = item
        if f not in info:
            return item, None
        dest = f"photos/{re.sub(r'[^a-z0-9-]+', '-', s.lower()).strip('-')}-{g}.webp"
        full = os.path.join(DATA, dest)
        if not os.path.exists(full):
            im = baixar_img(info[f]["url"])
            if im is None:
                return item, None
            if im.width > 320:
                im = im.resize((320, round(im.height * 320 / im.width)), Image.LANCZOS)
            im.save(full, "WEBP", quality=70, method=6)
        return item, dest

    # dedup: baixa cada arquivo uma vez
    unicos = {}
    for k, f in pedidos.items():
        unicos.setdefault(f, k)
    for (k, f), dest in pmap(baixar, [(k, f) for f, k in unicos.items()]):
        if dest:
            feitos[f] = dest
    n = 0
    for (s, g), f in pedidos.items():
        if f in feitos:
            locs[s].setdefault("fotos", {})[str(g)] = feitos[f]
            n += 1
    # remove fotos orfas de execucoes anteriores
    usados = {os.path.basename(p) for p in feitos.values()}
    for fn in os.listdir(os.path.join(DATA, "photos")):
        if fn not in usados:
            os.remove(os.path.join(DATA, "photos", fn))
    print(f"  fotos: {n} referencias, {len(feitos)} arquivos")


# ---------------------------------------------------------------- 7. conferencia
def imagens_checagem(index, locs):
    try:
        fonte = ImageFont.truetype("arial.ttf", 11)
    except OSError:
        fonte = ImageFont.load_default()
    for k, m in index.items():
        im = Image.open(os.path.join(DATA, m["arquivo"])).convert("RGB")
        esc = max(1, round(1400 / im.width))
        im = im.resize((im.width * esc, im.height * esc), Image.NEAREST)
        dr = ImageDraw.Draw(im)
        for s, l in sorted(locs.items()):
            if l.get("mapa") != k or "x" not in l:
                continue
            x, y = l["x"] * im.width / 100, l["y"] * im.height / 100
            cor = (255, 0, 160) if l["confianca"] == "alta" else (255, 140, 0)
            b = l["bbox"]
            dr.rectangle([b[0] * im.width / 100, b[1] * im.height / 100, b[2] * im.width / 100, b[3] * im.height / 100],
                         outline=cor)
            dr.ellipse([x - 4, y - 4, x + 4, y + 4], fill=cor, outline=(0, 0, 0))
            dr.text((x + 5, y - 6), l["nome"], fill=(0, 0, 0), font=fonte, stroke_width=2, stroke_fill=(255, 255, 255))
        im.save(os.path.join(CHECK, f"{k}.png"))


def selfcheck():
    m = np.zeros((10, 20), bool)
    m[2:4, 10:12] = True
    r, frac = medir(m)
    assert r == ((11.0, 3.0), (10, 2, 12, 4)) and frac == 0.02, r
    a = (np.random.default_rng(0).random((120, 200, 3)) * 255).astype(np.uint8)
    a = cv2.resize(a, (800, 480), interpolation=cv2.INTER_NEAREST)
    M = registrar(a[40:440, 100:700], a)  # recorte deve voltar para o deslocamento (100, 40)
    assert M is not None and abs(M[0, 2] - 100) < 2 and abs(M[1, 2] - 40) < 2, M
    assert candidatos_titulo({"nome": "Sea Route 19", "regiao": "Kanto"}) == ["Kanto Route 19"]
    assert escolher_foto({"image": "A PE.png", "imageII": "A GSC.png"}, 2) == "A GSC.png"
    assert escolher_foto({"image": "A SwSh.png"}, 8) == "A SwSh.png"
    assert limpar_arquivo("[[File:X Y.png|200px]]") == "X Y.png"
    assert limpar_arquivo("Driftveil City {{CurrUnovaSeason}} B2W2.png") == "Driftveil City Spring B2W2.png"
    assert limpar_arquivo("HGSS Bell Tower-{{#switch: {{#time: G}}|4|5=Morning|10=Day}}.png") == "HGSS Bell Tower-Morning.png"


# ---------------------------------------------------------------- main
def main():
    selfcheck()
    locs = carregar_locais()
    print(f"locais: {len(locs)} (com encontros: {sum(1 for l in locs.values() if l['versoes'])})")
    resolver_titulos(locs)
    # locais dos jogos extraidos da Bulbapedia (chave bp:<titulo>): junta com o local PokeAPI de mesmo titulo
    # ou cria um local novo (Hisui, Paldea, Kitakami, Blueberry, Lumiose...)
    por_bp = {l["bp"]: s for s, l in locs.items() if "bp" in l}
    novos = {}
    for g in BP_REGIAO:
        p = os.path.join(DATA, "enc", g + ".json")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for key in json.load(f)["locais"]:
                t = key[3:]
                if t in por_bp:
                    locs[por_bp[t]]["versoes"] = sorted(set(locs[por_bp[t]]["versoes"]) | {g})
                else:
                    novos.setdefault(t, set()).add(g)
    pags = buscar_paginas(list(novos))
    for t, gs in novos.items():
        r = pags.get(t)
        if not r:
            continue
        locs["bp:" + t] = {"id": 0, "regiao": BP_REGIAO[sorted(gs)[0]], "nome": t, "versoes": sorted(gs),
                           "bp": r[0], "_wt": r[1]}
    for l in locs.values():
        if "bp" in l:
            l["_ib"] = infobox(l["_wt"])
    print(f"  paginas Bulbapedia: {sum('bp' in l for l in locs.values())}")
    index = gerar_mapas(locs)
    gerar_fotos(locs)

    saida, relat = {}, {"nao_encontrados": [], "sem_mapa": [], "baixa": []}
    for s, l in sorted(locs.items()):
        e = {"nome": l["nome"]}
        for k in ("bp", "mapa", "x", "y", "bbox", "confianca", "fotos"):
            if k in l:
                e[k] = l[k]
        if l["versoes"]:
            e["versoes"] = l["versoes"]
        saida[s] = e
        if "bp" in l and not s.startswith("bp:"):
            saida.setdefault("bp:" + l["bp"], e)  # mesma entrada pela chave bp: (ORAS, BDSP...)
        tag = f'{s} ({l["nome"]}, {l["regiao"] or "-"}){" *enc" if l["versoes"] else ""}'
        if "bp" not in l:
            relat["nao_encontrados"].append(tag)
        elif "x" not in l:
            relat["sem_mapa"].append(tag + f' [{l.get("_mapfile", "sem arquivo Map")}]')
        elif l["confianca"] == "baixa":
            relat["baixa"].append(tag + f' frac={l.get("_frac")}')
    with open(os.path.join(DATA, "locs.json"), "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(DATA, "maps", "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    # mapas de execucoes anteriores que sumiram
    for fn in os.listdir(os.path.join(DATA, "maps")):
        if fn.endswith(".webp") and fn[:-5] not in index:
            os.remove(os.path.join(DATA, "maps", fn))
    imagens_checagem(index, locs)

    por_mapa = Counter(l.get("mapa", "-") for l in locs.values())
    relat["por_mapa"] = {k: {"total": por_mapa[k],
                             "alta": sum(1 for l in locs.values() if l.get("mapa", "-") == k and l.get("confianca") == "alta"),
                             "com_encontros": sum(1 for l in locs.values() if l.get("mapa", "-") == k and l["versoes"])}
                         for k in por_mapa}
    with open(os.path.join(CHECK, "relatorio.json"), "w", encoding="utf-8") as f:
        json.dump(relat, f, ensure_ascii=False, indent=1)
    tot = sum(os.path.getsize(os.path.join(dp, fn)) for dp, _, fs in os.walk(DATA) for fn in fs)
    print("por mapa:", json.dumps(relat["por_mapa"]))
    print(f"alta={sum(l.get('confianca') == 'alta' for l in locs.values())} "
          f"baixa={len(relat['baixa'])} sem_mapa={len(relat['sem_mapa'])} nao_encontrados={len(relat['nao_encontrados'])} "
          f"com_foto={sum(1 for l in locs.values() if l.get('fotos'))} data={tot / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
