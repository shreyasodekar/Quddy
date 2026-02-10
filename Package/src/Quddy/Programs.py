from qick import *
import ctypes
import numpy as np

class SingleTone(AveragerProgram):
    def initialize(self):
        cfg=self.cfg
        self.declare_gen(ch=cfg['resonator']['channel'], nqz=cfg['resonator']['nqz']) 	          #Declare generator for readout

        #configure the readout lengths and downconversion frequencies
        for ch in cfg['ADCs']: 
            self.declare_readout(ch=ch, 
                                 length=cfg['readout_length'],
                                 freq=cfg['resonator']['frequency'],            #this has to be in Mhz
                                 gen_ch=cfg['resonator']['channel'])

        self.set_pulse_registers(ch=cfg['resonator']['channel'], 
                                 style="const", 
                                 freq=self.freq2reg(cfg['resonator']['frequency'], gen_ch=cfg['resonator']['channel'], ro_ch=cfg['ADCs'][0]), 
                                 phase=self.deg2reg(cfg['resonator']['phase']), 
                                 gain=cfg['resonator']['gain'],
                                 length=cfg['resonator']['pulse_length'])
        
        self.sync_all(self.us2cycles(500))  # give processor some time to configure pulses
    
    def body(self):  
        cfg=self.cfg
        self.measure(pulse_ch=cfg['resonator']['channel'], 
             adcs=cfg['ADCs'],
             adc_trig_offset=cfg['adc_trig_offset'],
             wait=True,
             syncdelay=self.us2cycles(cfg['relax_delay']))    



class ConstantPulseProbe(AveragerProgram):
    def initialize(self):
        cfg=self.cfg
        self.declare_gen(ch=cfg['resonator']['channel'], nqz=cfg['resonator']['nqz']) #Readout
        self.declare_gen(ch=cfg['qubit']['channel'], nqz=cfg['qubit']['nqz']) #Qubit
        
        for ch in cfg['ADCs']: #configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch,
                                length=cfg['readout_length'],
                                freq=cfg['resonator']['frequency'], 
                                gen_ch=cfg['resonator']['channel'])

                # add qubit and readout pulses to respective channels
        self.set_pulse_registers(ch=cfg['qubit']['channel'], 
                                 style="const", 
                                 freq=self.freq2reg(cfg['qubit']['frequency'], gen_ch=cfg['qubit']['channel']), 
                                 phase=self.deg2reg(cfg['qubit']['phase']), 
                                 gain=cfg['qubit']['gain'],
                                 length=cfg['qubit']['pulse_length'])
        
        self.set_pulse_registers(ch=cfg['resonator']['channel'], 
                                 style="const", 
                                 freq=self.freq2reg(cfg['resonator']['frequency'], gen_ch=cfg['resonator']['channel'], ro_ch=cfg['ADCs'][0]), 
                                 phase=self.deg2reg(cfg['resonator']['phase']), 
                                 gain=cfg['resonator']['gain'], 
                                 length=cfg['resonator']['pulse_length'])
        
        self.sync_all(self.us2cycles(500))
    
    def body(self):
        cfg=self.cfg
        self.pulse(ch=self.cfg['qubit']['channel'])  #play probe pulse

        self.sync_all(self.us2cycles(cfg['qubit']['wait_time']))

        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg['resonator']['channel'], 
             adcs=cfg['ADCs'],
             adc_trig_offset=self.cfg['adc_trig_offset'],
             wait=True,
             syncdelay=self.us2cycles(self.cfg['relax_delay']))



