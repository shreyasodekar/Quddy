# -*- coding: utf-8 -*-
"""
Created on Mon Feb 23 14:06:28 2026

@author: frolovlab
"""

from matplotlib.gridspec import GridSpec
import pyvisa
from resonator import reflection
import json
from datetime import datetime
import time
          
# -------------------------
# Setting up PNA and MXG for simultaneous sweep
# -------------------------
# Needs hardware handshake via rear panel SMB/BNCs
def ams_sync_PNA_MXG_for_simultaneous_sweep(pna, mxg, pna_pwr, pna_start_freq, pna_stop_freq, mxg_pwr, mxg_start, mxg_stop, num_avg=10, num_pts=5):
    """
    Configures the MXG as a follower and the PNA as the Master.
    Separates Sweep Start (Immediate) from Point Advance (External).
    """
    # --- 1. MXG Setup (The Follower) ---
    mxg.write(':ABORt')                     # Kill any existing sweep engine
    # print(f"MXG initially Parked at Point: {mxg.ask(':LIST:CPO?')}")
    
    mxg.write(':FREQ:MODE CW')              # Set to CW to allow config changes
    
    # Power and ALC Setup
    mxg.write(':POW:ATT:AUTO ON')           # Enable auto-attenuation for setup
    mxg.write(f':POW {mxg_pwr}')            # Set desired pump power
    mxg.write(':POW:ALC:SOUR INT')          # Use internal leveling sensor
    time.sleep(0.001)                        # Settle time for attenuator mechanical switching
    mxg.write(':POW:ATT:AUTO OFF')          # Lock attenuator to prevent switching noise during sweep
    mxg.write(':POW:ALC OFF')               # Open loop mode for maximum frequency switching speed

    # Frequency List Setup
    mxg.write(f':FREQ:STAR {mxg_start}')    # Define List Start frequency
    mxg.write(f':FREQ:STOP {mxg_stop}')     # Define List Stop frequency
    mxg.write(f':SWE:POIN {num_pts}')       # Match MXG points to PNA points
    mxg.write(':LIST:TYPE STEP')            # Set to Linear step sweep mode
    mxg.write(':SWE:DWEL 0.0003')             # Set internal dwell to 0; VNA handles timing

    # Trigger Logic (The Handshake)
    mxg.write(':TRIG:SOUR IMM')             # First sweep point starts immediately upon arming
    mxg.write(':LIST:TRIG:SOUR EXT')        # Points 2 through N wait for BNC trigger pulse
    mxg.write(':TRIG:SLOP POS')             # Trigger on the rising edge of the pulse
    mxg.write(':LIST:RETRace OFF')          # Stay at last freq until VNA re-arms next sweep
    mxg.write(':INIT:CONT ON')              # Keep engine active for multi-sweep averaging
    
    # Park the instrument safely in Manual Mode
    mxg.write(':FREQ:MODE LIST')            # Engage List mode
    mxg.write(':LIST:MODE MAN')             # Manual point control for parking
    mxg.write(':LIST:MAN 1')                # Physically move to Point 1
    mxg.write(':LIST:MODE STEP') 
    print(f"MXG Parked at Point: {mxg.ask(':LIST:CPO?')}")

    # --- 2. PNA Setup (The Master) ---
    pna.power(pna_pwr)                      # Set VNA port power
    pna.start(pna_start_freq)               # Set VNA start freq
    pna.stop(pna_stop_freq)                 # Set VNA stop freq
    pna.points(num_pts)                     # Set VNA number of points
    
    pna.write(f'SENS1:AVER:COUN {num_avg}')      # Set averaging factor
    pna.write(f'SENS1:SWE:GRO:COUN {num_avg}')  # Set number of sweeps in the group
    pna.write('SENS1:AVER:STAT ON')             # Enable averaging
    pna.write('SENS1:AVER:CLE')                 # Clear existing average buffer

    # Trigger Out (AUX1) Configuration
    pna.write('TRIG:CHAN1:AUX1 ON')         # Enable Rear Panel BNC Output
    pna.write('TRIG:CHAN1:AUX1:INT POIN')   # Send a pulse after every point
    
    # Logic: VNA measures Point N, then pulses to move MXG to Point N+1.
    pna.write('TRIG:CHAN1:AUX1:POS AFT')    # Set pulse to fire AFTER measurement is done
    
    pna.write('TRIG:CHAN1:AUX1:DUR 0.0001') # 100us pulse width (fast enough for MXG)
    pna.write('TRIG:CHAN1:AUX1:OPOL POS')   # Positive polarity (Rising Edge)
    
    # Timing buffers
    pna.write('SENS1:SWE:DWEL 0.01')       # 10ms wait for small freq steps (e.g. 4.4MHz)
    pna.write('SENS1:SWE:DWEL:SDEL 0.02')   # 50ms wait for large retrace jump (e.g. 4GHz)

    pna.write('TRIG:SOUR IMM')               # Set VNA to Internal/Immediate trigger
    pna.ask('*OPC?')                         # Wait for all commands to finish

