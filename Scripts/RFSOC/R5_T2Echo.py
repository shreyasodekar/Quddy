# Open the Config file
pwd = os.path.dirname(__file__)
with open(pwd + '\\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/RFSOC/' + str(config['Device Name'])
expname = 'R5_T2Echo'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

config['qubit']['sync_time'] = 0.05
config['qubit']['echo_time'] = 1

expt_cfg = {'start': 0,
            'stop': 0.03,
            'points': 100
            }

x_pts = np.linspace(expt_cfg['start'],expt_cfg['stop'],expt_cfg['points'])
data = generate_empty_nan_array(len(x_pts),0)
snapshot = generate_empty_snapshot_array(len(x_pts),0)

# Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config, indent = 4))
f.create_dataset('Frequency', data = x_pts)
f.create_dataset('S21', data = data)
f.create_dataset('Fridge snapshot', data = snapshot)
f.swmr_mode = True

switch.channels[0].switch(2)
switch.channels[1].switch(2)
#Actual Measurement
for x in tqdm(range(len(x_pts))):
    config['qubit']['dephase_time'] = x_pts[x]
    prog = Programs.HahnEcho(soccfg, config)
    avgi, avgq = prog.acquire(soc, progress=False)
    data[x] = avgi[0][0]+1j*avgq[0][0]
    f['S21'][:] = data
    snapshot[x] = get_fridge_snapshot(Proteox)
    f['Fridge snapshot'] = snapshot

data  = rotate_s21(data)

# Plot results.
fig = plt.figure(figsize=(16,6))
plt.subplot(121,title=r"T2 Hahn Echo", xlabel=r"$\tau$ ($\mu$s)", ylabel="Amp. (adc level)")
plt.plot(x_pts, data.real, '.-')
fig.text(0.6, 0,'Metadata: \n \n'+json.dumps(config, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '{}"'}) , fontsize=10)
plt.savefig(path+'/'+filename.strip('.h5')+'.png')
plt.show()

# Save to docx
savedoc = input('Save to Doc file? [y]/n : ')
if savedoc == 'y' or savedoc == '':
    picture = selection.InlineShapes.AddPicture(path+'/'+filename.strip('.h5')+'.png')
    picture.Width = 500 #648 
    picture.Height = 187.5 #243 
doc.Save()