class GaussianPulseProbe(AveragerProgram):
    def initialize(self):
        cfg=self.cfg
        
        self.declare_gen(ch=cfg['resonator']['channel'], nqz=cfg['resonator']['nqz']) #Readout
        self.declare_gen(ch=cfg['qubit']['channel'], nqz=cfg['qubit']['nqz']) #Qubit
        
        for ch in cfg['ADCs']: #configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch,
                                length=cfg['readout_length'],
                                freq=cfg['resonator']['frequency'], 
                                gen_ch=cfg['resonator']['channel'])

                # add qubit and readout pulses to respective channels
        self.add_gauss(ch=cfg['qubit']['channel'], 
                       name="qubit", 
                       sigma=self.us2cycles(cfg['qubit']['sigma']), 
                       length=self.us2cycles(cfg['qubit']['sigma'])*4)
        
        self.set_pulse_registers(ch=cfg['qubit']['channel'], 
                                 style="arb", 
                                 freq=self.freq2reg(cfg['qubit']['frequency'], gen_ch=cfg['qubit']['channel']), 
                                 phase=self.deg2reg(cfg['qubit']['phase']), 
                                 gain=cfg['qubit']['gain'],
                                 waveform="qubit")
        
        self.set_pulse_registers(ch=cfg['resonator']['channel'], 
                                 style="const", 
                                 freq=self.freq2reg(cfg['resonator']['frequency'], gen_ch=cfg['resonator']['channel'], ro_ch=cfg['ADCs'][0]), 
                                 phase=self.deg2reg(cfg['resonator']['phase']), 
                                 gain=cfg['resonator']['gain'], 
                                 length=cfg['resonator']['pulse_length'])
        
        self.sync_all(self.us2cycles(500))
        
    def body(self):
        cfg=self.cfg
        self.pulse(ch=self.cfg['qubit']['channel'])  #play probe pulse
        
        self.sync_all(self.us2cycles(cfg['qubit']['wait_time']))

        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg['resonator']['channel'], 
              adcs=cfg['ADCs'],
              adc_trig_offset=self.cfg['adc_trig_offset'],
              wait=True,
              syncdelay=self.us2cycles(self.cfg['relax_delay']))

class Ramsey(AveragerProgram):
    def initialize(self):
        cfg=self.cfg
        
        self.declare_gen(ch=cfg['resonator']['channel'], nqz=cfg['resonator']['nqz']) #Readout
        self.declare_gen(ch=cfg['qubit']['channel'], nqz=cfg['qubit']['nqz']) #Qubit
        for ch in cfg['ADCs']: #configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch,
                                length=cfg['readout_length'],
                                freq=cfg['resonator']['frequency'], 
                                gen_ch=cfg['resonator']['channel'])

                # add qubit and readout pulses to respective channels
        self.add_gauss(ch=cfg['qubit']['channel'], 
                       name="qubit", 
                       sigma=self.us2cycles(cfg['qubit']['sigma']/2),  ### changed sigma to sigma/2
                       length=self.us2cycles(cfg['qubit']['sigma'])*4/2)
        
        self.set_pulse_registers(ch=cfg['qubit']['channel'], 
                                 style="arb", 
                                 freq=self.freq2reg(cfg['qubit']['frequency'], gen_ch=cfg['qubit']['channel']), 
                                 phase=self.deg2reg(cfg['qubit']['phase']), 
                                 gain=int(cfg['qubit']['gain']),
                                 waveform="qubit")
        
        self.set_pulse_registers(ch=cfg['resonator']['channel'], 
                                 style="const", 
                                 freq=self.freq2reg(cfg['resonator']['frequency'], gen_ch=cfg['resonator']['channel'], ro_ch=cfg['ADCs'][0]), 
                                 phase=self.deg2reg(cfg['resonator']['phase']), 
                                 gain=cfg['resonator']['gain'], 
                                 length=cfg['resonator']['pulse_length'])
        
        self.sync_all(self.us2cycles(1))
    
    def body(self):
        cfg=self.cfg
        self.pulse(ch=self.cfg['qubit']['channel'])    #play probe pi/2-pulse
        self.sync_all(self.us2cycles(cfg['qubit']['dephase_time'])) # 
        self.pulse(ch=self.cfg['qubit']['channel'])    #play probe pi/2-pulse
        self.sync_all(self.us2cycles(cfg['qubit']['wait_time'])) # align channels and wait


        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg['resonator']['channel'], 
              adcs=cfg['ADCs'],
              adc_trig_offset=self.cfg['adc_trig_offset'],
              wait=True,
              syncdelay=self.us2cycles(self.cfg['relax_delay']))


