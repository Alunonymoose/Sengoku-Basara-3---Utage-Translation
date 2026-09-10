# -*- coding: utf-8 -*-
"""Glosses for the single-character entries that appear in every route.

The high-index records of the story archives carry a one-glyph field beside
each speech.  Its value walks steadily up the font's ordinal order as the
record index rises, so it is an index the engine stores in the text encoding,
not a word - but it still has to be re-encoded into the Latin font like any
other run, and an uncovered entry renders blank.  Glossing each one keeps the
route at 100%, keeps the run short, and reads sensibly if it is ever drawn.

Written once here because these characters recur across all thirty routes.
"""
KANA = {
    'ぃ': 'i', 'い': 'i', 'う': 'u', 'ぇ': 'e', 'え': 'e', 'ぉ': 'o', 'お': 'o',
    'か': 'ka', 'き': 'ki', 'ぎ': 'gi', 'く': 'ku', 'ぐ': 'gu', 'け': 'ke',
    'げ': 'ge', 'こ': 'ko', 'ご': 'go', 'さ': 'sa', 'ざ': 'za', 'し': 'shi',
    'じ': 'ji', 'す': 'su', 'ず': 'zu', 'せ': 'se', 'ぜ': 'ze', 'そ': 'so',
    'ぞ': 'zo', 'た': 'ta', 'だ': 'da', 'ち': 'chi', 'っ': 'tsu', 'つ': 'tsu',
    'づ': 'zu', 'て': 'te', 'で': 'de', 'ど': 'do', 'ぷ': 'pu', 'へ': 'he',
    'べ': 'be', 'ゃ': 'ya', 'や': 'ya', 'ゅ': 'yu', 'ゆ': 'yu', 'ょ': 'yo',
    'よ': 'yo', 'ら': 'ra', 'ろ': 'ro', 'ゎ': 'wa', 'を': 'wo',
    'な': 'na', 'に': 'ni', 'ぬ': 'nu', 'ね': 'ne',
    'イ': 'i', 'ゥ': 'u', 'ェ': 'e', 'エ': 'e', 'ガ': 'ga', 'キ': 'ki',
    'ギ': 'gi', 'ク': 'ku', 'ケ': 'ke', 'コ': 'ko', 'ザ': 'za', 'シ': 'shi',
    'ジ': 'ji', 'ス': 'su', 'タ': 'ta', 'ダ': 'da', 'チ': 'chi', 'ッ': 'tsu',
    'ツ': 'tsu', 'テ': 'te', 'ト': 'to', 'ノ': 'no', 'パ': 'pa', 'フ': 'fu',
    'ウ': 'u', 'オ': 'o', 'デ': 'de', 'ド': 'do', 'カ': 'ka', 'グ': 'gu',
    'ロ': 'ro', 'ゾ': 'zo', 'ナ': 'na', 'ズ': 'zu', 'ゲ': 'ge', 'ネ': 'ne',
    'ニ': 'ni',
    'ゴ': 'go', 'バ': 'ba', 'ほ': 'ho',
    'ソ': 'so',
    'ぼ': 'bo', 'は': 'ha',
    'ぁ': 'a', 'び': 'bi', 'ゼ': 'ze',
    'ば': 'ba', 'ぱ': 'pa', 'ひ': 'hi', 'ぺ': 'pe', 'ま': 'ma',
    'ォ': 'o', 'セ': 'se', 'ヒ': 'hi', 'ビ': 'bi', 'ピ': 'pi', 'プ': 'pu',
    'ぅ': 'u', 'り': 'ri', 'る': 'ru', 'れ': 're', 'も': 'mo', 'あ': 'a',
    'ふ': 'fu', 'ぶ': 'bu', 'み': 'mi', 'む': 'mu', 'め': 'me',
}

