import numpy as np
from scipy.optimize import curve_fit

def C1_Single_tone(start, stop, points):
    with open(r"C:\Users\HatLab_Xi Cao\Documents\Python Scripts\msmt\CW\C1_Single_tone.py") as file:
        expt_cfg = {'start': start,
                'stop': stop,
                'points': points
                }
    exec(file.read())


def C1_1_Single_tone_powerdep(f_start, f_stop, f_points):
    with open(r"C:\Users\HatLab_Xi Cao\Documents\Python Scripts\msmt\CW\C1_Single_tone.py") as file:
        expt_cfg = {'start': start,
                'stop': stop,
                'points': points
                }
    exec(file.read())