class HahnEcho(AveragerProgram):
    def initialize(self):
        cfg=self.cfg
        
        self.declare_gen(ch=cfg['resonator']['channel'], nqz=cfg['resonator']['nqz']) #Readout
        self.declare_gen(ch=cfg['qubit']['channel'], nqz=cfg['qubit']['nqz']) #Qubit
        for ch in cfg['ADCs']: #configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch,
                                length=cfg['readout_length'],
                                freq=cfg['resonator']['frequency'], 
                                gen_ch=cfg['resonator']['channel'])

                # add qubit and readout pulses to respective channels
        self.add_gauss(ch=cfg['qubit']['channel'], 
                       name="Rx", 
                       sigma=self.us2cycles(cfg['qubit']['sigma']/2), 
                       length=self.us2cycles(cfg['qubit']['sigma'])*4/2) #### added another waveform
        
        self.add_gauss(ch=cfg['qubit']['channel'], 
                       name="Ry", 
                       sigma=self.us2cycles(cfg['qubit']['sigma']), 
                       length=self.us2cycles(cfg['qubit']['sigma'])*4)
        
        
        self.default_pulse_registers(ch=cfg['qubit']['channel'], 
                                 style="arb", 
                                 freq=self.freq2reg(cfg['qubit']['frequency'], gen_ch=cfg['qubit']['channel']),
                                 gain=cfg['qubit']['gain'])
        
        self.set_pulse_registers(ch=cfg['resonator']['channel'], 
                                 style="const", 
                                 freq=self.freq2reg(cfg['resonator']['frequency'], gen_ch=cfg['resonator']['channel'], ro_ch=cfg['ADCs'][0]), 
                                 phase=self.deg2reg(cfg['resonator']['phase']), 
                                 gain=cfg['resonator']['gain'], 
                                 length=cfg['resonator']['pulse_length'])
        
        self.sync_all(self.us2cycles(500))
    
    def body(self):
        cfg=self.cfg
        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], waveform = 'Rx', phase=self.deg2reg(cfg['qubit']['phase']))
        self.pulse(ch=self.cfg['qubit']['channel'])    #play pi/2 probe pulse
        
        self.sync_all(self.us2cycles(cfg['qubit']['echo_time'])) # align channels and wait
        
        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], waveform = 'Ry', phase=self.deg2reg(cfg['qubit']['phase']))
        self.pulse(ch=self.cfg['qubit']['channel'])    #play pi probe pulse witha 90 degree phase difference.
        
        self.sync_all(self.us2cycles(cfg['qubit']['echo_time'])) # align channels and wait
        
        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], waveform = 'Rx', phase=self.deg2reg(cfg['qubit']['phase']))
        self.pulse(ch=self.cfg['qubit']['channel'])    #play pi/2 probe pulse
        
        self.sync_all(self.us2cycles(cfg['qubit']['sync_time'])) # align channels and wait


        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg['resonator']['channel'], 
              adcs=cfg['ADCs'],
              adc_trig_offset=self.cfg['adc_trig_offset'],
              wait=True,
              syncdelay=self.us2cycles(self.cfg['relax_delay']))


class CPMG(AveragerProgram):
    def initialize(self):
        cfg=self.cfg
        self.declare_gen(ch=cfg['resonator']['channel'], nqz=cfg['resonator']['nqz']) #Readout
        self.declare_gen(ch=cfg['qubit']['channel'], nqz=cfg['qubit']['nqz']) #Qubit
        for ch in cfg['ADCs']: #configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch,
                                length=cfg['readout_length'],
                                freq=cfg['resonator']['frequency'], 
                                gen_ch=cfg['resonator']['channel'])

                # add qubit and readout pulses to respective channels
        self.add_gauss(ch=cfg['qubit']['channel'], 
                       name="Rx", 
                       sigma=self.us2cycles(cfg['qubit']['sigma']), 
                       length=self.us2cycles(cfg['qubit']['sigma'])) #### added another waveform
        
        self.add_gauss(ch=cfg['qubit']['channel'], 
                       name="Ry", 
                       sigma=self.us2cycles(cfg['qubit']['sigma']), 
                       length=self.us2cycles(cfg['qubit']['sigma'])*3)
        
        
        self.default_pulse_registers(ch=cfg['qubit']['channel'], 
                                 style="arb", 
                                 freq=self.freq2reg(cfg['qubit']['frequency'], gen_ch=cfg['qubit']['channel']),
                                 gain=cfg['qubit']['gain'])
        
        self.set_pulse_registers(ch=cfg['resonator']['channel'], 
                                 style="const", 
                                 freq=self.freq2reg(cfg['resonator']['frequency'], gen_ch=cfg['resonator']['channel'], ro_ch=cfg['ADCs'][0]), 
                                 phase=self.deg2reg(cfg['resonator']['phase']), 
                                 gain=cfg['resonator']['gain'], 
                                 length=cfg['resonator']['pulse_length'])
        
        self.sync_all(self.us2cycles(500))
    
    def body(self):
        cfg=self.cfg
        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], waveform = 'Rx', phase=self.deg2reg(cfg['qubit']['phase']))
        self.pulse(ch=self.cfg['qubit']['channel'])    #play pi/2 probe pulse
        
        for i in range(self.cfg['CPMG_order']):
            self.sync_all(self.us2cycles(cfg['qubit']['echo_time'])) # align channels and wait
            
            self.set_pulse_registers(ch=self.cfg['qubit']['channel'], waveform = 'Ry', phase=self.deg2reg(cfg['qubit']['phase']+90))
            self.pulse(ch=self.cfg['qubit']['channel'])    #play pi probe pulse
            
            self.sync_all(self.us2cycles(cfg['qubit']['echo_time'])) # align channels and wait
        
        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], waveform = 'Rx', phase=self.deg2reg(cfg['qubit']['phase']))
        self.pulse(ch=self.cfg['qubit']['channel'])    #play pi/2 probe pulse
        
        self.sync_all(self.us2cycles(cfg['qubit']['sync_time'])) # align channels and wait


        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg['resonator']['channel'], 
              adcs=cfg['ADCs'],
              adc_trig_offset=self.cfg['adc_trig_offset'],
              wait=True,
              syncdelay=self.us2cycles(self.cfg['relax_delay']))
        

  

class Threetone(AveragerProgram):
    def initialize(self):
        cfg=self.cfg
        
        self.declare_gen(ch=cfg['resonator']['channel'], nqz=cfg['resonator']['nqz']) #Readout
        self.declare_gen(ch=cfg['qubit']['channel'], nqz=cfg['qubit']['nqz']) #Qubit
        
        for ch in cfg['ADCs']: #configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch,
                                length=cfg['readout_length'],
                                freq=cfg['resonator']['frequency'], 
                                gen_ch=cfg['resonator']['channel'])

                # add qubit and readout pulses to respective channels
        self.add_gauss(ch=cfg['qubit']['channel'], 
                       name="qubit", 
                       sigma=self.us2cycles(cfg['qubit']['sigma']), 
                       length=self.us2cycles(cfg['qubit']['sigma'])*4)

        self.add_gauss(ch=cfg['qubit']['channel'], 
                       name="qubit12", 
                       sigma=self.us2cycles(cfg['qubit']['sigma12']), 
                       length=self.us2cycles(cfg['qubit']['sigma12'])*4)
        
        self.default_pulse_registers(ch=cfg['qubit']['channel'], 
                                 style="arb",
                                 gain=cfg['qubit']['gain'],
                                 phase=cfg['qubit']['phase'])
        
        self.set_pulse_registers(ch=cfg['resonator']['channel'], 
                                 style="const", 
                                 freq=self.freq2reg(cfg['resonator']['frequency'], gen_ch=cfg['resonator']['channel'], ro_ch=cfg['ADCs'][0]), 
                                 phase=self.deg2reg(cfg['resonator']['phase']), 
                                 gain=cfg['resonator']['gain'], 
                                 length=cfg['resonator']['pulse_length'])
        
        self.sync_all(self.us2cycles(500))
        
    def body(self):
        cfg=self.cfg
        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], waveform = 'qubit', freq=self.freq2reg(cfg['qubit']['frequency'], gen_ch=cfg['qubit']['channel']),)
        self.pulse(ch=self.cfg['qubit']['channel'])
        
        self.sync_all(self.us2cycles(cfg['qubit']['wait_time']))

        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], waveform = 'qubit12', freq=self.freq2reg(cfg['qubit']['frequency12'], gen_ch=cfg['qubit']['channel']),)
        self.pulse(ch=self.cfg['qubit']['channel'])

        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg['resonator']['channel'], 
              adcs=cfg['ADCs'],
              adc_trig_offset=self.cfg['adc_trig_offset'],
              wait=True,
              syncdelay=self.us2cycles(self.cfg['relax_delay']))
        


class SingleShot(RAveragerProgram):
    def initialize(self):
        cfg=self.cfg
        
        self.declare_gen(ch=cfg['resonator']['channel'], nqz=cfg['resonator']['nqz']) 	#Declare generator for readout
        self.declare_gen(ch=cfg['qubit']['channel'], nqz=cfg['qubit']['nqz']) 	    #Declare generator for qubit
        
        for ch in cfg['ADCs']:       #configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, 
                                 length=cfg['readout_length'],
                                 freq=cfg['resonator']['frequency'], 
                                 gen_ch=cfg['resonator']['channel'])

        cfg['start']=0
        cfg['step']=cfg['qubit']['gain']
        cfg['expts']=2
        
        self.q_rp=self.ch_page(cfg['qubit']['channel'])     # get register page for qubit_ch
        self.r_gain=self.sreg(cfg['qubit']['channel'], 'gain')   # get gain register for qubit_ch    
        
        # add qubit and readout pulses to respective channels
        self.add_gauss(ch=cfg['qubit']['channel'], 
                       name="qubit", 
                       sigma=self.us2cycles(cfg['qubit']['sigma']), 
                       length=self.us2cycles(cfg['qubit']['sigma'])*4)
        
        self.set_pulse_registers(ch=cfg['qubit']['channel'], 
                                 style="arb", 
                                 freq=self.freq2reg(cfg['qubit']['frequency'], gen_ch=cfg['qubit']['channel']), 
                                 phase=self.deg2reg(cfg['qubit']['phase']), 
                                 gain=cfg["start"],
                                 waveform="qubit")
        
        self.set_pulse_registers(ch=cfg['resonator']['channel'], 
                                 style="const", 
                                 freq=self.freq2reg(cfg['resonator']['frequency'], gen_ch=cfg['resonator']['channel'], ro_ch=cfg['ADCs'][0]), 
                                 phase=self.deg2reg(cfg['resonator']['phase']), 
                                 gain=cfg['resonator']['gain'], 
                                 length=cfg['resonator']['pulse_length'])

        self.sync_all(self.us2cycles(500))
    
    def body(self):
        cfg = self.cfg
        self.pulse(ch=cfg['qubit']['channel'])  #play probe pulse
        self.sync_all(self.us2cycles(0.05)) # align channels and wait 50ns

        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=cfg['resonator']['channel'], 
                     adcs=cfg['ADCs'],
                     adc_trig_offset=cfg['adc_trig_offset'],
                     wait=True,
                     syncdelay=self.us2cycles(cfg['relax_delay'])) 
    
    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg['step']) # update frequency list index
        
    def acquire(self,soc, progress=False):
        super().acquire(soc, progress=progress)
        return self.collect_shots()
        
    def collect_shots(self):
        shots_i0=self.di_buf[0].reshape((self.cfg['expts'],self.cfg['reps']))/self.cfg['readout_length']
        shots_q0=self.dq_buf[0].reshape((self.cfg['expts'],self.cfg['reps']))/self.cfg['readout_length']
        shots_i1=self.di_buf[1].reshape((self.cfg['expts'],self.cfg['reps']))/self.cfg['readout_length']
        shots_q1=self.dq_buf[1].reshape((self.cfg['expts'],self.cfg['reps']))/self.cfg['readout_length']
        return shots_i0,shots_q0,shots_i1,shots_q1
        
    def analyze(self, shots_i, shots_q):
        plt.subplot(111, xlabel='I', ylabel='Q', title='Single Shot Histogram')
        plt.plot(shots_i[0],shots_q[0],'.',label='g')
        plt.plot(shots_i[1],shots_q[1],'.',label='e')
        plt.legend()
        plt.gca().set_aspect('equal', 'datalim')