_KANJI_SRC = """
判 Judge|別 Part|利 Gain|刺 Pierce|刻 Carve|前 Front|劇 Drama|劉 Split
加 Add|助 Aid|勢 Force|匂 Scent|北 North|匿 Hide|十 Ten|参 Visit
及 Reach|友 Friend|収 Gather|受 Receive|口 Mouth|古 Old|叫 Shout|可 May
叱 Scold|叶 Grant|司 Rule|合 Join|吉 Fortune|同 Same|名 Name|向 Face
君 Lord|否 Nay|吹 Blow|吻 Kiss|吾 Self|呂 Spine|呈 Present|告 Tell
周 Circuit|呪 Curse|味 Taste|呵 Laugh|呼 Call|命 Life|咲 Bloom|品 Grace
哭 Wail|問 Ask|啜 Sip|喜 Joy|嗜 Relish|嘲 Mock|四 Four|回 Turn
土 Earth|増 Increase|局 Bureau|居 Dwell|屈 Bend|届 Reach|屋 House|屓 Strain
履 Tread|山 Mountain|岡 Hill|岩 Rock|島 Island|崎 Cape|崩 Crumble|嵐 Storm
川 River|州 Province|巡 Patrol|巧 Skill|差 Difference|己 Self|巻 Scroll|市 Market
希 Hope|帚 Broom|師 Master|帰 Return|常 Constant|幕 Curtain|平 Level|年 Year
幸 Fortune|幹 Trunk|幻 Illusion|幼 Young|幾 Several|広 Wide|庄 Manor|底 Bottom
度 Degree|座 Seat|庫 Store|庭 Garden|庵 Hermitage|康 Health|延 Extend|弁 Speech
式 Rite|弔 Mourn|弘 Vast|弥 Ever|弱 Weak|張 Stretch|強 Strong|当 Hit
待 Wait|後 After|復 Restore|徳 Virtue|心 Heart|必 Certain|志 Will|忘 Forget
忙 Busy|応 Answer|忠 Loyal|念 Thought|怒 Anger|怖 Fear|思 Think|急 Haste
性 Nature|怯 Flinch|恐 Dread|恩 Kindness|息 Breath|恵 Blessing|悔 Regret|悦 Delight
悪 Evil|悲 Grief|情 Feeling|惑 Bewilder|惚 Enrapture|惜 Grudge|惨 Wretched|惹 Attract
愉 Pleasure|意 Intent|愚 Folly|愛 Love|感 Feel|慈 Mercy|態 Manner|慌 Fluster
慎 Prudence|慟 Lament|慢 Pride|慣 Custom|慶 Rejoice|憎 Hatred|憶 Memory|懸 Suspend
懺 Repent|成 Become|我 Self|戒 Precept|或 Certain|戦 War|戸 Door|時 Time
晒 Bleach|景 Scene|晴 Clear|智 Wisdom|曇 Cloud|曖 Vague|更 Renew|書 Write
服 Garment|朝 Morning|期 Term|木 Tree|未 Not yet|末 End|本 Origin|朱 Vermilion
朽 Decay|杉 Cedar|材 Timber|村 Village|条 Article|来 Come|杯 Cup|東 East
松 Pine|枚 Sheet|果 Fruit|枯 Wither|柄 Handle|某 Certain|染 Dye|柱 Pillar
柴 Brushwood|根 Root|格 Rank|案 Plan|桶 Pail|極 Extreme|楼 Tower|楽 Ease
構 Stance|様 Manner|標 Mark|模 Pattern|横 Side|欠 Lack|次 Next|欲 Desire
歌 Song|止 Halt|正 Right|武 Valour|歩 Step|歪 Warp|歯 Tooth|歳 Age
死 Death|殊 Special|残 Remain|殲 Annihilate|殺 Kill|毎 Every|毛 Hair|民 People
気 Spirit|水 Water|永 Eternal|汁 Broth|求 Seek|汗 Sweat|江 Inlet|決 Decide
沈 Sink|河 River|沸 Boil|治 Govern|況 Condition|泉 Spring|波 Wave|洗 Wash
洞 Cavern|津 Harbour|活 Live|流 Flow|浄 Pure|浅 Shallow|浪 Billow|浮 Float
海 Sea|浸 Steep|消 Vanish|涙 Tear|涯 Shore|渡 Cross|温 Warm|満 Full
源 Source|滅 Perish|滞 Stagnate|滴 Drop|漆 Lacquer|演 Perform|潮 Tide|澄 Clear
澱 Sediment|濂 Ripple|火 Fire|灯 Lamp|灰 Ash|炎 Flame|点 Point|為 Deed
烈 Fierce|無 Nothing|焦 Scorch|然 So|焼 Burn|熟 Ripen|熱 Heat|燃 Blaze
父 Father|爽 Refreshing|片 Fragment|物 Thing|牲 Offering|特 Special|犧 Sacrifice|犬 Dog
狂 Madness|狙 Aim|独 Alone|狭 Narrow|猛 Fierce|献 Offer|猶 Yet|猿 Monkey
獲 Seize|玄 Mystery|玉 Jewel|王 King|玩 Toy|現 Present|理 Reason|琶 Lute
瓊 Gem|瓦 Tile|甘 Sweet|生 Life|用 Use|田 Field|由 Cause|男 Man
界 Realm|畏 Awe|畑 Field|留 Detain|畜 Beast|番 Order|異 Strange|疑 Doubt
白 White|百 Hundred|皆 All|盛 Flourish|秀 Excel|私 Private|秋 Autumn|程 Extent
稙 Seedling|稲 Rice|積 Pile|穢 Defile|空 Sky|突 Thrust|窟 Cave|窮 Extremity
立 Stand|端 Edge|竹 Bamboo|笑 Laugh|第 Order|筆 Brush|筈 Ought|等 Equal
筋 Sinew|答 Answer|策 Scheme|箱 Box|篠 Bamboo grass|簒 Usurp|簡 Simple|米 Rice
粋 Pure|糾 Twist|約 Promise|紅 Crimson|紋 Crest|紗 Gauze|級 Grade|組 Band
緋 Scarlet|練 Temper|罪 Sin|罰 Punish|美 Beauty|義 Duty|者 One|肉 Flesh
肝 Liver|背 Back|胸 Breast|能 Skill|腹 Belly|臣 Retainer|自 Self|舞 Dance
船 Ship|花 Flower|芳 Fragrance
嘆 Sigh|刃 Blade|捧 Dedicate|祀 Enshrine|祈 Pray|祓 Purify|祖 Ancestor
祝 Celebrate|神 God|祷 Prayer|禁 Forbid|福 Luck|分 Divide
処 Place|囀 Chirp|崖 Cliff|巌 Crag|曰 Say|曾 Once|替 Replace|最 Most
冷 Cold|凄 Dread|糸 Thread|純 Pure|細 Fine
再 Again|悩 Worry|内 Inside|双 Pair|左 Left|帯 Sash|注 Pour|箸 Chopstick
編 Weave|縫 Sew|習 Learn|考 Think|聞 Hear|聴 Listen|肌 Skin|臨 Attend|刀 Sword
凛 Cold|営 Camp|厳 Stern|損 Loss|又 Again|右 Right|小 Small|少 Few|尖 Sharp
尻 Rear|尽 Exhaust|屍 Corpse|望 Wish|札 Tag|杏 Apricot|束 Bundle|泣 Weep
派 Faction|淤 Silt|煙 Smoke|産 Bear|的 Target|笶 Smile|粗 Coarse|縛 Bind
置 Place|羅 Gauze|羽 Feather|育 Rear|腕 Arm|興 Rise|舎 Hut|良 Good|若 Young
茂 Lush|茶 Tea|草 Grass|指 Point|善 Good|切 Cut|去 Depart|叢 Thicket|形 Shape
彼 He|清 Pure|濯 Rinse|犯 Offend|憤 Rage|籠 Basket|恋 Love|恨 Grudge|卿 Lord
厄 Misfortune|就 Assume|尾 Tail|巫 Shrine|従 Follow|得 Gain|御 Honour|揃 Gather
援 Aid|普 Common|月 Moon|有 Have|殿 Lord|比 Compare|浴 Bathe|焚 Burn|申 State
発 Set out|直 Direct|相 Mutual|翼 Wing|胴 Torso|腫 Swell|腰 Waist|舟 Boat
色 Colour|芸 Art|芽 Bud|苦 Bitter|荒 Wild|荷 Load|荼 Bitter herb|菜 Greens
快 Pleasant|怪 Strange|拝 Worship|啓 Open|拾 Pick up|出 Go out|剣 Blade
唯 Only|勘 Intuition|原 Plain|反 Oppose|召 Summon|尊 Revere|導 Guide|尼 Nun
布 Cloth|彫 Carve|持 Hold|新 New|昇 Ascend|昌 Prosper|明 Bright|昔 Long ago
星 Star|春 Spring|昨 Yesterday|昼 Noon|晩 Evening|椒 Pepper|椿 Camellia
業 Deed|溺 Drown|炉 Hearth|瞼 Eyelid|矛 Spear|知 Know|硬 Hard|示 Show
祭 Festival|称 Name|稼 Earn|穏 Calm|究 Study|竈 Stove|籤 Lot|腐 Rot|腥 Raw
懐 Bosom|叩 Strike|員 Member|峰 Peak|席 Seat|役 Duty|忍 Endure|柿 Persimmon
桜 Cherry|樹 Tree|橋 Bridge|櫻 Cherry|歓 Joy|氏 Clan|法 Law|泰 Peace|添 Attach
済 Settle|漬 Steep|潔 Pure|潛 Hide|潤 Moisten|烙 Brand|焙 Roast|爪 Claw|牛 Ox
牡 Male|状 Form|瓜 Melon|痛 Pain|筒 Tube|節 Joint|精 Spirit|締 Bind|緯 Weft
縄 Rope|繁 Thrive|脇 Side
慨 Lament|慮 Consider|影 Shadow|引 Pull|制 Control|信 Trust|保 Keep
喧 Noisy|喰 Devour|暴 Violent|効 Effect|微 Faint|狼 Wolf|価 Value|列 Row
剥 Peel|募 Recruit|包 Wrap|占 Occupy|如 Like|姉 Elder sister|始 Begin
姫 Princess|姿 Figure|婆 Old woman|嫌 Dislike|子 Child|字 Letter|客 Guest
宣 Proclaim|宮 Palace|宴 Feast|宵 Evening|対 Face|封 Seal|敗 Defeat|数 Number
敵 Enemy|暇 Leisure|曲 Tune|油 Oil|泥 Mud|滝 Waterfall|潰 Crush|瀬 Shallows
煮 Boil|狩 Hunt|砂 Sand|砦 Fort|磨 Polish|功 Merit|劣 Inferior|削 Whittle
属 Belong|杖 Staff|烏 Crow|焉 End|猜 Suspect|猪 Boar|率 Lead|画 Picture
疲 Weary|群 Flock|史 History|各 Each|吐 Spit|層 Layer|工 Craft|杜 Grove
毒 Poison|汚 Foul|渦 Whirl|港 Harbour|漢 Man|炊 Cook|猫 Cat|秘 Secret
粉 Powder|給 Supply|網 Net|総 Whole|署 Post
骨 Bone|高 High|入 Enter|嘘 Lie|噂 Rumour|斬 Slay|早 Early|元 Origin
恥 Shame|初 First|断 Sever|旦 Dawn|旨 Gist|旬 Season|繋 Tie|老 Old|耳 Ear
凶 Ill omen|黒 Black|髭 Moustache|麟 Kirin|家 House|旗 Banner|矢 Arrow
確 Certain|先 Ahead|兄 Elder brother|優 Gentle|魚 Fish|鮪 Tuna|鮭 Salmon
駆 Gallop|騎 Ride|験 Test|驅 Drive|髄 Marrow|秒 Second|太 Stout|夫 Husband
失 Lose|奉 Serve|吼 Roar|悟 Awaken|昆 Kelp|易 Easy|暗 Dark|槍 Spear
母 Mother|準 Standard|溢 Overflow|熊 Bear|狐 Fox|狡 Cunning|獣 Beast
眼 Eye|絢 Splendid|纏 Wrap|鼻 Nose|魅 Charm|髪 Hair|鬱 Gloom|鬼 Demon
魂 Soul|麗 Fair|黙 Silent|場 Place|堵 Wall|塗 Coat|塞 Block|専 Sole
将 General|救 Save|教 Teach|散 Scatter|旅 Journey|既 Already|日 Day
是 Right|帳 Curtain|映 Reflect|暁 Dawn|競 Vie|築 Build|絆 Bond|全 Whole
兜 Helm|八 Eight|鳥 Bird|鶴 Crane|鹿 Deer|弐 Two|馬 Horse|力 Strength
勇 Brave|勧 Urge|化 Change|印 Seal|危 Peril|即 Instant|厠 Privy|好 Fond
妄 Delusion|嬉 Glad|存 Exist|孫 Grandchild|官 Office|定 Fixed|実 Fruit
容 Form|授 Grant|掌 Palm|掟 Rule|探 Seek|接 Join|揺 Sway|撃 Strike
撤 Withdraw|擁 Embrace|攫 Snatch|攻 Attack|放 Release|政 Rule|故 Cause
敬 Respect|敷 Spread|文 Letter|料 Fee|殻 Shell|涜 Defile|深 Deep|混 Mix
滑 Slip|球 Sphere|瑕 Flaw|畳 Mat|痴 Folly|癒 Heal|盟 Pact|目 Eye|真 True
眠 Sleep|着 Wear|瞳 Pupil|石 Stone|研 Hone|砲 Cannon|破 Break|磯 Shore
祇 Deity|肖 Likeness|耗 Wear away|啼 Cry
移 Shift|儚 Fleeting|像 Image|傷 Wound|偉 Great|卒 Soldier|屏 Screen
帽 Cap|穴 Hole|凡 Common|冗 Idle|和 Harmony|瞬 Blink|礼 Thanks|僅 Scant
光 Light|傾 Lean|動 Move|勝 Win|卵 Egg|宝 Treasure|害 Harm|稚 Childish
稽 Rehearse|繰 Reel|耐 Endure|肩 Shoulder|臭 Stench|察 Perceive|寺 Temple
岸 Shore|朗 Clear|枷 Fetter|棋 Chess|殴 Strike|段 Step|洒 Stylish|淋 Lonely
溶 Melt|睨 Glare|符 Token|箇 Item|索 Search|舐 Lick|悶 Writhe|嘯 Boast
律 Law|猾 Sly|胞 Cell|臼 Mortar
兵 Soldier|往 Go|充 Fill|具 Tool|兼 Serve both|渋 Astringent|社 Shrine
南 South|共 Together|冬 Winter|公 Public|基 Base|堂 Hall|報 Report|勲 Merit
屁 Trifle|斐 Worth|暖 Warm|暫 Awhile|棄 Discard|棒 Rod|氷 Ice|碁 Go
碌 Decent|紛 Confuse|績 Achievement|聳 Tower|落 Fall|葉 Leaf|蒲 Rush
蒼 Blue|薄 Thin|薔 Rose|虎 Tiger|虚 Void|六 Six|団 Group|囮 Decoy|単 Single
厭 Weary|富 Wealth|寝 Sleep|弾 Shot|欺 Deceive|砕 Shatter|千 Thousand
巣 Nest|巨 Giant|激 Fierce|牙 Fang|々 Repeat|粥 Gruel
怨 Rancour|鶏 Fowl|驕 Pride|昧 Obscure|億 Hundred million|鉄 Iron
量 Measure|金 Gold|鈍 Dull|鈴 Bell|隙 Gap|隠 Hide|雀 Sparrow|偽 False
邪 Wicked|閻 Yama|郎 Man|闥 Door|部 Section|闖 Intrude|郷 Home|堕 Fall
機 Device|禦 Ward off|稀 Rare|穰 Abundance|働 Labour|儀 Rite|集 Gather
雑 Coarse|難 Hardship|健 Sound|那 Which|防 Defend|到 Arrive|副 Deputy
努 Strive|劫 Aeon|労 Toil|匹 Match|半 Half|士 Retainer|奥 Depths|奪 Seize
奮 Rouse|女 Woman|奴 Fellow|委 Entrust|戴 Receive|投 Cast|折 Break
抜 Draw|択 Choose|抱 Embrace|押 Press|拙 Clumsy|拭 Wipe|拶 Press
挟 Pinch|挨 Push|振 Shake|捉 Grasp|捨 Cast off|据 Set|捻 Twist|掛 Hang
掠 Graze|掻 Scratch|描 Depict|昂 Rise|検 Inspect|楯 Shield|殆 Nearly
毀 Damage|滾 Seethe|焔 Flame|猟 Hunt|猩 Ape|皮 Skin|省 Reflect|看 Watch
眺 Gaze|瞞 Deceive|瞭 Clear|隣 Neighbour
冴 Clear|凌 Endure|儲 Profit|兆 Sign|禄 Stipend|務 Duty|匠 Artisan
宿 Lodging|射 Shoot|忌 Shun|没 Sink|照 Shine|盤 Board|短 Short|羨 Envy
償 Atone|暮 Dusk|減 Decrease|算 Reckon|紹 Introduce
困 Trouble|刑 Penalty|崇 Revere|憾 Regret|手 Hand|才 Talent|方 Way
"""

KANJI = {}
for _part in _KANJI_SRC.replace('\n', '|').split('|'):
    _part = _part.strip()
    if not _part:
        continue
    _k, _v = _part.split(' ', 1)
    KANJI[_k] = _v

PUNCT = {'\u300f': '"', '\u300d': '"', '\u300e': '"', '\u300c': '"'}

PUNCT.update({'０': '0', '１': '1', '２': '2', '３': '3',
              '４': '4', '５': '5', '６': '6', '７': '7',
              '８': '8', '９': '9', '？': '?', '～': '~'})

SINGLE = dict(KANA)
SINGLE.update(KANJI)
SINGLE.update(PUNCT)
