# Open the Config file
pwd = os.path.dirname(__file__)
with open(pwd + '\\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/' +str(config['Device Name']) +  '/CW/'
expname = 'C3_Three_tone'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

expt_cfg = {'resonator_frequency' : 7.551656765e+09,  ## This should be the resonator frequency at |e>
            'f01': 3.3065655e9,
            'start': 3.15e9,
            'stop': 3.22e9,
            'points': 200
            }

x_pts = set_sweep(config, expt_cfg['start'], expt_cfg['stop'], expt_cfg['points'])

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
pna.group_trigger_count(config['pna']['averages'])

mxg.power(config['mxg']['power'])
sc.power(config['sc']['power'])


data = generate_empty_nan_array(len(x_pts),0)
# snapshot = generate_empty_snapshot_array(len(x_pts),0)

# Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config, indent = 4))
f.create_dataset('Frequency', data = x_pts)
f.create_dataset('S21', data = data)
# f.create_dataset('Fridge snapshot', data = snapshot)
f.swmr_mode = True

pna.output(1)
mxg.rf_output(1)
sc.output_status(1)

sc.frequency(expt_cfg['f01'])

for x in tqdm(range(len(x_pts))):
    mxg.frequency(x_pts[x]) 
    temp = pna.polar()
    data[x] = np.mean(temp)
    f['S21'][:] = data
    time.sleep(0.01)   
    # snapshot[x] = get_fridge_snapshot(Proteox)
    # f['Fridge snapshot'] = snapshot

pna.output(0)
mxg.rf_output(0)
sc.output_status(0)
pna.sweep_mode("CONT")

if show_plot:
    # Plot 
    popt, pcov = curve_fit(fitter.lorentzian, x_pts, 20*np.log10(np.abs(data)), p0=[x_pts[np.argmax(20*np.log10(np.abs(data)))], -30, 10, 1e6])
    fig = plt.figure(figsize=(16,6))
    plt.subplot(121, title="Three Tone", xlabel="Frequency (GHz)", ylabel="Magnitude (dB)")
    plt.plot(x_pts, 20*np.log10(np.abs(data)))
    plt.plot(x_pts, fitter.lorentzian(x_pts, popt[0], popt[1], popt[2], popt[3]))
    plt.grid()
    fig.text(0.6, 0,'Metadata: \n \n'+json.dumps(config, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '[]{}"'}) , fontsize=10)
    plt.savefig(path+'/'+filename.split('.')[0]+'.png')
    plt.show()
    print('f_ef is ' + str(popt[0]/1e9) + ' GHz')
    print('FWHM is ' + str(np.abs(popt[3])/1e6) + ' MHz')
    
    if ask_save_to_doc:
        # Save to docx
        savedoc = input('Save to Doc file? [y]/n : ')
        if savedoc == 'y' or savedoc == '':
            word.Selection.TypeText("\n")
            picture = selection.InlineShapes.AddPicture(path+'/'+filename.strip('.h5')+'.png')
            picture.Width = 500 #648
            picture.Height = 187.5 #243
        doc.Save()
f.close()
