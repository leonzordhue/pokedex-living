#!/bin/sh
# Regera todos os dados do app, na ordem certa. Uso: sh scripts/build_all.sh
set -e
cd "$(dirname "$0")"
python -I build_enc_bp.py      # encontros da Bulbapedia (ORAS, BDSP, LA, SV, Z-A)
python -I build_avail.py       # disponibilidade, jogos e locais por jogo
python -I build_maps.py        # mapas, pinos e fotos
python -I build_maps_hisui.py  # Hisui: um mapa por área
python -I fix_paldea.py        # Paldea: encaixa o centro no mapa geral
python -I apply_overrides.py   # correções manuais + apelidos bp:
