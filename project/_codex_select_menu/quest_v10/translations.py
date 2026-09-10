TRANSLATIONS={}
families=[('Bull','Red'),('Lion','Red'),('Turtle','Green'),('Rice Ball','Silver'),('Boar','Brown'),('Tiger','Yellow'),('Fan','Sun'),('Sakura','Coral'),('Centipede','Red'),('Pauldron','Indigo'),('Seashell','Amber'),('Chick','Pink'),('Mantis','Green'),('Locust','Green'),('Dragon','Sky'),('Spear','Blue'),('Crab','Brown'),('Horse','Brown'),('Bat','Scarlet')]
for g,(noun,color) in enumerate(families):
 for tier,prefix in enumerate(['Gray',color,'Gold']):
  idx=192+3*g+tier
  if idx<=247:TRANSLATIONS[idx]=f'{prefix} {noun}'
for g,stat in enumerate(['health','attack power','defense']):
 for t,verb in enumerate(['Increases','Considerably increases','Greatly increases']):TRANSLATIONS[400+g*3+t]=f'{verb} {stat}.'
templates=[
'{v} health restored by healing items.',
'{v} BASARA attack power.',
'{v} attack during Hero Time or Sengoku Drive.',
'{v} attack against base captains.\n<c>No effect in Japan\'s Event.</c>',
'{v} elemental attack chance.\n<c>Requires an elemental weapon.</c>',
'{v} the chance of breaking guards and stunning enemies.',
'{v} resistance to staggering, guard breaks and stunning.',
'{v} attack for each allied base.\n<c>No effect in Japan\'s Event.</c>',
'Each BASARA Assist raises attack and defense. {effect} effect.\nStacks up to 10 times.',
'{v} attack and defense when near death.',
'{v} attack power while airborne.',
'Full health, BASARA and Hero Time give a {effect} attack boost.\nWith Sengoku Drive, one stock is enough.',
'{v} the power of the first hit in a normal attack chain.',
'{v} parry attack power.',
]
for g,template in enumerate(templates):
 for t,(verb,effect) in enumerate([('Increases','Small'),('Considerably increases','Medium'),('Greatly increases','Strong')]):TRANSLATIONS[409+g*3+t]=template.format(v=verb,effect=effect)
for t,seconds in enumerate([10,15,30]):TRANSLATIONS[451+t]=f'Huge attack boost for the first {seconds} seconds of battle.\nEquipping more copies adds to the duration.'
TRANSLATIONS[454]='Slowly restores health while guarding. Small effect.'
TRANSLATIONS[455]='Slowly restores health while guarding. Medium effect.'
for i in range(4):
 TRANSLATIONS[336+i]=f'Clear Mind {i+1}'
 TRANSLATIONS[340+i]=f'Last Breath {i+1}'
 TRANSLATIONS[544+i]='Gain one weapon. Four copies improve its quality.\n<c>No guarding. Wearer only. No effect in Japan\'s Event.</c>'
 TRANSLATIONS[548+i]='Better chest and weapon quality per copy. Four improve it more.\n<c>No healing. Wearer only. No effect in Japan\'s Event.</c>'
names=['Oshu Chief','Peerless Spear','Wrathful Lord','Eastern Light','Smoky Flight','Heavy Schemes','Splendid Soul','Pure White','Swift Gale','Heavenly Garb','Dark Stars','One-Hit Kill','Phantom Words','Cunning Lord',"Sengoku's Best",'Demon King','Clear Skies','Autumn Night','Strange Dance','Merciful Eye','Divine Speed','Moonlit Love','Sky Runner','Noble Outlaw','Brilliant Mind','Free Spirit','Iron Resolve','War God','Supreme One','Boundless Soul','Six God Beads','EXP Hairpin','Six Paths Map','Lottery Ticket','Resonant Blades','Gold Blossom']
TRANSLATIONS.update({344+i:s for i,s in enumerate(names)})
descs=[
'<c>Masamune only.</c> Start battle in permanent six-sword mode.',
'<c>Yukimura only.</c> Start battle with permanent Burning Soul.',
'<c>Mitsunari only.</c> Equipped Terror lasts indefinitely.\nAll weapons have a 15% chance of dark elemental attacks.',
'<c>Ieyasu only.</c> Start battle with the hood up.\nShortens charging time.',
'<c>Magoichi only.</c> Normal attacks fire rockets instead of bullets.',
'<c>Kanbe only.</c> Greatly increases the number of spins in skills.\nEvasive steps also leave bombs behind.',
'<c>Keiji only.</c> Taunting makes nearby enemies dance.',
'<c>Tsuruhime only.</c> Start battle inside a bubble.\nDashing into enemies traps them in bubbles.',
'<c>Kotaro only.</c> Airborne attacks count as 3 hits per strike.\nAll airborne attacks are critical hits.',
'<c>Motochika only.</c> Adds huge spikes to the net for more damage.\nThe net can also catch certain previously immune warriors.',
'<c>Yoshitsugu only.</c> Attacks on marked enemies count as 3 hits.',
'<c>Yoshihiro only.</c> Both you and your enemies die in one hit.',
'<c>Oichi only.</c> Revive once per stage after losing all health.',
'<c>Mori only.</c> No staggering while setting traps.\nTraps last twice as long.',
'<c>Tadakatsu only.</c> Special arts have no time limit.\nElectromagnetic mode no longer drains health.',
'<c>Nobunaga only.</c> Greatly extends Hero Time and Sengoku Drive.',
'<c>Muneshige only.</c> Start battle permanently electrified.',
'<c>Hideaki only.</c> At full health, his eating skill gives fine food.\nNormal eating also restores health.',
'<c>Yoshiaki only.</c> Taunting makes you play dead.\nHealth and BASARA recover while playing dead.',
'<c>Tenkai only.</c> Start battle with permanent Climax of Sacrifice.',
'<c>Kenshin only.</c> Divine Domain boosts speed and adds ice attacks.\nDivine Domain also lasts longer.',
'<c>Kasuga only.</c> Any attack can bind enemies it hits.',
'<c>Sasuke only.</c> Dashing, jumping and evading summon shadow\nclones that attack enemies.',
'<c>Kojuro only.</c> Start battle in permanent Extreme Slaughter mode.',
'<c>Matsu only.</c> Doubles the power of all animal attacks.',
'<c>Toshiie only.</c> Moves faster and strengthens all unique skills\nand special arts.',
'<c>Ujimasa only.</c> Triples the duration of Hojo Moxibustion\nand Hojo Glory buffs.',
'<c>Shingen only.</c> Moves faster and strengthens all unique skills\nand special arts.',
'<c>Hisahide only.</c> Start battle in permanent flame-realm mode.',
'<c>Sorin only.</c> Greatly boosts converted troops.\nDamage taken is multiplied by five.'
]
TRANSLATIONS.update({552+i:s for i,s in enumerate(descs)})
TRANSLATIONS[583]='Gain 5 extra EXP for each enemy defeated.'
TRANSLATIONS[585]='Increases the chance of finding BASARA Lottery tickets.\n<c>No effect in Japan\'s Event.</c>'
TRANSLATIONS[586]='Doubles weapon attack when both players equip this item.'
TRANSLATIONS[587]='Improves the quality of acquired treasure chests and weapons.\n<c>No effect in Japan\'s Event.</c>'
assert len(names)==36 and len(descs)==30




