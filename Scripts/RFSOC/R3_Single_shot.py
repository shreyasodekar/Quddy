# Open the Config file
pwd = os.path.dirname(__file__)
with open(pwd + '\\config.json','r+') as f:
    config = json.load(f)
config['Timestamp'] = datetime.now().strftime('%m/%d/%Y %I:%M:%S %p')

path = os.path.abspath('./Data') + '/' +str(config['Device Name']) +  '/RFSOC/'
expname = 'R3_Single_shot'
filename = get_unique_filename(path,expname, '.h5')
config['Expt ID'] = filename.strip('.h5')

egain = config['qubit']['gain']

config['reps'] = 1
expt_cfg = {'start': 3307.7432519531426,  ## MHz. Pay attention to the NQZ used in the config
            'stop': 3307.7432519531426,   ## MHz
            'points': 10000
            }

x_pts = set_sweep(config, expt_cfg['start'], expt_cfg['stop'], expt_cfg['points'])


def hist(data=None, plot=True, ran=1.0):
    
    ig = data[0]
    qg = data[1]
    ie = data[2]
    qe = data[3]

    numbins = 200
    
    xg, yg = np.median(ig), np.median(qg)
    xe, ye = np.median(ie), np.median(qe)

    if plot==True:
        fig, axs = plt.subplots(nrows=1, ncols=3, figsize=(16, 4))
        fig.tight_layout()

        axs[0].scatter(ig, qg, label='g', color='b', marker='*', alpha = 0.2)
        axs[0].scatter(ie, qe, label='e', color='r', marker='*', alpha = 0.2)
        axs[0].scatter(xg, yg, color='k', marker='o')
        axs[0].scatter(xe, ye, color='k', marker='o')
        axs[0].set_xlabel('I (a.u.)')
        axs[0].set_ylabel('Q (a.u.)')
        axs[0].legend(loc='upper right')
        axs[0].set_title('Unrotated')
        axs[0].axis('equal')
    """Compute the rotation angle"""
    theta = -np.arctan2((ye-yg),(xe-xg))
    """Rotate the IQ data"""
    ig_new = ig*np.cos(theta) - qg*np.sin(theta)
    qg_new = ig*np.sin(theta) + qg*np.cos(theta) 
    ie_new = ie*np.cos(theta) - qe*np.sin(theta)
    qe_new = ie*np.sin(theta) + qe*np.cos(theta)
    
    """New means of each blob"""
    xg, yg = np.median(ig_new), np.median(qg_new)
    xe, ye = np.median(ie_new), np.median(qe_new)
    
    #print(xg, xe)
    
    xlims = [xg-ran, xg+ran]
    ylims = [yg-ran, yg+ran]

    if plot==True:
        axs[1].scatter(ig_new, qg_new, label='g', color='b', marker='*', alpha = 0.2)
        axs[1].scatter(ie_new, qe_new, label='e', color='r', marker='*', alpha = 0.2)
        axs[1].scatter(xg, yg, color='k', marker='o')
        axs[1].scatter(xe, ye, color='k', marker='o')    
        axs[1].set_xlabel('I (a.u.)')
        axs[1].legend(loc='lower right')
        axs[1].set_title('Rotated')
        axs[1].axis('equal')

        """X and Y ranges for histogram"""
        
        ng, binsg, pg = axs[2].hist(ig_new, bins=numbins, range = xlims, color='b', label='g', alpha=0.5)
        ne, binse, pe = axs[2].hist(ie_new, bins=numbins, range = xlims, color='r', label='e', alpha=0.5)
        axs[2].set_xlabel('I(a.u.)')       
        axs[2].legend()
        
    else:        
        ng, binsg = np.histogram(ig_new, bins=numbins, range = xlims, alpha=0.5)
        ne, binse = np.histogram(ie_new, bins=numbins, range = xlims, alpha=0.5)

    """Compute the fidelity using overlap of the histograms"""
    contrast = np.abs(((np.cumsum(ng) - np.cumsum(ne)) / (0.5*ng.sum() + 0.5*ne.sum())))
    tind=contrast.argmax()
    threshold=binsg[tind]
    fid = contrast[tind]
    axs[2].set_title(f"Fidelity = {fid*100:.2f}%")

    return fid, threshold, theta

i_g = []
q_g = []

i_e = []
q_e = []

config['qubit']['gain'] = 0
prog = QubitSpectroscopyProgram(soccfg, config)
_, i_g, q_g = prog.acquire(soc, progress=False)

config['qubit']['gain'] = egain 
prog = QubitSpectroscopyProgram(soccfg, config)
_, i_e, q_e = prog.acquire(soc, progress=False)

hist(data=[i_g[0][0], q_g[0][0], i_e[0][0], q_e[0][0]], plot=True, ran=2.5)
