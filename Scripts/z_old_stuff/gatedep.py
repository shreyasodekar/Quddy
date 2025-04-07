# -*- coding: utf-8 -*-
"""
Created on Fri Dec 13 00:31:09 2024

@author: frolovlab
"""

import numpy as np
import matplotlib.pyplot as plt
import h5py
import json
from pprint import pprint

f1 = h5py.File('./Data/E2_1_Two_tone_gatedep.h5','r')
f2 = h5py.File('./Data/E2_1_Two_tone_gatedep_1.h5','r')
f3 = h5py.File('./Data/E2_1_Two_tone_gatedep_2.h5','r')
f4 = h5py.File('./Data/E2_1_Two_tone_gatedep_3.h5','r')

x1 = f1['Frequency'][:]
y1 = f1['Power'][:]
z1 = f1['S21'][:]

x2 = f2['Frequency'][:]
y2 = f2['Power'][:]
z2 = f2['S21'][:]    

x3 = f3['Frequency'][:]
y3 = f3['Power'][:]
z3 = f3['S21'][:] 

x4 = f4['Frequency'][:]
y4 = f4['Power'][:]
z4 = f4['S21'][:]  
  
f1.close()
f2.close()
f3.close()
f4.close()

#Plot your previously saved data
fig = plt.figure(figsize=(8,6), dpi = 150)
plt.title('Two tone - gate dependence')
plt.pcolormesh(x1/1e9, y1, 20*np.log10(np.abs(z1)))
plt.pcolormesh(x2/1e9, y2, 20*np.log10(np.abs(z2)))
plt.pcolormesh(x3/1e9, y3, 20*np.log10(np.abs(z3)))
plt.pcolormesh(x4/1e9, y4, 20*np.log10(np.abs(z4)))
plt.xlabel('Frequency (GHz)')
plt.ylabel('V_g (mV)')
plt.show()

