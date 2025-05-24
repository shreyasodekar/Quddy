# Open the Config file
pwd = os.path.dirname(__file__)
with open(pwd + '\\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/RFSOC/' + str(config['Device Name'])
expname = 'R1_1_Single_tone_powerdep'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

expt_cfg = {'start': 5715,
            'stop': 5735,
            'points': 400
            }

gain_cfg = {'start': 100,
            'stop': 5000,
            'step': 100
            }

x_pts = np.linspace(expt_cfg['start'],expt_cfg['stop'],expt_cfg['points'])
y_pts = np.arange(gain_cfg['start'],gain_cfg['stop'],gain_cfg['step'], dtype = 'float64')
data = generate_empty_nan_array(len(y_pts),len(x_pts))
snapshot = generate_empty_snapshot_array(len(y_pts),len(x_pts))

# Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config, indent = 4))
f.create_dataset('Frequency', data = x_pts)
f.create_dataset('Power', data = y_pts)
f.create_dataset('S21', data = data)
f.create_dataset('Fridge snapshot', data = snapshot)
f.swmr_mode = True
    
y_pts = np.arange(gain_cfg['start'],gain_cfg['stop'],gain_cfg['step'])


switch.channels[0].switch(2)
switch.channels[1].switch(2)
#Actual Measurement
for y in tqdm(range(len(y_pts))):
    config['resonator']['gain'] = y_pts[y].item()
    for x in range(len(x_pts)):
        config['resonator']['frequency'] = x_pts[x]
        prog = Programs.SingleTone(soccfg, config)
        avgi, avgq = prog.acquire(soc, progress=False)
        data[y,x] = avgi[0][0]+1j*avgq[0][0]
        f['S21'][:] = data
        snapshot[y,x] = get_fridge_snapshot(Proteox)
        f['Fridge snapshot'] = snapshot

# Plot results. Need to add fitting functions.
fig = plt.figure(figsize=(16,6))
plt.subplot(121,title="Resonator Spectroscopy - Power Dependence", xlabel="Frequency (MHz)", ylabel="Gain")
plt.pcolormesh(x_pts, y_pts, np.abs(data))
plt.colorbar()
fig.text(0.6, 0,'Metadata: \n \n'+json.dumps(config, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '{}"'}) , fontsize=10)
plt.savefig(path+'/'+filename.strip('.h5')+'.png')

# Save to docx
import win32com.client as win32
word = win32.Dispatch("Word.Application")
doc = word.ActiveDocument
selection = word.Selection
savedoc = input('Save to Doc file? [y]/n : ')
if savedoc == 'y' or savedoc == '':
    picture = selection.InlineShapes.AddPicture(path+'/'+filename.strip('.h5')+'.png')
    picture.Width = 648
    picture.Height = 243
doc.Save()
