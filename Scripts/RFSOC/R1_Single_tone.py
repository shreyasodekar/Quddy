# Open the Config file
pwd = os.path.dirname(__file__)
with open(pwd + '\\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/RFSOC/' + str(config['Device Name'])
expname = 'R1_Single_tone'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

expt_cfg = {'start': 8176,
            'stop': 8181,
            'points': 500
            }

x_pts = np.linspace(expt_cfg['start'],expt_cfg['stop'],expt_cfg['points'])
data = generate_empty_nan_array(len(x_pts),0)

# Save data.
f = h5py.File(path+'/'+filename, 'a', libver='latest')
f.create_dataset('Metadata', data = json.dumps(config, indent = 4))
f.create_dataset('Frequency', data = x_pts)
f.create_dataset('S21', data = data)
f.swmr_mode = True

switch.channels[0].switch(2)
switch.channels[1].switch(2)
# ivvi._set_dac(10, config['V_gate']['2'])
# ivvi._set_dac(11, config['V_gate']['5'])
ivvi._set_dac(12, config['V_gate']['4']/5)
# ivvi._set_dac(13, config['V_gate']['5'])
# print('V_g2 = '+str(ivvi._get_dac(10))+ ' mV')
# time.sleep(1)

#Actual Measurement
for x in tqdm(range(len(x_pts))):
    config['resonator']['frequency'] = x_pts[x]
    prog = Programs.SingleTone(soccfg, config)
    # prog = Programs.ConstantPulseProbe(soccfg, config)
    avgi, avgq = prog.acquire(soc, progress=False)
    data[x] = avgi[0][0]+1j*avgq[0][0]
    f['S21'][:] = data
        
# popt, pcov = curve_fit(fitter.lorentzian, x_pts, 10*np.log10(np.abs(data)), p0=[x_pts[np.argmin(np.abs(data))], -5, -40, 1] )
# # popt, pcov = curve_fit(fitter.lorentzian, x_pts, np.abs(data), p0=[x_pts[np.argmin(np.abs(data))], -0.8, -0.2, 2] )

# resonator = shunt.LinearShuntFitter(frequency=x_pts, data=data,
#                               background_model=background.MagnitudeSlopeOffsetPhaseDelay())
# print(r"The resonance frequency is f_r = {:.6e}".format(resonator.resonance_frequency))
# print("The internal quality factor is Q_i = {:.0f}".format(resonator.Q_i))
# print("The total quality factor is Q_c = {:.0f}".format(resonator.Q_c))
# print("The total quality factor is Q_t = {:.0f}".format(resonator.Q_t))

# Plot results
fig = plt.figure(figsize=(16,6))
plt.subplot(121,title="Resonator Spectroscopy", xlabel="Frequency (MHz)", ylabel="Amp. (adc level)")
plt.plot(x_pts, np.log10(np.abs(data))*20)
# plt.plot(x_pts, np.abs(data),'.-')
# plt.plot(x_pts, fitter.lorentzian(x_pts, popt[0], popt[1], popt[2], popt[3]))
fig.text(0.6, 0,'Metadata: \n \n'+json.dumps(config, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '{}"'}) , fontsize=10)
plt.savefig(path+'/'+filename.strip('.h5')+'.png')
plt.show()
print(x_pts[np.argmin(np.log10(np.abs(data))*10)])
# print('Resonator frequency is ' + str(popt[0]) + ' MHz' )
# print('FWHM is '+ str(abs(popt[3])) + ' MHz')

# Save to docx
savedoc = input('Save to Doc file? [y]/n : ')
if savedoc == 'y' or savedoc == '':
    picture = selection.InlineShapes.AddPicture(path+'/'+filename.strip('.h5')+'.png')
    picture.Width = 500 #648 
    picture.Height = 187.5 #243 
    word.Selection.TypeText("\n")
doc.Save()

f.close()
