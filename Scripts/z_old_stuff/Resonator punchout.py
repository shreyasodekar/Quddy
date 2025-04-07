# -*- coding: utf-8 -*-
"""
Created on Sun Dec  1 15:49:29 2024

@author: frolovlab
"""
import numpy as np
import matplotlib.pyplot as plt
import h5py
import json
from pprint import pprint

path = os.path.abspath('./Data/')
expname = 'E1_Single_tone'

f1 = h5py.File('./Data/E1_Single_tone_4.h5','r')
f2 = h5py.File('./Data/E1_Single_tone_5.h5','r')
# f3 = h5py.File('./Data/E1_Single_tone_27.h5','r')
# f1 = h5py.File('./Data/E1_Single_tone_spectroscopy_35.h5','r')
# f2 = h5py.File('./Data/E1_Single_tone_spectroscopy_34.h5','r')
# f3 = h5py.File('./Data/E1_Single_tone_spectroscopy_14.h5','r')
x_pts = f1['Frequency'][:]
y1 = f1['S21'][:]
y2 = f2['S21'][:]    
# y3 = f3['S21'][:]    
f1.close()
f2.close()
# f3.close()

#Plot your previously saved data
fig = plt.figure(figsize=(8,6), dpi = 300)
# plt.title('Resonator punchout - All')
plt.title('Punch out')
plt.plot(x_pts/1e9, 10*np.log10(np.abs(y1)), '-', linewidth = 1, label = '-40 dBm')
plt.plot(x_pts/1e9, 10*np.log10(np.abs(y2)), '-', linewidth = 1, label = '20 dBm')
# plt.plot(x_pts/1e9, 20*np.log10(np.abs(y3)), '-', linewidth = 1, label = 'punchout')
# plt.plot(x_pts/1e9, np.abs(y1), '-', linewidth = 1, label = '|g>')
# plt.plot(x_pts/1e9, np.abs(y2), '-', linewidth = 1, label = '|e>')
# plt.plot(x_pts/1e9, np.abs(y3)/80-0.01, '-', linewidth = 1, label = 'punchout (scaled)')
plt.xlabel('Frequency')
plt.ylabel('Magnitude (dB)')
plt.legend()

# plt.legend()
# # plt.title('This is how you get back stored data from hdf5 files.')
# # plt.show()

# x_pts[np.argmax(i_vals)]