class CPMG4(AveragerProgram):
    def initialize(self):
        cfg=self.cfg
        self.declare_gen(ch=cfg['resonator']['channel'], nqz=cfg['resonator']['nqz']) #Readout
        self.declare_gen(ch=cfg['qubit']['channel'], nqz=cfg['qubit']['nqz']) #Qubit
        for ch in cfg['ADCs']: #configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch,
                                length=cfg['readout_length'],
                                freq=cfg['resonator']['frequency'], 
                                gen_ch=cfg['resonator']['channel'])

                # add qubit and readout pulses to respective channels
        self.add_gauss(ch=cfg['qubit']['channel'], 
                       name="Rx", 
                       sigma=self.us2cycles(cfg['qubit']['sigma']), 
                       length=self.us2cycles(cfg['qubit']['sigma'])) #### added another waveform
        
        self.add_gauss(ch=cfg['qubit']['channel'], 
                       name="Ry", 
                       sigma=self.us2cycles(cfg['qubit']['sigma']), 
                       length=self.us2cycles(cfg['qubit']['sigma'])*3)
        
        
        self.default_pulse_registers(ch=cfg['qubit']['channel'], 
                                 style="arb", 
                                 freq=self.freq2reg(cfg['qubit']['frequency'], gen_ch=cfg['qubit']['channel']),
                                 gain=cfg['qubit']['gain'])
        
        self.set_pulse_registers(ch=cfg['resonator']['channel'], 
                                 style="const", 
                                 freq=self.freq2reg(cfg['resonator']['frequency'], gen_ch=cfg['resonator']['channel'], ro_ch=cfg['ADCs'][0]), 
                                 phase=self.deg2reg(cfg['resonator']['phase']), 
                                 gain=cfg['resonator']['gain'], 
                                 length=cfg['resonator']['pulse_length'])
        
        self.sync_all(self.us2cycles(500))
    
    def body(self):
        cfg=self.cfg
        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], waveform = 'Rx', phase=self.deg2reg(cfg['qubit']['phase']))
        self.pulse(ch=self.cfg['qubit']['channel'])    #play pi/2 probe pulse
        
        ##1
        self.sync_all(self.us2cycles(cfg['qubit']['echo_time'])) # align channels and wait
        
        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], waveform = 'Ry', phase=self.deg2reg(cfg['qubit']['phase']+90))
        self.pulse(ch=self.cfg['qubit']['channel'])    #play pi probe pulse
        
        self.sync_all(self.us2cycles(cfg['qubit']['echo_time'])) # align channels and wait
        
        ##2
        self.sync_all(self.us2cycles(cfg['qubit']['echo_time'])) # align channels and wait
        
        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], waveform = 'Ry', phase=self.deg2reg(cfg['qubit']['phase']+90))
        self.pulse(ch=self.cfg['qubit']['channel'])    #play pi probe pulse
        
        self.sync_all(self.us2cycles(cfg['qubit']['echo_time'])) # align channels and wait
        
        ##3
        self.sync_all(self.us2cycles(cfg['qubit']['echo_time'])) # align channels and wait
        
        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], waveform = 'Ry', phase=self.deg2reg(cfg['qubit']['phase']+90))
        self.pulse(ch=self.cfg['qubit']['channel'])    #play pi probe pulse
        
        self.sync_all(self.us2cycles(cfg['qubit']['echo_time'])) # align channels and wait
        
        ##4
        self.sync_all(self.us2cycles(cfg['qubit']['echo_time'])) # align channels and wait
        
        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], waveform = 'Ry', phase=self.deg2reg(cfg['qubit']['phase']+90))
        self.pulse(ch=self.cfg['qubit']['channel'])    #play pi probe pulse
        
        self.sync_all(self.us2cycles(cfg['qubit']['echo_time'])) # align channels and wait
        
        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], waveform = 'Rx', phase=self.deg2reg(cfg['qubit']['phase']))
        self.pulse(ch=self.cfg['qubit']['channel'])    #play pi/2 probe pulse
        
        self.sync_all(self.us2cycles(cfg['qubit']['sync_time'])) # align channels and wait


        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg['resonator']['channel'], 
              adcs=cfg['ADCs'],
              adc_trig_offset=self.cfg['adc_trig_offset'],
              wait=True,
              syncdelay=self.us2cycles(self.cfg['relax_delay']))
        

