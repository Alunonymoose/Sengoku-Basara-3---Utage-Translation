NAMES=[
'Steady Flute','Dragon Gloves','Parry Guard','Divine Blade','Alarm Bell','Phantom Socks','Pursuit Reins','Time Whip','Wild Horse','Last Stand',
'Frail Mask','Revenge Blade','Dark Glasses','Glory Cup','Victory Cup',"Smith's Hammer",'Gold Hammer','Uesugi Salt','Easy Money','Time Trick',
'Launch Paddle',"Fool's Screen",'Training Sword','Wanted Notice','Flattery Rod','Cheering Wig','Oshu Mailbox','Elder Flask','Sweet Parasol','Gamble Pill',
'Singing Biwa','Singing koto','Solo Drum','Support Flute','Record Player','Exile Comb']
DESCRIPTIONS=[
'Arrows and bullets no longer make you stagger.',
'Automatically reflects arrows and bullets while guarding.',
'Slightly extends the timing window for parrying.',
'Win weapon clashes more easily and recover health on victory.\nNo effect in two-player mode.',
'Prevents stunning, no matter how many attacks you take.',
'Take no damage during an evasive step.',
'Adds 1 to the hit count while on horseback.',
'On horseback, combos continue until you take damage.',
'Increases attack power while on horseback.',
'Start battle near death, but add 1 to the EXP multiplier.',
'Adds 3 to the coin multiplier, but health drains gradually.',
'Attack power rises with each enemy defeated during the battle.',
'Hides the health gauge, but adds 0.5 to the EXP multiplier.',
'Doubles the EXP gained from special rewards.\nNo effect in Japan\'s Event.',
'Adds 0.2 to the EXP multiplier.\nIf both players equip it, the bonus becomes 2.',
'Weapon rewards are one level above your equipped weapon.\nNo effect in Japan\'s Event.',
'Every 100 defeats, a lucky hammer appears instead of rice.',
'Doubles all enemy health, but increases EXP from defeating them.',
'Adds 4 to the coin multiplier, but taking damage halves funds.',
'Sword, shield and hammer power-ups last 10 seconds longer.',
'Launch attacks send enemies flying much farther.',
'Your ally stops following you and stops using BASARA Assist.\nNo effect in two-player mode.',
'Start battle with all stat boosts from resources disabled.',
'Reveals fugitives. Both players equipping raises spawn chance.\nNo effect in Japan\'s Event.',
'Allied soldiers flatter you with pleasing words.',
'Allied soldiers offer awkward encouragement that saps morale.',
'Listen to the popular Oshu Mailbox show during battle.',
'Allied soldiers start a party with girls during battle.',
'A stern but kind girl keeps talking to you during battle.',
'If luck is on your side, you can revive after losing all health.',
'Changes the stage music to UTAGE.',
'Changes the stage music to Twilight.',
'Changes the stage music to the equipped warrior\'s theme.',
'Changes the stage music to your accompanying ally\'s theme.\nNo effect in two-player mode.',
'Changes the stage music to the last track played in Gallery.',
'Swaps the effects of equipped gray and gold accessories.'
]
assert len(NAMES)==len(DESCRIPTIONS)==36
TRANSLATIONS={288+i:n for i,n in enumerate(NAMES)}|{496+i:n for i,n in enumerate(DESCRIPTIONS)}
RED_RECORDS={499,509,511,517,519,529}

