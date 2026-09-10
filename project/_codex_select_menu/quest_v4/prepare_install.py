from pathlib import Path
v3=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v3');v4=v3.parent/'quest_v4'
s=(v3/'package_and_install.py').read_text().replace('V3','V4').replace('v3','v4').replace('Utage_Menu_V4_CHARASELE_AND_REWARDS_ROOT_READY.zip','Utage_Menu_V4_STARTUP_AND_CLEAN_TEXTURES_ROOT_READY.zip')
s=s.replace("assert target.is_relative_to(ROOT/'PS3_GAME/USRDIR/nativePS3/rom/eng');", "assert target.is_relative_to(ROOT/'PS3_GAME/USRDIR/nativePS3/rom/eng') or target==ROOT/'PS3_GAME/USRDIR/nativePS3/rom/battleQuest.arc';")
(v4/'package_and_install_v4.py').write_text(s)