def CWTwoToneTriggered(pna, mxg, pna_pwr, pna_start_freq, pna_stop_freq,
                     mxg_pwr, mxg_start, mxg_stop,
                     num_avg=10, num_pts=5):
    """Synchronized PNA + MXG two-tone measurement.

    The PNA acts as master, sending a TTL pulse from Aux 1 before each point
    to step the MXG through its frequency list. Returns averaged S21 as a
    complex array.

    Parameters
    ----------
    pna : KeysightP9374A
        VNA instrument object.
    mxg : KeysightN5183B
        Signal generator instrument object.
    pna_pwr : float
        PNA source power (dBm).
    pna_start_freq, pna_stop_freq : float
        PNA readout frequency range (Hz).
    mxg_pwr : float
        MXG source power (dBm).
    mxg_start, mxg_stop : float
        MXG drive frequency range (Hz).
    num_avg : int
        Number of averages. Default 10.
    num_pts : int
        Number of sweep points. Default 5.

    Returns
    -------
    s21 : np.ndarray (complex)
        Averaged S21 data, length = num_pts.
    """

    # --- 1. MXG Setup (Follower) ---
    mxg.write(':FREQ:MODE FIX')                 # Reset to allow config changes
    mxg.write(f':POW {mxg_pwr}')
    mxg.write(f':FREQ:START {mxg_start}')
    mxg.write(f':FREQ:STOP {mxg_stop}')
    mxg.write(f':SWE:POIN {num_pts}')
    mxg.write(':LIST:TYPE STEP')                # Linear step sweep
    mxg.write(':SWE:DWEL 0')                    # Step immediately on trigger
    mxg.write(':LIST:TRIG:SOUR EXT')            # Wait for rear BNC pulse from PNA
    mxg.write(':TRIG:SWE:SOUR IMM')             # Auto-reset to start of list
    mxg.write(':FREQ:MODE SWE')                 # Enable sweep mode
    mxg.write(':OUTP ON')                        # Turn RF on
    mxg.ask('*OPC?')                             # Wait until MXG is ready

    # --- 2. PNA Setup (Master) ---
    pna.power(pna_pwr)
    pna.start(pna_start_freq)
    pna.stop(pna_stop_freq)
    pna.points(num_pts)

    # Averaging
    pna.write(f'SENS1:AVER:COUN {num_avg}')
    pna.write(f'SENS1:SWE:GRO:COUN {num_avg}')
    pna.write('SENS1:AVER:STAT ON')
    pna.write('SENS1:AVER:CLE')

    # Aux 1 trigger output — pulse before each point to step MXG
    pna.write('TRIG:CHAN1:AUX1 ON')
    pna.write('TRIG:CHAN1:AUX1:INT POIN')        # Trigger per point
    pna.write('TRIG:CHAN1:AUX1:POS BEF')         # Pulse before PNA measures
    pna.write('TRIG:CHAN1:AUX1:DUR 0.01')       # 10 ms pulse duration
    pna.write('TRIG:CHAN1:AUX1:OPOL POS')        # Positive TTL polarity
    pna.write('SENS1:SWE:DWEL 0.05')            # 50 ms dwell for MXG settling

    # Manual trigger so we can do a controlled group sweepwha
    pna.write('TRIG:SOUR MAN')
    pna.ask('*OPC?')                              # Wait until PNA is ready

    # --- 3. Run the measurement ---
    pna.write('SENS1:SWE:GRO:SING')              # Initiate group sweep (num_avg sweeps)
    pna.ask('*OPC?')                              # Wait until all averages complete

    # --- 4. Retrieve data ---
    raw = pna.ask('CALC1:DATA? SDATA')            # Alternating real, imag pairs
    values = np.array(raw.split(','), dtype=float)
    s21 = values[0::2] + 1j * values[1::2]

    # --- 5. Cleanup ---
    mxg.write(':OUTP OFF')
    pna.write('TRIG:CHAN1:AUX1 OFF')

    return s21


