# Pokédex Living Dex

Pokédex web para fechar a living dex de cada jogo principal, versão por versão (38 jogos):
Red, Blue, Yellow · Gold, Silver, Crystal · Ruby, Sapphire, Emerald, FireRed, LeafGreen · Diamond, Pearl, Platinum, HeartGold, SoulSilver · Black, White, Black 2, White 2 · X, Y, Omega Ruby, Alpha Sapphire · Sun, Moon, Ultra Sun, Ultra Moon, Let's Go Pikachu, Let's Go Eevee · Sword, Shield (com Isle of Armor e Crown Tundra), Brilliant Diamond, Shining Pearl, Legends: Arceus · Scarlet, Violet (com The Teal Mask e The Indigo Disk), Legends: Z-A.

## O que faz
- Escolha o jogo e veja a dex regional ou a nacional até a geração do jogo.
- **Pokémon em todos os jogos**: escolha um Pokémon e veja como obtê-lo em cada um dos 38 jogos (captura, evolução, ovo, troca, transferência, evento) com os locais resumidos; "Abrir neste jogo" leva à ficha completa.
- Link direto para compartilhar: `#todos/25` (Pikachu em todos os jogos) ou `#sword/25` (Pikachu no Sword).
- Busque por nome ou número. Filtros: todos, faltando, "faltando e dá pra pegar aqui", tenho.
- **Como obter** em cada jogo: captura direta, evoluindo, chocando ovo (com o incenso, quando precisa), exclusivo da versão irmã (trocar), evento, ou como trazer de outra geração (Time Capsule, Pal Park, Poké Transfer, Bank, HOME).
- **Onde encontrar**: local, método (grama, pesca, Headbutt, Rock Smash, surto, Poké Radar, SOS, horda, Max Raid, Dynamax Adventure, troca com NPC...), nível, chance, hora do dia, clima, estação e outras condições, tudo em português, com dicas.
- **Mapa**: mapa da região com o local marcado em cada card, foto do local na geração do jogo e um mapa geral com um ponto por local. Clicando no ponto aparecem todos os Pokémon do local (os que faltam na sua dex em vermelho).
- Linha evolutiva com os requisitos que valem naquele jogo.
- Descrição e categoria da Pokédex em português, arte oficial, sprite da época, shiny e grito.
- Marque o que já tem. O progresso fica no navegador; use Exportar/Importar para guardar ou passar para outro aparelho.

## Dados
- Encontros, dex e evoluções: [PokéAPI](https://pokeapi.co), ao vivo (Red/Blue até Sword/Shield e Let's Go).
- `data/enc/*.json`: encontros de Omega Ruby/Alpha Sapphire, Brilliant Diamond/Shining Pearl, Legends: Arceus, Scarlet/Violet (+DLCs) e Legends: Z-A, extraídos das tabelas da [Bulbapedia](https://bulbapedia.bulbagarden.net) por `scripts/build_enc_bp.py` (a PokéAPI não tem esses jogos).
- `data/avail.json`, `data/areas.json`, `data/games.json`: gerados por `scripts/build_avail.py` (lista de jogos em `scripts/games.json`).
- Ordem para atualizar tudo: `build_enc_bp.py`, `build_avail.py`, `build_maps.py`, `apply_overrides.py` (todos com `python -I`).
- `data/locs.json`, `data/maps/`, `data/photos/`: mapas e fotos dos locais da [Bulbapedia](https://bulbapedia.bulbagarden.net), gerados por `scripts/` (posição do pino calculada pela diferença entre o mapa com o local destacado e o mapa-base).
- `data/pt.json`: tradução das entradas da Pokédex.
- Imagens dos Pokémon: [PokeAPI/sprites](https://github.com/PokeAPI/sprites).

Projeto de fã, sem fins comerciais. Pokémon é marca da Nintendo, Game Freak e Creatures.
