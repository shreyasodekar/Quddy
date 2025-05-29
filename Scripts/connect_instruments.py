import os
import time
from datetime import datetime
import json
import logging

import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
from tqdm import tqdm, trange
import h5py
from qick import *
from Quddy import *
from Quddy.helper import get_unique_filename, generate_empty_nan_array, rotate_s21, get_fridge_snapshot, generate_empty_snapshot_array
from resonator import background, see, shunt

import qcodes as qc
from qcodes.dataset import Measurement
from qcodes.logger.logger import start_all_logging
from qcodes_contrib_drivers.drivers.OxfordInstruments.Proteox import oiDECS
from qcodes.instrument_drivers.Keysight import KeysightP9374A
from qcodes.instrument_drivers.Keysight import KeysightN5183B

from qcodes.instrument_drivers.Minicircuits import MiniCircuitsRCSPDT
from qcodes_contrib_drivers.drivers.QuTech.IVVI import IVVI
from qick.pyro import make_proxy

Proteox = oiDECS('Proteox')
Proteox.timeout(500)
pna = KeysightP9374A('pna','TCPIP0::localhost::hislip0::INSTR')
mxg = KeysightN5183B('mxg','TCPIP0::192.168.1.140::inst0::INSTR')
# ivvi = IVVI('ivvi', 'ASRL4::INSTR', numdacs=16, dac_step=10, dac_delay=0.01, safe_version=True, polarity=['BIP', 'BIP', 'BIP', 'BIP'], use_locks=False)
# ivvi.set_dacs_zero()
switch = MiniCircuitsRCSPDT('switch', '192.168.1.141')

soc, soccfg = make_proxy(ns_host="192.168.1.138", ns_port=8888, proxy_name="rfsoc")

directory = 'C:/Users/frolovlab/Documents/Python Scripts/Data/'
expt = '2025_05_24_TransmonFridge_Res-LL-2_Cooldown1'

if not os.path.exists(directory + expt):
    os.makedirs(directory + expt + '/Data' + '/All/'+ 'CW')
    os.makedirs(directory + expt + '/Data' + '/All/'+ 'RFSOC')
    os.makedirs(directory + expt + '/Data' + '/R1/' + 'CW')
    os.makedirs(directory + expt + '/Data' + '/R1/' + 'RFSOC')
    os.makedirs(directory + expt + '/Data' + '/R2/' + 'CW')
    os.makedirs(directory + expt + '/Data' + '/R2/' + 'RFSOC')
    os.makedirs(directory + expt + '/Data' + '/R3/' + 'CW')
    os.makedirs(directory + expt + '/Data' + '/R3/' + 'RFSOC')
    os.makedirs(directory + expt + '/Data' + '/R4/' + 'CW')
    os.makedirs(directory + expt + '/Data' + '/R4/' + 'RFSOC')
    os.makedirs(directory + expt + '/Data' + '/R5/' + 'CW')
    os.makedirs(directory + expt + '/Data' + '/R5/' + 'RFSOC')
    os.makedirs(directory + expt + '/Data' + '/R6/' + 'CW')
    os.makedirs(directory + expt + '/Data' + '/R6/' + 'RFSOC')
    
os.chdir(directory + expt)

print('All instruments connected')
print('Working Directory: '+ directory + expt)

import win32com.client as win32
word = win32.Dispatch('Word.Application')
if not os.path.exists('./'+expt + '.docx'):
    open('./'+expt + '.docx','w').close()
doc = word.Documents.Open(os.path.abspath('./'+expt + '.docx'))
word.Selection.GoTo(What=3, Which=-1)
word.Visible = True
selection = word.Selection
