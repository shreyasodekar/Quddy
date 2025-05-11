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
from Quddy.helper import get_unique_filename, generate_empty_nan_array, rotate_s21, get_fridge_snapshot
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
pna = KeysightP9374A('pna','TCPIP0::localhost::hislip0::INSTR')
mxg = KeysightN5183B('mxg','TCPIP0::192.168.1.140::inst0::INSTR')
ivvi = IVVI('ivvi', 'ASRL4::INSTR', numdacs=16, dac_step=10, dac_delay=0.01, safe_version=True, polarity=['BIP', 'BIP', 'BIP', 'BIP'], use_locks=False)
ivvi.set_dacs_zero()
switch = MiniCircuitsRCSPDT('switch', '192.168.1.141')

soc, soccfg = make_proxy(ns_host="192.168.1.138", ns_port=8888, proxy_name="rfsoc")

directory = 'C:/Users/frolovlab/Documents/Python Scripts/Data/'
expt = '2025_02_18_TransmonFridge_SnInAs_2x7_ParampV1.1-2_Cooldown1'
os.chdir(directory + expt)
print('All instruments connected')
print('Working Directory: '+ directory + expt)

import win32com.client as win32
word = win32.Dispatch('Word.Application')
doc = word.Documents.Open(directory + expt + '/' + expt + '.docx')
word.Selection.GoTo(What=win32.constants.wdGoToLine, Which=win32.constants.wdGoToLast)
word.Visible = True
selection = word.Selection
