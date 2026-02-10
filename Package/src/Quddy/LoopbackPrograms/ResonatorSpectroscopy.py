from qick import *


class ResonatorSpectroscopyProgram(RAveragerProgram):
    """Resonator spectroscopy — sweeps resonator drive frequency.
    
    Additional cfg keys required:
        cfg['start']  : sweep start frequency (MHz)
        cfg['step']   : frequency step size (MHz)
        cfg['expts']  : number of sweep points
        cfg['reps']   : averages per point
    """
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg['resonator']['channel'], nqz=cfg['resonator']['nqz'])

        for ch in cfg['ADCs']:
            self.declare_readout(ch=ch,
                                 length=cfg['readout_length'],
                                 freq=cfg['resonator']['frequency'],
                                 gen_ch=cfg['resonator']['channel'])

        # --- sweep register setup ---
        self.r_rp   = self.ch_page(cfg['resonator']['channel'])
        self.r_freq = self.sreg(cfg['resonator']['channel'], 'freq')

        self.set_pulse_registers(ch=cfg['resonator']['channel'],
                                 style="const",
                                 freq=self.freq2reg(cfg['start'],
                                        gen_ch=cfg['resonator']['channel'],
                                        ro_ch=cfg['ADCs'][0]),
                                 phase=self.deg2reg(cfg['resonator']['phase']),
                                 gain=cfg['resonator']['gain'],
                                 length=cfg['resonator']['pulse_length'])

        self.sync_all(self.us2cycles(500))

    def body(self):
        cfg = self.cfg
        self.measure(pulse_ch=cfg['resonator']['channel'],
                     adcs=cfg['ADCs'],
                     adc_trig_offset=cfg['adc_trig_offset'],
                     wait=True,
                     syncdelay=self.us2cycles(cfg['relax_delay']))

    def update(self):
        self.mathi(self.r_rp, self.r_freq, self.r_freq, '+',
                   self.freq2reg(self.cfg['step'],
                                 gen_ch=self.cfg['resonator']['channel']))
