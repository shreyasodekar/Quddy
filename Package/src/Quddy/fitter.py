import numpy as np
from scipy.optimize import curve_fit

def lorentzian( x, x0, y0 , a, gam ):
    return a * gam**2 / ( gam**2 + ( x - x0 )**2) + y0

def duallorentzian( x, x0_1, x0_2, y0, a_1, a_2, gam_1, gam_2 ):
    return a_1 * gam_1**2 / ( gam_1**2 + ( x - x0_1 )**2) + a_2 * gam_2**2 / ( gam_2**2 + ( x - x0_2 )**2) + y0

def sinedecay(x, y0, a, omega, T, phi):
    return a * np.exp(-x/T) * np.sin(omega*x + phi) + y0

def Tdecay(x, y0, a, T):
    return y0 + a*np.exp(-x/T)