def CWTwoToneTriggered_SC5511A(pna, sc, pna_pwr, pna_freq,
                              sc_pwr, sc_start, sc_stop,
                              num_avg=10, num_pts=5):
    """Synchronized PNA + SignalCore SC5511A two-tone measurement.

    The PNA is parked at a single readout frequency (resonator) while the
    SC5511A sweeps through a qubit drive frequency range. The PNA acts as
    master, sending a TTL pulse from Aux 1 before each point to step the
    SC5511A via its hardware trigger input.

    Parameters
    ----------
    pna : KeysightP9374A
        VNA instrument object.
    sc : SC5511A
        SignalCore SC5511A instrument object (QCoDeS driver).
    pna_pwr : float
        PNA source power (dBm).
    pna_freq : float
        PNA readout frequency (Hz) — fixed at the resonator.
    sc_pwr : float
        SC5511A output power (dBm).
    sc_start, sc_stop : float
        SC5511A drive frequency range (Hz).
    num_avg : int
        Number of averages. Default 10.
    num_pts : int
        Number of sweep points. Default 5.

    Returns
    -------
    s21 : np.ndarray (complex)
        Averaged S21 data, length = num_pts.
    """

    step_freq = int((sc_stop - sc_start) / (num_pts - 1))
    dll = sc._dll
    sn = sc._serial_number

    # --- 1. SC5511A Setup (Follower) ---
    sc.power(sc_pwr)
    sc.frequency(sc_start)

    # Open device for sweep configuration
    handle = ctypes.c_void_p(dll.sc5511a_open_device(sn))

    # Set sweep frequency parameters
    dll.sc5511a_set_freq(handle, ctypes.c_ulonglong(int(sc_start)))

    # Configure RF params for sweep
    rf_params = sc._rf_params
    rf_params.start_freq = ctypes.c_ulonglong(int(sc_start))
    rf_params.stop_freq = ctypes.c_ulonglong(int(sc_stop))
    rf_params.step_freq = ctypes.c_ulonglong(step_freq)
    rf_params.sweep_dwell_time = ctypes.c_uint(0)       # Step immediately on trigger
    rf_params.sweep_cycles = ctypes.c_uint(0)            # Continuous until stopped

    # Configure list mode — step on hardware trigger, return to start
    list_mode = sc._list_mode
    list_mode.sss_mode = ctypes.c_ubyte(1)               # Enable sweep mode
    list_mode.sweep_dir = ctypes.c_ubyte(0)              # Forward
    list_mode.tri_waveform = ctypes.c_ubyte(0)           # No triangular
    list_mode.hw_trigger = ctypes.c_ubyte(1)             # Enable hardware trigger
    list_mode.step_on_hw_trig = ctypes.c_ubyte(1)        # Step one freq per pulse
    list_mode.return_to_start = ctypes.c_ubyte(1)        # Reset after full sweep
    list_mode.trig_out_enable = ctypes.c_ubyte(0)        # No trigger output
    list_mode.trig_out_on_cycle = ctypes.c_ubyte(0)

    dll.sc5511a_list_mode_config(handle, ctypes.byref(list_mode))

    # Set RF mode to sweep (1) and enable output
    dll.sc5511a_set_rf_mode(handle, ctypes.c_ubyte(1))
    dll.sc5511a_set_output(handle, ctypes.c_ubyte(1))

    dll.sc5511a_close_device(handle)

    # --- 2. PNA Setup (Master) ---
    pna.power(pna_pwr)
    pna.start(pna_freq)                          # Park at resonator frequency
    pna.stop(pna_freq)                           # Same — PNA doesn't move
    pna.points(num_pts)

    # Averaging
    pna.write(f'SENS1:AVER:COUN {num_avg}')
    pna.write(f'SENS1:SWE:GRO:COUN {num_avg}')
    pna.write('SENS1:AVER:STAT ON')
    pna.write('SENS1:AVER:CLE')

    # Aux 1 trigger output — pulse before each point to step SC5511A
    pna.write('TRIG:CHAN1:AUX1 ON')
    pna.write('TRIG:CHAN1:AUX1:INT POIN')        # Trigger per point
    pna.write('TRIG:CHAN1:AUX1:POS BEF')         # Pulse before PNA measures
    pna.write('TRIG:CHAN1:AUX1:DUR 0.001')       # 1 ms pulse duration
    pna.write('TRIG:CHAN1:AUX1:OPOL POS')        # Positive TTL polarity
    pna.write('SENS1:SWE:DWEL 0.005')            # 5 ms dwell for settling

    # Manual trigger for controlled group sweep
    pna.write('TRIG:SOUR MAN')
    pna.ask('*OPC?')                              # Wait until PNA is ready

    # --- 3. Run the measurement ---
    pna.write('SENS1:SWE:GRO:SING')              # Initiate group sweep
    pna.ask('*OPC?')                              # Wait until all averages complete

    # --- 4. Retrieve data ---
    raw = pna.ask('CALC1:DATA? SDATA')            # Alternating real, imag pairs
    values = np.array(raw.split(','), dtype=float)
    s21 = values[0::2] + 1j * values[1::2]

    # --- 5. Cleanup ---
    handle = ctypes.c_void_p(dll.sc5511a_open_device(sn))
    dll.sc5511a_set_output(handle, ctypes.c_ubyte(0))    # RF off
    dll.sc5511a_set_rf_mode(handle, ctypes.c_ubyte(0))   # Back to single tone
    dll.sc5511a_close_device(handle)
    pna.write('TRIG:CHAN1:AUX1 OFF')

    return s21