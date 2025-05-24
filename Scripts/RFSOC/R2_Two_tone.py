# Open the Config file
pwd = os.path.dirname(__file__)
with open(pwd + '\\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/RFSOC/' + str(config['Device Name'])
expname = 'R2_Two_tone'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

expt_cfg = {'start': 3300,
            'stop': 3800,
            'points': 250
            }

x_pts = np.linspace(expt_cfg['start'],expt_cfg['stop'],expt_cfg['points'])
data = generate_empty_nan_array(len(x_pts),0)
snapshot = generate_empty_snapshot_array(len(x_pts),0)

# Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config))
f.create_dataset('Frequency', data = x_pts)
f.create_dataset('S21', data = data)
f.create_dataset('Fridge snapshot', data = snapshot)
f.swmr_mode = True

switch.channels[0].switch(2)
switch.channels[1].switch(2)
# ivvi._set_dac(10, config['V_gate']['2'])
# ivvi._set_dac(11, config['V_gate']['5'])
# ivvi._set_dac(12, config['V_gate']['4']/5)
# ivvi._set_dac(13, config['V_gate']['5'])
# print(ivvi._get_dac(10))
# time.sleep(5)

#Actual Measurement
for x in tqdm(range(len(x_pts))):
    config['qubit']['frequency'] = x_pts[x]
    prog = Programs.ConstantPulseProbe(soccfg, config)
    # prog = Programs.GaussianPulseProbe(soccfg, config)
    avgi, avgq = prog.acquire(soc, progress=False)
    data[x] = avgi[0][0]+1j*avgq[0][0]
    f['S21'][:] = data
    snapshot[x] = get_fridge_snapshot(Proteox)
    f['Fridge snapshot'] = snapshot

data = rotate_s21(data)
popt, pcov = curve_fit(fitter.lorentzian, x_pts, data.real, p0=[x_pts[np.argmax(data.real)], 0.3, 0.1, 3] )

# Plot results.
fig = plt.figure(figsize=(16,6))
plt.subplot(121,title="Pulse Probe Spectroscopy", xlabel="Frequency (MHz)", ylabel="Amp. (adc level)")
plt.plot(x_pts, data.real,'.-')
# plt.plot(x_pts, data.imag,'.')
plt.plot(x_pts, fitter.lorentzian(x_pts, popt[0], popt[1], popt[2], popt[3]))
fig.text(0.6, 0,'Metadata: \n \n'+json.dumps(config, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '{}"'}) , fontsize=10)
plt.savefig(path+'/'+filename.strip('.h5')+'.png')
plt.show()
print('Qubit frequency is ' + str(popt[0]) + ' MHz' )
print('FWHM is '+ str(np.abs(popt[3])) + ' MHz')


# Save to docx
savedoc = input('Save to Doc file? [y]/n : ')
if savedoc == 'y' or savedoc == '':
    picture = selection.InlineShapes.AddPicture(path+'/'+filename.strip('.h5')+'.png')
    picture.Width = 500 #648 
    picture.Height = 187.5 #243 
    word.Selection.TypeText("\n")
doc.Save()

f.close()
