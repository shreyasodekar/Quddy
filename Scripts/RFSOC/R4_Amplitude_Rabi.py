# Open the Config file
with open(r'C:\Users\frolovlab\Documents\Python Scripts\msmt\RFSOC\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/RFSOC/' + str(config['Device Name'])
expname = 'R4_Amplitude_Rabi'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

expt_cfg = {'start': 0,
            'stop': 10000,
            'step': 100
            }

x_pts = np.arange(expt_cfg['start'],expt_cfg['stop'],expt_cfg['step'], dtype = 'float64')
data = generate_empty_nan_array(len(x_pts),0)

# Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config, indent = 4))
f.create_dataset('Frequency', data = x_pts)
f.create_dataset('S21', data = data)
f.swmr_mode = True
    
x_pts = np.arange(expt_cfg['start'],expt_cfg['stop'],expt_cfg['step'])

switch.channels[0].switch(2)
switch.channels[1].switch(2)
#Actual Measurement
for x in tqdm(range(len(x_pts))):
    config['qubit']['gain'] = x_pts[x].item()
    # prog = Programs.ConstantPulseProbe(soccfg, config)
    prog = Programs.GaussianPulseProbe(soccfg, config)
    avgi, avgq = prog.acquire(soc, progress=False)
    data[x] = avgi[0][0]+1j*avgq[0][0]
    f['S21'][:] = data

data = rotate_s21(data)
popt, pcov = curve_fit(fitter.sinedecay, x_pts, data.real, p0=[0, 0.01, 1, 30, 0])

# Plot results.
fig = plt.figure(figsize=(16,6))
plt.subplot(121,title="Amplitude Rabi", xlabel="Gain (a.u.)", ylabel="Amp. (adc level)")
# plt.plot(x_pts, data.imag,'.-')
plt.plot(x_pts, data.real,'.-')
plt.plot(x_pts,fitter.sinedecay(x_pts, popt[0], popt[1], popt[2], popt[3], popt[4]), label='Fit')
fig.text(0.6, 0,'Metadata: \n \n'+json.dumps(config, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '{}"'}) , fontsize=10)
plt.savefig(path+'/'+filename.strip('.h5')+'.png')
plt.show()
print(r'$\pi$-pulse Gain @ length = ' + str(config['qubit']['pulse_length']) + ' is ' + str((np.pi*popt[2] + popt[4]/popt[2])/2) + 'DAC units')
print(r'$\pi/2$-pulse Gain @ Length = ' + str(config['qubit']['pulse_length']) + ' is ' + str((np.pi*popt[2] + popt[4]/popt[2])/4) + 'DAC units')

# Save to docx
savedoc = input('Save to Doc file? [y]/n : ')
if savedoc == 'y' or savedoc == '':
    picture = selection.InlineShapes.AddPicture(path+'/'+filename.strip('.h5')+'.png')
    picture.Width = 500 #648 
    picture.Height = 187.5 #243 
doc.Save()