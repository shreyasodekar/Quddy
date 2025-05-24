# Open the Config file
pwd = os.path.dirname(__file__)
with open(pwd + '\\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/CW/' + str(config['Device Name'])
expname = 'C2_Two_tone'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

expt_cfg = {'start': 3.9e9,
            'stop': 4e9,
            'points': 300
            }

x_pts = np.linspace(expt_cfg['start'],expt_cfg['stop'],expt_cfg['points'])

switch.channels[0].switch(1)
switch.channels[1].switch(1)
pna.trace("S21")
pna.power(config['pna']['power'])
pna.start(expt_cfg['resonator_frequency'])
pna.stop(expt_cfg['resonator_frequency'])
pna.points(100)
pna.if_bandwidth(config['pna']['if_bandwidth'])
pna.averages_enabled(True)
pna.averages(config['pna']['averages'])

mxg.power(config['mxg']['power'])

meas = Measurement()
meas.register_parameter(pna.polar)

data = generate_empty_nan_array(len(x_pts),0)
snapshot = generate_empty_snapshot_array(len(x_pts),0)

# Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config, indent = 4))
f.create_dataset('Frequency', data = x_pts)
f.create_dataset('S21', data = data)
f.create_dataset('Fridge snapshot', data = snapshot)
f.swmr_mode = True

ivvi._set_dac(12,config['V_gate']['4']/5)
time.sleep(5)
pna.output(1)

for x in tqdm(range(len(x_pts))):
    mxg.frequency(x_pts[x])
    mxg.rf_output(1)
    temp = pna.polar()
    data[x] = np.mean(temp)
    f['S21'][:] = data
    mxg.rf_output(0)
    time.sleep(0.1)   
    snapshot[x] = get_fridge_snapshot(Proteox)
    f['Fridge snapshot'] = snapshot

pna.output(0)
pna.sweep_mode("CONT")

popt, pcov = curve_fit(fitter.lorentzian, x_pts, 10*np.log10(np.abs(data)), p0=[(expt_cfg['start']+expt_cfg['stop'])/2, -30, 10, 1e6])

# Plot 
fig = plt.figure(figsize=(16,6))
plt.subplot(121, title="Two Tone", xlabel="Frequency (GHz)", ylabel="Magnitude (dB)")
plt.plot(x_pts, 20*np.log10(np.abs(data)))
plt.plot(x_pts, fitter.lorentzian(x_pts, popt[0], popt[1], popt[2], popt[3]))
plt.grid()
fig.text(0.6, 0,'Metadata: \n \n'+json.dumps(config, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '[]{}"'}) , fontsize=10)
plt.savefig(path+'/'+filename.strip('.h5')+'.png')
plt.show()
print('Qubit frequency is ' + str(popt[0]/1e9) + ' GHz')
print('FWHM is ' + str(np.abs(popt[3])/1e6) + ' MHz')

# Save to docx
savedoc = input('Save to Doc file? [y]/n : ')
if savedoc == 'y' or savedoc == '':
    picture = selection.InlineShapes.AddPicture(path+'/'+filename.strip('.h5')+'.png')
    picture.Width = 500 #648 
    picture.Height = 187.5 #243 
    word.Selection.TypeText("\n")
doc.Save()
f.close()
