# Live Utage ARC Resource-Class Census — 2026-09-25

Source: current live `E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom\eng` tree.

The tree contained 4,645 PS3 big-endian ARC v8 files and 68,325 ARC members in this census.

All **48 distinct live resource type hashes** resolve using the combined public REvilLib SB3 / Samurai Heroes PS3 class inventories and the MT Framework V2 class-hash algorithm.

| Hash | Count | Class | Ext |
|---|---:|---|---|
| 241F5DEB | 50342 | rTexture | tex |
| 10C460E6 | 4100 | rMessage | msg |
| 2EA515BF | 4100 | rMessageInfo | mif |
| 19DB4587 | 3326 | rRoomData | rdt |
| 1D609FFB | 2037 | rFontCode | fnt |
| 5E0EF076 | 2037 | rAscii | asc |
| 167DBBFF | 1515 | rSoundStreamRequest | stq |
| 58A15856 | 136 | rModel | mod |
| 73850D05 | 117 | rArchive | arc |
| 276DE8B7 | 115 | rEffect2D | e2d |
| 60DD1B16 | 111 | rLayoutSpr | lsp |
| 6D5AE854 | 111 | rEffectList | efl |
| 0B52347D | 90 | rPlParam | ppm |
| 30FC745F | 32 | rSoundSubMixer | smx |
| 4E397417 | 20 | rEffectAnim | ean |
| 4C0DB839 | 18 | rScheduler | sdl |
| 619CF7E7 | 14 | rPalette | plt |
| 76042FD2 | 12 | rEffectCollect | eco |
| 7C067B17 | 7 | rWeaponData | wpd |
| 398BD2C5 | 6 | rOtomoData | otm |
| 7E33A16C | 6 | rSoundPackage | spc |
| 1BCC4966 | 6 | rSoundRequest | srq |
| 255926EF | 6 | rAnimeTexSrtList | ltsa |
| 0315E81F | 4 | rSoundDirectionalSet | sds |
| 7DC513BA | 4 | rQuestInfo | qif |
| 2D12E086 | 4 | rSoundRandom | srd |
| 494CE020 | 4 | rRewardDrop | rew |
| 76820D81 | 4 | rMotionList | lmt |
| 4323D83A | 4 | rSceneTexture | stex |
| 6005E229 | 3 | rFontColor | fcl |
| 3CFBE7D5 | 3 | rPlParamCommon | ppc |
| 6246E90D | 3 | rSchedulerCtrl | scn |
| 340AD7F6 | 3 | rAnimeMatList | lcla |
| 39C52040 | 3 | rCameraList | lcm |
| 0ECD7DF4 | 2 | rSoundCurveSet | scs |
| 232E228C | 2 | rSoundReverb | rev_ps3 |
| 2B40AE8F | 2 | rSoundEQ | equ |
| 23DBF8CE | 2 | rBasaraShop | bsh |
| 280C9CB7 | 2 | rSetModelInfo | smi |
| 015D1B6B | 2 | rScrSetData | sst |
| 1DA0352D | 2 | rTenkaPlInfo | tpi |
| 5B99F299 | 2 | rTenkaUnlock | tul |
| 0D49BAAE | 1 | rOtomoPresent | pre |
| 4CD902BC | 1 | rVersusPlayerInfo | vpi |
| 314ACB2A | 1 | rVersus30Player | v30 |
| 4115DFF1 | 1 | rFieldPos | fpd |
| 0C103FAA | 1 | rFieldInfo | fif |
| 1ACCC2DD | 1 | rEvtParam | etp |

## Hash rule

For these resource class names:

```text
class_hash = (~CRC32(class_name)) & 0x7FFFFFFF
```

This is the MT Framework V2 hash corroborated by REvilLib and known Utage vectors.

## Important correction for ASCII-related resources

`rAscii` is `0x5E0EF076`.

The tiny raw resources named `msg\ascii\...\ascii_*_ID_HQ` in `basara.arc` / `startup.arc` are actually typed as `rPalette` (`0x619CF7E7`), not `rAscii`.

Do not infer resource class solely from an internal path segment such as `ascii`.
