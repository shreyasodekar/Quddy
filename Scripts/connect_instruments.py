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
from qcodes.instrument_drivers.Keysight.Keysight_P5005A import KeysightP5005A
from qcodes.instrument_drivers.Keysight import KeysightN5183B
from qcodes_contrib_drivers.drivers.SignalCore.SC5511A import SC5511A

from qcodes.instrument_drivers.Minicircuits import MiniCircuitsRCSPDT
from qcodes_contrib_drivers.drivers.QuTech.IVVI import IVVI
from qcodes_contrib_drivers.drivers.QuTech.Optodac import Optodac
from qick.pyro import make_proxy

Proteox = oiDECS('Proteox')
Proteox.timeout(500)
pna = KeysightP5005A('pna','TCPIP0::localhost::hislip0::INSTR')
pna.timeout(500)
pna.visa_handle.chunk_size = 1024*1024
mxg = KeysightN5183B('mxg','TCPIP0::192.168.1.140::inst0::INSTR')
sc = SC5511A('mw1', '10001C4E')
sc.connect_message()
# ivvi = IVVI('ivvi', 'ASRL4::INSTR', numdacs=16, dac_step=10, dac_delay=0.1, safe_version=True, polarity=['BIP', 'BIP', 'BIP', 'BIP'], use_locks=False)
# ivvi.set_dacs_zero()
switch = MiniCircuitsRCSPDT('switch', '192.168.1.141')
ivvi = Optodac('ivvi', 'ASRL3::INSTR', numdacs=8, dac_step=1, dac_delay=0.1)

soc, soccfg = make_proxy(ns_host="192.168.1.156", ns_port=8888, proxy_name="rfsoc")

directory = 'C:/Users/frolovlab/Documents/Python Scripts/Data/'
# expt = '2026_05_07_TransmonFridge_GateMon_Ec250Mhz_ChipA_MC_Cooldown1'
expt = '2026_04_30_TransmonFridge_LL_Candle_qubit_Cooldown4'

if not os.path.exists(directory + expt):
    os.makedirs(directory + expt + '/Data' + '/All/'+ 'CW')
    os.makedirs(directory + expt + '/Data' + '/All/'+ 'RFSOC')
    os.makedirs(directory + expt + '/Data' + '/Q1/' + 'CW')
    os.makedirs(directory + expt + '/Data' + '/Q1/' + 'RFSOC')
    os.makedirs(directory + expt + '/Data' + '/Q2/' + 'CW')
    os.makedirs(directory + expt + '/Data' + '/Q2/' + 'RFSOC')
    os.makedirs(directory + expt + '/Data' + '/Q3/' + 'CW')
    os.makedirs(directory + expt + '/Data' + '/Q3/' + 'RFSOC')
    os.makedirs(directory + expt + '/Data' + '/Q4/' + 'CW')
    os.makedirs(directory + expt + '/Data' + '/Q4/' + 'RFSOC')
    os.makedirs(directory + expt + '/Data' + '/Q5/' + 'CW')
    os.makedirs(directory + expt + '/Data' + '/Q5/' + 'RFSOC')
    os.makedirs(directory + expt + '/Data' + '/Q6/' + 'CW')
    os.makedirs(directory + expt + '/Data' + '/Q6/' + 'RFSOC')
    
os.chdir(directory + expt)

print('All instruments connected')
print('Working Directory: '+ directory + expt)

show_plot = True
ask_save_to_doc = True

import win32com.client as win32
word = win32.Dispatch('Word.Application')
if not os.path.exists('./'+expt + '.docx'):
    open('./'+expt + '.docx','w').close()
doc = word.Documents.Open(os.path.abspath('./'+expt + '.docx'))
word.Selection.GoTo(What=3, Which=-1)
word.Visible = True
selection = word.Selection
