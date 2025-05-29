# Open the Config file
pwd = os.path.dirname(__file__)
with open(pwd + '\\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/' +str(config['Device Name']) +  '/RFSOC/'
expname = 'R0_TOF'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

config['reps'] = 1
config['soft_avgs'] = 1000

switch.channels[0].switch(2)
switch.channels[1].switch(2)
prog = Programs.SingleTone(soccfg, config)
iq_list = prog.acquire_decimated(soc, progress=True)
data = iq_list[0][0]+1j*iq_list[0][1]
x_pts = prog.get_time_axis(0)
snapshot = get_fridge_snapshot(Proteox)

# Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config, indent = 4))
f.create_dataset('Time', data = x_pts)
f.create_dataset('S21', data = data)
f.create_dataset('Fridge snapshot', data = snapshot)
f.swmr_mode = True

# Plot results.
fig = plt.figure(figsize=(16,6))
plt.subplot(121, title="TOF", xlabel="Clock ticks", ylabel="Transmission (adc levels)")
plt.plot(data.real, label="I value")
plt.plot(data.imag, label="Q value")
# plt.plot(20*np.log10(np.abs(data)))
# plt.legend()
# plt.axvline(config["adc_trig_offset"])
fig.text(0.6, 0,'Metadata: \n \n'+json.dumps(config, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '[]{}"'}) , fontsize=10)
plt.savefig(path+'/'+filename.split('.')[0]+'.png')
plt.show()
print(np.angle(np.mean(data))*180/np.pi)

# Save to docx
savedoc = input('Save to Doc file? [y]/n : ')
if savedoc == 'y' or savedoc == '':
    picture = selection.InlineShapes.AddPicture(path+'/'+filename.strip('.h5')+'.png')
    picture.Width = 500 #648 
    picture.Height = 187.5 #243 
doc.Save()

f.close()
