# -*- coding: utf-8 -*-
"""The roster, in player-slot order.

Slots 0-15 are the Samurai Heroes cast, and the spellings below are read off
that game's own English name plates - Saica, Kanbe and Mori are theirs, not
mine.  Slots 16-29 are Utage-exclusive, so those spellings are this patch's.

Second entries are the Xavism baptismal names Sorin hands out; they appear on
the plate under the real name, and the dialogue already uses these spellings.
"""
ROSTER = {
    0:  ["Masamune Date"],
    1:  ["Yukimura Sanada"],
    2:  ["Mitsunari Ishida"],
    3:  ["Ieyasu Tokugawa"],
    4:  ["Magoichi Saica"],
    5:  ["Kanbe Kuroda", "Josie Kuroda"],
    6:  ["Keiji Maeda"],
    7:  ["Tsuruhime"],
    8:  ["Kotaro Fuma"],
    9:  ["Motochika Chosokabe"],
    10: ["Yoshitsugu Otani"],
    11: ["Yoshihiro Shimazu", "Chest Shimazu"],
    12: ["Oichi"],
    13: ["Motonari Mori", "Sunday Mori"],
    14: ["Tadakatsu Honda"],
    15: ["Nobunaga Oda"],
    16: ["Muneshige Tachibana", "Gallop Tachibana"],
    17: ["Hideaki Kobayakawa"],
    18: ["Yoshiaki Mogami"],
    19: ["Tenkai"],
    20: ["Kenshin Uesugi"],
    21: ["Kasuga"],
    22: ["Sasuke Sarutobi"],
    23: ["Kojuro Katakura"],
    24: ["Matsu"],
    25: ["Toshiie Maeda"],
    26: ["Ujimasa Hojo"],
    27: ["Shingen Takeda"],
    28: ["Hisahide Matsunaga"],
    29: ["Sorin Otomo"],
}

# Slots whose English name art Samurai Heroes already shipped.
SH_SLOTS = set(range(16))
