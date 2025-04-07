# Open the Config file
with open(r'C:\Users\frolovlab\Documents\Python Scripts\msmt\RFSOC\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/RFSOC/' + str(config['Device Name'])
expname = 'R4_2_Chevron'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

expt_cfg = {'t_start': 4,
            't_stop': 400,
            't_points': 100,
            'f_start': 8640,
            'f_stop': 8660,
            'f_points': 50
            }

x_pts = np.linspace(expt_cfg['f_start'],expt_cfg['f_stop'],expt_cfg['f_points'])
y_pts = np.linspace(expt_cfg['t_start'],expt_cfg['t_stop'],expt_cfg['t_points'])
data = generate_empty_nan_array(len(y_pts),len(x_pts))

# Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config, indent = 4))
f.create_dataset('Frequency', data = x_pts)
f.create_dataset('Power', data = y_pts)
f.create_dataset('S21', data = data)
f.swmr_mode = True
    
switch.channels[0].switch(2)
switch.channels[1].switch(2)
#Actual Measurement
for x in tqdm(range(len(x_pts))):
    config['qubit']['frequency'] = x_pts[x]
    for y in range(len(y_pts)):
        config['qubit']['pulse_length'] = y_pts[y]
        prog = Programs.ConstantPulseProbe(soccfg, config)
        # config['qubit']['sigma'] = y_pts[y]
        # prog = Programs.GaussianPulseProbe(soccfg, config)
        avgi, avgq = prog.acquire(soc, progress=False)
        data[y,x] = avgi[0][0]+1j*avgq[0][0]
        f['S21'][:] = data

# Plot results.
fig = plt.figure(figsize=(16,6))
plt.subplot(121,title="Chevron Plot", xlabel="Frequency (MHz)", ylabel="Pulse length (clock ticks)")
pc = plt.pcolormesh(x_pts, y_pts, data.real)
fig.colorbar(pc)
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
