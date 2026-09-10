exec(open(r'E:\Utage Patching New\_codex_select_menu\quest_v3\probe.py').read().split('rgb=')[0])
rgb=np.stack([y+1.402*co,y-.344136*cg-.714136*co,y+1.772*cg,x[:,:,1]],axis=2)
a=Image.fromarray(np.uint8(np.clip(rgb,0,255)));bg=Image.new('RGBA',a.size,(25,25,25,255));bg.alpha_composite(a);bg.convert('RGB').save(r'E:\Utage Patching New\_codex_select_menu\quest_v3\ycbcr_test.png')
