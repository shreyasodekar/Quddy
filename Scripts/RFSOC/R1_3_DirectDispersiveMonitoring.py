# Pulse sequence
# Q ------------
# R ---|Measure|
# Measure frequency is being sweep

Use_Raverager = True

# Open the Config file
pwd = os.path.dirname(__file__)
with open(pwd + '\\config.json','r+') as f:
    config = json.load(f)

config['reps'] = 1
config['expts'] = 1000
config['start'] = 1 # dummy
config['step'] = 1  # dummy
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/' +str(config['Device Name']) +  '/RFSOC/'
expname = 'R1_3_DirectDispersiveMonitoring'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

data = generate_empty_nan_array(config['expts'],0)
# snapshot = generate_empty_snapshot_array(len(x_pts),0)

# Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config, indent = 4))
f.create_dataset('Frequency', data = x_pts)
f.create_dataset('S21', data = data)
# f.create_dataset('Fridge snapshot', data = snapshot)
f.swmr_mode = True

switch.channels[0].switch(2)
switch.channels[1].switch(2)

#Actual Measurement
if Use_Raverager:
    prog = DirectDispersiveMonitoring.DirectDispersiveMonitoring(soccfg, config)
    _, avgi, avgq = prog.acquire(soc, progress=False)
    data = avgi[0][0]+1j*avgq[0][0]
    f['S21'][:] = data
    # snapshot[:] = get_fridge_snapshot(Proteox)
    # f['Fridge snapshot'] = snapshot
        
if show_plot:
    # Plot results
    data  = rotate_s21(data)
    fig = plt.figure(figsize=(16,6))
    plt.subplot(121,title="Resonator Spectroscopy", xlabel="Time (ms)", ylabel="Amp. (adc level)")
    plt.plot(np.linspace(0, config['relax_delay']*config['expts']/1000, config['expts']), data.real)
    
    # plt.plot(data.real, data.imag,'.-')
    # plt.xlabel('asds')
    
    fig.text(0.6, 0,'Metadata: \n \n'+json.dumps(config, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '{}"'}) , fontsize=10)
    plt.savefig(path+'/'+filename.split('.')[0]+'.png')
    plt.show()
    
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