# -------------------------
# Restore MXG and PNA to safe standalone operation
# -------------------------
# Restore both instruments to safe default states, we are familiar in seeing. 
# Particularly, useful after synchronized sweeps but can be used in general after many experiments.

def restore_MXG_PNA_to_defaults(ATTEN_HOLD_RESET = 0):

    # --- 0. Querry the ALC state, ATTEN HOLD is a problem in you want to set higher powers later    
    alc_state = mxg.ask(':POW:ALC:STAT?').strip()
    atten_auto = mxg.ask(':POW:ATT:AUTO?').strip() # atten_auto = 0 means ATTEN HOLD is on and you can't increase power beyond 5dBm
    alc_search_state = float(mxg.ask(':POW:ALC:SEAR?').strip())
    
    error_msg = mxg.ask(':SYST:ERR?')
    if "Unleveled" in error_msg:
        print(f"Warning: MXG was unleveled during high power sweep: {error_msg}")
        
    # --- 1. MXG Restore ---
    # Reset to CW/Fixed first to break the sweep engine
    mxg.write(':FREQ:MODE FIX') 
    mxg.write(':SOUR:POW -20') 
    mxg.write(':OUTP OFF')

    # Force restoration if they were modified by the simultaneous sweep preset defined earlier
    if alc_state == '0' or (atten_auto == '0' and ATTEN_HOLD_RESET == 1 ) or alc_search_state != 1:
        print("Restoring Power Leveling (ALC ON / Atten AUTO)...")
        mxg.write(':POW:ALC:STAT ON')     # Turn ALC back on
        mxg.write(':POW:ATT:AUTO ON')     # Release Atten Hold
        mxg.write(':POW:ALC:SEAR ON')     # Ensure Search is active
    
    # Optional: Reset trigger back to Immediate so manual front-panel use works
    mxg.write(':TRIG:SOUR IMM')
    mxg.write(':FREQ:MODE CW')            # Reset state to allow frequency/point changes

    # --- 2. PNA Restore ---
    # Disable the hardware handshake first
    pna.write('TRIG:CHAN1:AUX1 OFF')      
    pna.write('SENS1:SWE:DWEL 0')         # Remove the artificial delay we added for triggered measurements
    
    # Reset Averaging/Grouping
    pna.write('SENS1:SWE:GRO:COUN 1')     # Default to 1 sweep per group
    
    # IMPORTANT: Return to Continuous Sweep mode
    # If left in 'HOLD' or 'SINGle', the VNA screen will look "frozen" to the next user.
    pna.write('SENS1:SWE:MODE CONT')      
    
    # Ensure it's using Internal Trigger
    pna.write('TRIG:SOUR IMM')            
    
    print("Instruments restored to safe standalone operation.")
