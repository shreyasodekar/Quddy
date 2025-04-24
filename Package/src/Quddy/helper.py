#helper functions
import os 
import numpy as np
import matplotlib.pyplot as plt

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

        axs[0].scatter(ig, qg, label='g', color='b', marker='*')
        axs[0].scatter(ie, qe, label='e', color='r', marker='*')
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
        axs[1].scatter(ig_new, qg_new, label='g', color='b', marker='*')
        axs[1].scatter(ie_new, qe_new, label='e', color='r', marker='*')
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
        
    else:        
        ng, binsg = np.histogram(ig_new, bins=numbins, range = xlims)
        ne, binse = np.histogram(ie_new, bins=numbins, range = xlims)

    """Compute the fidelity using overlap of the histograms"""
    contrast = np.abs(((np.cumsum(ng) - np.cumsum(ne)) / (0.5*ng.sum() + 0.5*ne.sum())))
    tind=contrast.argmax()
    threshold=binsg[tind]
    fid = contrast[tind]
    axs[2].set_title(f"Fidelity = {fid*100:.2f}%")

    return fid, threshold, theta


def get_unique_filename(path,base_name,extension):
    counter = 0
    filename = str(base_name)+str(extension)
    while os.path.exists(path+'/'+filename):
        counter += 1
        filename = str(base_name)+"_"+str(counter)+str(extension)
    return filename
        
def generate_empty_nan_array(x, y):
    if y == 0:
        arr = np.zeros(x)+1j*np.zeros(x)
        arr = arr*np.nan
    else:    
        arr = np.zeros((x,y))+1j*np.zeros((x,y))
        arr = arr*np.nan
    return arr

def rotate_s21(data):
    imaginary_parts = np.imag(data)
    min_imag = np.min(imaginary_parts)
    max_imag = np.max(imaginary_parts)

    angles = np.linspace(0, 2 * np.pi, 360)
    variances = [np.var(np.imag(data * np.exp(-1j * angle))) for angle in angles]
    optimal_angle = angles[np.argmin(variances)]

    rotated_data = data * np.exp(-1j * optimal_angle)
    new_angle = np.angle(np.mean(rotated_data))
    if np.pi/2 < np.abs(new_angle)< np.pi:
        rotated_data = rotated_data*np.exp(1j * np.pi)
        
    return rotated_data

def f01estimate(fbare, fr, g):
    return fbare - g**2 /(fr - fbare)
