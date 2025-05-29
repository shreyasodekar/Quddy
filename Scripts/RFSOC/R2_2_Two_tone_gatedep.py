# Open the Config file
pwd = os.path.dirname(__file__)
with open(pwd + '\\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/' +str(config['Device Name']) +  '/RFSOC/'
expname = 'R2_2_Two_tone_gatedep'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

expt_cfg = {'start': 8550,
            'stop': 8750,
            'points': 200
            }

gate_cfg = {'start': -4500,
            'stop': 4500,
            'step': 100
            }

x_pts = np.linspace(expt_cfg['start'],expt_cfg['stop'],expt_cfg['points'])
y_pts = np.linspace(gate_cfg['start'],gate_cfg['stop'],gate_cfg['step'])
data = generate_empty_nan_array(len(y_pts),len(x_pts))
snapshot = generate_empty_snapshot_array(len(y_pts),len(x_pts))

# Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config, indent = 4))
f.create_dataset('Frequency', data = x_pts)
f.create_dataset('Gate Voltage', data = y_pts)
f.create_dataset('S21', data = data)
f.create_dataset('Fridge snapshot', data = snapshot)
f.swmr_mode = True

switch.channels[0].switch(2)
switch.channels[1].switch(2)
#Actual Measurement
for y in tqdm(range(len(y_pts))):
    ivvi._set_dac(12, y_pts[y]/5)
    for x in range(len(x_pts)):
        config['qubit']['frequency'] = x_pts[x]
        prog = Programs.ConstantPulseProbe(soccfg, config)
        # prog = Programs.GaussianPulseProbe(soccfg, config)
        avgi, avgq = prog.acquire(soc, progress=False)
        data[y,x] = avgi[0][0]+1j*avgq[0][0]
        f['S21'][:] = data
        snapshot[y,x] = get_fridge_snapshot(Proteox)
        f['Fridge snapshot'] = snapshot
            
# Plot results.
fig = plt.figure(figsize=(16,6))
plt.subplot(121,title="Pulse Probe Spectroscopy - Gate dependence", xlabel="Frequency (MHz)", ylabel="Gate Voltage (mV)")
plt.pcolormesh(x_pts, y_pts, data.real)
plt.colorbar()
fig.text(0.6, 0,'Metadata: \n \n'+json.dumps(config, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '{}"'}) , fontsize=10)
plt.savefig(path+'/'+filename.strip('.h5')+'.png')
plt.show()

# Save to docx
import win32com.client as win32
word = win32.Dispatch("Word.Application")
doc = word.ActiveDocument
selection = word.Selection
savedoc = input('Save to Doc file? [y]/n : ')
if savedoc == 'y' or savedoc == '':
    picture = selection.InlineShapes.AddPicture(path+'/'+filename.strip('.h5')+'.png')
    picture.Width = 500 #648 
    picture.Height = 187.5 #243 
    word.Selection.TypeText("\n")
doc.Save()

f.close()
