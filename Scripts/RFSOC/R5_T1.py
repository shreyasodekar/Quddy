# Open the Config file
pwd = os.path.dirname(__file__)
with open(pwd + '\\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/' +str(config['Device Name']) +  '/RFSOC/'
expname = 'R5_T1'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

expt_cfg = {'start': 0,
            'stop': 25,
            'points': 100
            }

x_pts = np.linspace(expt_cfg['start'],expt_cfg['stop'],expt_cfg['points'])
data = generate_empty_nan_array(len(x_pts),0)
snapshot = generate_empty_snapshot_array(len(x_pts),0)

# Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config, indent = 4))
f.create_dataset('Time', data = x_pts)
f.create_dataset('S21', data = data)
f.create_dataset('Fridge snapshot', data = snapshot)
f.swmr_mode = True

switch.channels[0].switch(2)
switch.channels[1].switch(2)
#Actual Measurement
for x in tqdm(range(len(x_pts))):
    config['qubit']['wait_time'] = x_pts[x]
    # prog = Programs.ConstantPulseProbe(soccfg, config)
    prog = Programs.GaussianPulseProbe(soccfg, config)
    avgi, avgq = prog.acquire(soc, progress=False)
    data[x] = avgi[0][0]+1j*avgq[0][0]
    f['S21'][:] = data
    snapshot[x] = get_fridge_snapshot(Proteox)
    f['Fridge snapshot'] = snapshot

data = rotate_s21(data)
popt , pcov = curve_fit(fitter.Tdecay,x_pts, data.real, p0 = [0, 2, 5])  #us

# Plot results.
fig = plt.figure(figsize=(16,6))
plt.subplot(121,title="T1", xlabel="Time (us)", ylabel="Amp. (adc level)")
plt.plot(x_pts, data.real,'.', label='I')
plt.plot(x_pts,fitter.Tdecay(x_pts, popt[0], popt[1], popt[2]), label='Fit')
fig.text(0.6, 0,'Metadata: \n \n'+json.dumps(config, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '{}"'}) , fontsize=10)
plt.savefig(path+'/'+filename.strip('.h5')+'.png')
plt.show()
print('T1 is ' + str(popt[2]) + ' us' )

# Save to docx
savedoc = input('Save to Doc file? [y]/n : ')
if savedoc == 'y' or savedoc == '':
    picture = selection.InlineShapes.AddPicture(path+'/'+filename.strip('.h5')+'.png')
    picture.Width = 500 #648 
    picture.Height = 187.5 #243 
doc.Save()
