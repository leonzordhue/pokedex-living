# Formato dos encontros extraídos da Bulbapedia (`data/enc/<versao>.json`)

Usado para os jogos que a PokéAPI não cobre ou cobre mal. Uma versão por arquivo:
`omega-ruby`, `alpha-sapphire`, `brilliant-diamond`, `shining-pearl`, `legends-arceus`,
`scarlet`, `violet` (inclui The Teal Mask e The Indigo Disk), `legends-za` (inclui Mega Dimension).

```json
{
  "versao": "scarlet",
  "fonte": "Bulbapedia (CC BY-NC-SA), extraído em AAAA-MM-DD",
  "locais": {
    "bp:South Province (Area One)": {"nome": "South Province (Area One)", "regiao": "paldea", "dlc": ""}
  },
  "enc": {
    "187": [
      {"loc": "bp:South Province (Area One)", "form": "", "m": "walk", "mpt": "Andando (grama/terra)",
       "lv": "2-8", "ch": "60", "cs": ["Dia", "Chuva"], "nota": ""}
    ]
  }
}
```

Regras:
- Chave de local = `"bp:" + título CANÔNICO da página da Bulbapedia` (depois de seguir redirect). Os mapas usam a mesma chave.
- Chave de `enc` = número da Pokédex Nacional como string, sem zeros à esquerda ("187").
- `form`: vazio para a forma padrão; senão o nome da forma em inglês minúsculo (ex.: "paldea", "galar", "alola", "hisui", "white-striped").
- `m`: método em inglês curto (reaproveite quando der: `walk`, `surf`, `old-rod`, `good-rod`, `super-rod`, `rock-smash`, `headbutt`, `gift`, `gift-egg`, `npc-trade`, `static`, `overworld`, `overworld-water`, `overworld-flying`, `horde`, `dexnav`, `poke-radar`, `grand-underground`, `tera-raid`, `mass-outbreak`, `space-time-distortion`, `alpha`, `tree-shake`, `ore`, `fishing`, `wild-zone`, `rooftop`, `rogue-mega`...).
- `mpt`: o mesmo método em português (BR), curto. `cs`: condições em português (hora do dia, clima, estação, versão da história, "Alpha", "Só depois do Hall of Fame", "Toca 5★" etc.). `ch`: chance como aparece (número em % sem o símbolo, ou texto como "Uma vez", "Raro").
- Só entram as linhas da VERSÃO do arquivo (as tabelas marcam yes/no por versão).
- `nota`: dica curta em português quando a tabela tiver algo útil (ex.: "Só aparece no céu", "Precisa de Ride Pokémon").
- JSON compacto, UTF-8.
