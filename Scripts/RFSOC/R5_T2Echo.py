# Pulse sequence
# Q---|Rx(pi/2)|---tau---|Rx{pi}|---tau---|Rx(pi/2)|----------
# R--------------------------------------------------|Measure|
# tau is being sweept

Use_Raverager = False

# Open the Config file
pwd = os.path.dirname(__file__)
with open(pwd + '\\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/' +str(config['Device Name']) +  '/RFSOC/'
expname = 'R5_T2Echo'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

config['qubit']['sync_time'] = 0.05
config['qubit']['dephase_time'] = 1

expt_cfg = {'start': 0,
            'stop': 800,
            'points': 100
            }

x_pts = helper.set_sweep(config, expt_cfg['start'], expt_cfg['stop'], expt_cfg['points'])
data = generate_empty_nan_array(len(x_pts),0)
# snapshot = generate_empty_snapshot_array(len(x_pts),0)

# Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config, indent = 4))
f.create_dataset('Time', data = x_pts)
f.create_dataset('S21', data = data)
# f.create_dataset('Fridge snapshot', data = snapshot)
f.swmr_mode = True

switch.channels[0].switch(2)
switch.channels[1].switch(2)

# Actual Measurement
if Use_Raverager:
    prog = HahnEchoProgram(soccfg, config)
    _, avgi, avgq = prog.acquire(soc, progress=False)
    data = avgi[0][0]+1j*avgq[0][0]
    f['S21'][:] = data
    # snapshot[:] = get_fridge_snapshot(Proteox)
    # f['Fridge snapshot'] = snapshot
else:
    for x in tqdm(range(len(x_pts))):
        config['qubit']['dephase_time'] = x_pts[x]
        prog = Programs.HahnEcho(soccfg, config)
        avgi, avgq = prog.acquire(soc, progress=False)
        data[x] = avgi[0][0]+1j*avgq[0][0]
        f['S21'][:] = data
        # snapshot[x] = get_fridge_snapshot(Proteox)
        # f['Fridge snapshot'] = snapshot

if show_plot:
    # Plot results.
    data  = rotate_s21(data)
    popt , pcov = curve_fit(fitter.Tdecay,x_pts + config['qubit']['pulse_length'], data.real, p0 = [0, 2, 200])  #us
    fig = plt.figure(figsize=(16,6))
    plt.subplot(121,title=r"T2 Hahn Echo", xlabel=r"Time ($\mu$s)", ylabel="Amp. (adc level)")
    plt.plot(x_pts + config['qubit']['pulse_length'], data.real, '.-')
    plt.plot(x_pts + config['qubit']['pulse_length'],fitter.Tdecay(x_pts + config['qubit']['pulse_length'], popt[0], popt[1], popt[2]), label='Fit')
    fig.text(0.6, 0,'Metadata: \n \n'+json.dumps(config, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '{}"'}) , fontsize=10)
    plt.savefig(path+'/'+filename.split('.')[0]+'.png')
    plt.show()
    print('T2echo is ' + str(popt[2]) + ' us' )

    
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
