# Open the Config file
pwd = os.path.dirname(__file__)
with open(pwd + '\\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/CW/' + str(config['Device Name'])
expname = 'C2_2_Two_tone_gatedep'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

expt_cfg = {'resonator_frequency': 8.15223589097666e9,
            'f_start': 3.2e9,
            'f_stop': 4.8e9,
            'f_points': 10,
            'v_start': 1900,
            'v_stop': 2100,
            'v_points' : 5
            }

x_pts = np.linspace(expt_cfg['f_start'],expt_cfg['f_stop'],expt_cfg['f_points'])
y_pts = np.linspace(expt_cfg['v_start'],expt_cfg['v_stop'],expt_cfg['v_points'])

switch.channels[0].switch(1)
switch.channels[1].switch(1)
pna.trace("S21")
pna.power(config['pna']['power'])
mxg.power(config['mxg']['power'])

data = generate_empty_nan_array(len(y_pts), len(x_pts))
snapshot = generate_empty_nan_array(len(y_pts), len(x_pts))

# # Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config, indent = 4))
f.create_dataset('Frequency', data = x_pts)
f.create_dataset('Power', data = y_pts)
f.create_dataset('S21', data = data)
f.create_dataset('Fridge snapshot', data = snapshot)
f.swmr_mode = True

for y in tqdm(range(len(y_pts))):
    ivvi._set_dac(12, y_pts[y]/5)
    time.sleep(2)
    ST_expt_cfg = {'start': 8.176e9,
                'stop': 8.183e9,
                'points': 801
                }
    ST_x_pts = np.linspace(ST_expt_cfg['start'],ST_expt_cfg['stop'],ST_expt_cfg['points'])
    pna.start(ST_expt_cfg['start'])
    pna.stop(ST_expt_cfg['stop'])
    pna.points(ST_expt_cfg['points'])
    pna.if_bandwidth(config['pna']['if_bandwidth'])
    pna.averages_enabled(True)
    pna.averages(100)
    meas = Measurement()
    meas.register_parameter(pna.polar)
    pna.output(1)
    ST_data = pna.polar()
    pna.output(0)
    # popt, pcov = curve_fit(fitter.lorentzian, ST_x_pts, 10*np.log10(np.abs(ST_data)), p0=[ST_x_pts[np.argmin(np.log10(np.abs(ST_data))*10)], -20, -10, 1e6] )
    # print('new resonator frequency is '+str(popt[0]/1e9) + ' GHz')
    # pna.start(popt[0] +5e3)
    # pna.stop(popt[0] +5e3)
    pna.start(ST_x_pts[np.argmin(10*np.log10(np.abs(ST_data)))])
    pna.stop(ST_x_pts[np.argmin(10*np.log10(np.abs(ST_data)))])
    pna.points(100)
    pna.averages(config['pna']['averages'])
    meas = Measurement()
    meas.register_parameter(pna.polar)
    for x in range(len(x_pts)):
        mxg.rf_output(1)
        mxg.frequency(x_pts[x])
        pna.output(1)
        temp = pna.polar()
        pna.output(0)
        mxg.rf_output(0)
        data[y,x] = np.mean(temp) 
        f['S21'][:] = data
        time.sleep(0.5)
        snapshot[y,x] = get_fridge_snapshot()
        f['Fridge snapshot'] = snapshot

pna.sweep_mode("CONT")

# PLot 
fig = plt.figure(figsize=(16,6))
plt.subplot(121, title="Two Tone - gate dependence", xlabel="Frequency (GHz)", ylabel="V_g (mV)")
plt.pcolormesh(x_pts/1e9, y_pts ,10*np.log10(np.abs(data)))
plt.colorbar()
fig.text(0.6, 0,'Metadata: \n \n'+json.dumps(config, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '[]{}"'}) , fontsize=10)
plt.savefig(path+'/'+filename.strip('.h5')+'.png')
plt.show()

# Save to docx
savedoc = input('Save to Doc file? [y]/n : ')
if savedoc == 'y' or savedoc == '':
    picture = selection.InlineShapes.AddPicture(path+'/'+filename.strip('.h5')+'.png')
    picture.Width = 500 #648 
    picture.Height = 187.5 #243 
    word.Selection.TypeText("\n")
doc.Save()

f.close()
