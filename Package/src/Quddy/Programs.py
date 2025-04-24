from qick import *


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
                       length=self.us2cycles(cfg['qubit']['sigma'])*3)
        
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
                       sigma=self.us2cycles(cfg['qubit']['sigma']), 
                       length=self.us2cycles(cfg['qubit']['sigma'])*3)
        
        self.set_pulse_registers(ch=cfg['qubit']['channel'], 
                                 style="arb", 
                                 freq=self.freq2reg(cfg['qubit']['frequency'], gen_ch=cfg['qubit']['channel']), 
                                 phase=self.deg2reg(cfg['qubit']['phase']), 
                                 gain=int(cfg['qubit']['gain']/2),
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
                       name="qubit", 
                       sigma=self.us2cycles(cfg['qubit']['sigma']), 
                       length=self.us2cycles(cfg['qubit']['sigma'])*3)
        
        self.default_pulse_registers(ch=cfg['qubit']['channel'], 
                                 style="arb", 
                                 freq=self.freq2reg(cfg['qubit']['frequency'], gen_ch=cfg['qubit']['channel']),
                                 phase=self.deg2reg(cfg['qubit']['phase']),
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
        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], gain=int(cfg['qubit']['gain'] / 2))
        self.pulse(ch=self.cfg['qubit']['channel'])    #play pi/2 probe pulse
        
        self.sync_all(self.us2cycles(cfg['qubit']['echo_time'])) # align channels and wait
        
        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], gain=cfg['qubit']['gain'])
        self.pulse(ch=self.cfg['qubit']['channel'])    #play pi probe pulse
        
        self.sync_all(self.us2cycles(cfg['qubit']['echo_time'])) # align channels and wait
        
        self.set_pulse_registers(ch=self.cfg['qubit']['channel'], gain=int(cfg['qubit']['gain'] / 2))
        self.pulse(ch=self.cfg['qubit']['channel'])    #play pi/2 probe pulse
        
        self.sync_all(self.us2cycles(cfg['qubit']['sync_time'])) # align channels and wait


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
