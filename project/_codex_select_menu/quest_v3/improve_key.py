from pathlib import Path
p=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v3\build_charasele.py')
s=p.read_text();a=s.index('master=Image.open');b=s.index('# Native UV slots')
s=s[:a]+'''from scipy import ndimage as ndi
master=Image.open(W/'menu_lettering_key.png').convert('RGBA');arr=np.array(master);r,g,b=arr[:,:,0].astype(int),arr[:,:,1].astype(int),arr[:,:,2].astype(int)
possible=(r>155)&(b>155)&(g<105)&(np.abs(r-b)<100)
seed=np.zeros(possible.shape,bool);seed[0,:]=possible[0,:];seed[-1,:]=possible[-1,:];seed[:,0]=possible[:,0];seed[:,-1]=possible[:,-1]
bg=ndi.binary_propagation(seed,mask=possible)|((r>220)&(b>220)&(g<55))
fg=~bg
lab,n=ndi.label(fg);sizes=np.bincount(lab.ravel());fg &= sizes[lab]>120
fg=ndi.binary_erosion(fg,iterations=1)
arr[:,:,3]=fg.astype('uint8')*255;arr[~fg,:3]=0;master=Image.fromarray(arr)
master.save(W/'menu_lettering_sprites.png')
''' +s[b:];p.write_text(s)
p=Path(r'E:\Utage Patching New\_codex_select_menu\quest_v3\common.py');s=p.read_text().replace("x=np.asarray(im.convert('RGBA')).astype(float);r=x[:,:,0];g=x[:,:,1];b=x[:,:,2]","x=np.asarray(im.convert('RGBA')).astype(float);x[x[:,:,3]<1,:3]=0;r=x[:,:,0];g=x[:,:,1];b=x[:,:,2]");p.write_text(s)
