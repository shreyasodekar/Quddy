# Open the Config file
pwd = os.path.dirname(__file__)
with open(pwd + '\\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/CW/' + str(config['Device Name'])
expname = 'C1_Single_tone'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

expt_cfg = {'start': 8.1e9,
            'stop': 8.2e9,
            'points': 30
            }

x_pts = np.linspace(expt_cfg['start'],expt_cfg['stop'],expt_cfg['points'])

switch.channels[0].switch(1)
switch.channels[1].switch(1)
pna.trace("S21")
pna.power(config['pna']['power'])
pna.start(expt_cfg['start'])
pna.stop(expt_cfg['stop'])
pna.points(expt_cfg['points'])
pna.if_bandwidth(config['pna']['if_bandwidth'])
pna.averages_enabled(True)
pna.averages(config['pna']['averages'])

meas = Measurement()
meas.register_parameter(pna.polar)
ivvi._set_dac(12,config['V_gate']['4']/5)
time.sleep(5)

# mxg.frequency(4.276330732469043e9)
# mxg.rf_output(1)
# time.sleep(5)
pna.output(1)
data = pna.polar()
pna.output(0)
# mxg.rf_output(0)
snapshot = get_fridge_snapshot(Proteox)
pna.sweep_mode("CONT")

# Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config, indent = 4))
f.create_dataset('Frequency', data = x_pts)
f.create_dataset('S21', data = data)
f.create_dataset('Fridge snapshot', data = snapshot)
f.swmr_mode = True

# resonator = shunt.LinearShuntFitter(frequency=x_pts, data=data,
#                               background_model=background.MagnitudeSlopeOffsetPhaseDelay())
# print(r"The resonance frequency is f_r = {:.6e}".format(resonator.resonance_frequency))
# print("The internal quality factor is Q_i = {:.0f}".format(resonator.Q_i))
# print("The coupling quality factor is Q_c = {:.0f}".format(resonator.Q_c))
# print("The total quality factor is Q_t = {:.0f}".format(resonator.Q_t))

popt, pcov = curve_fit(fitter.lorentzian, x_pts, 10*np.log10(np.abs(data)), p0=[x_pts[np.argmin(np.log10(np.abs(data))*10)], -15, -10, 1e6] )

# Plot 
fig = plt.figure(figsize=(16,6))
plt.subplot(121, title="Single Tone", xlabel="Frequency (GHz)", ylabel="Magnitude (dB)")
plt.plot(x_pts, 10*np.log10(np.abs(data)))
plt.plot(x_pts, fitter.lorentzian(x_pts, popt[0], popt[1], popt[2], popt[3]))
plt.grid()
fig.text(0.6, 0,'Metadata: \n \n'+json.dumps(config, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '[]{}"'}) , fontsize=10)
plt.savefig(path+'/'+filename.strip('.h5')+'.png')
plt.show()
print('Resonator frequency is ' + str(popt[0]/1e9) + 'GHz')
print('FWHM is ' + str(np.abs(popt[3])/1e6) + 'MHz')

# Save to docx
savedoc = input('Save to Doc file? [y]/n : ')
if savedoc == 'y' or savedoc == '':
    picture = selection.InlineShapes.AddPicture(path+'/'+filename.strip('.h5')+'.png')
    picture.Width = 500 #648 
    picture.Height = 187.5 #243 
    word.Selection.TypeText("\n")

doc.Save()

f.close()
