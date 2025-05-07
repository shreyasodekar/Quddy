# Open the Config file
pwd = os.path.dirname(__file__)
with open(pwd + '\\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/CW/' + str(config['Device Name'])
expname = 'C1_1_Single_tone_powerdep'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

expt_cfg = {'f_start': 8.14e9,
            'f_stop': 8.165e9,
            'f_points': 401,
            'p_start': -43,
            'p_stop': 20,
            'p_step' : 2
            }

x_pts = np.linspace(expt_cfg['f_start'],expt_cfg['f_stop'],expt_cfg['f_points'])
y_pts = np.arange(expt_cfg['p_start'],expt_cfg['p_stop'],expt_cfg['p_step'])

switch.channels[0].switch(1)
switch.channels[1].switch(1)
pna.trace("S21")
pna.power(config['pna']['power'])
pna.start(expt_cfg['f_start'])
pna.stop(expt_cfg['f_stop'])
pna.points(expt_cfg['f_points'])
pna.if_bandwidth(config['pna']['if_bandwidth'])
pna.averages_enabled(True)
pna.averages(config['pna']['averages'])
meas = Measurement()
meas.register_parameter(pna.polar)

data = generate_empty_nan_array(len(y_pts), len(x_pts))
snapshot = generate_empty_nan_array(len(y_pts))

# Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config, indent=4))
f.create_dataset('Frequency', data = x_pts)
f.create_dataset('Power', data = y_pts)
f.create_dataset('S21', data = data)
f.create_dataset('Fridge snapshot', data = snapshot)
f.swmr_mode = True


for y in tqdm(range(len(y_pts))):
    pna.power(y_pts[y])
    pna.output(1)
    temp = pna.polar()
    data[y] = temp
    f['S21'][:] = data
    pna.output(0)
    snapshot[y] = get_fridge_snapshot()
    f['Fridge snapshot'] = snapshot

pna.sweep_mode("CONT")


# Plot 
fig = plt.figure(figsize=(16,6))
plt.subplot(121, title="Single Tone - power dependence", xlabel="Frequency (GHz)", ylabel="VNA output power (dBm)")
plt.pcolormesh(x_pts/1e9, y_pts ,10*np.log10(np.abs(data)))
plt.colorbar()
fig.text(0.6, 0,'Metadata: \n \n'+json.dumps(config, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '[]{}"'}) , fontsize=10)
plt.savefig(path+'/'+filename.strip('.h5')+'.png')
# plt.savefig(path+'/'+filename.strip('.h5')+'.svg')
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
