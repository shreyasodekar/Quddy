from qick import *


class QubitSpectroscopyProgram(RAveragerProgram):
    """Two-tone spectroscopy with Gaussian qubit pulse — sweeps qubit drive frequency.

    Additional cfg keys required:
        cfg['start']  : sweep start frequency (MHz)
        cfg['step']   : frequency step size (MHz)
        cfg['expts']  : number of sweep points
        cfg['reps']   : averages per point
    """
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg['resonator']['channel'], nqz=cfg['resonator']['nqz'])
        self.declare_gen(ch=cfg['qubit']['channel'],     nqz=cfg['qubit']['nqz'])

        for ch in cfg['ADCs']:
            self.declare_readout(ch=ch,
                                 length=cfg['readout_length'],
                                 freq=cfg['resonator']['frequency'],
                                 gen_ch=cfg['resonator']['channel'])

        # --- sweep register setup ---
        self.q_rp   = self.ch_page(cfg['qubit']['channel'])
        self.r_freq = self.sreg(cfg['qubit']['channel'], 'freq')

        self.add_gauss(ch=cfg['qubit']['channel'],
                       name="qubit",
                       sigma=self.us2cycles(cfg['qubit']['sigma']),
                       length=self.us2cycles(cfg['qubit']['sigma']) * 4)

        self.set_pulse_registers(ch=cfg['qubit']['channel'],
                                 style="arb",
                                 freq=self.freq2reg(cfg['start'],
                                        gen_ch=cfg['qubit']['channel']),
                                 phase=self.deg2reg(cfg['qubit']['phase']),
                                 gain=cfg['qubit']['gain'],
                                 waveform="qubit")

        self.set_pulse_registers(ch=cfg['resonator']['channel'],
                                 style="const",
                                 freq=self.freq2reg(cfg['resonator']['frequency'],
                                        gen_ch=cfg['resonator']['channel'],
                                        ro_ch=cfg['ADCs'][0]),
                                 phase=self.deg2reg(cfg['resonator']['phase']),
                                 gain=cfg['resonator']['gain'],
                                 length=cfg['resonator']['pulse_length'])

        self.sync_all(self.us2cycles(500))

    def body(self):
        cfg = self.cfg
        self.pulse(ch=cfg['qubit']['channel'])
        self.sync_all(self.us2cycles(cfg['qubit']['wait_time']))

        self.measure(pulse_ch=cfg['resonator']['channel'],
                     adcs=cfg['ADCs'],
                     adc_trig_offset=cfg['adc_trig_offset'],
                     wait=True,
                     syncdelay=self.us2cycles(cfg['relax_delay']))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+',
                   self.freq2reg(self.cfg['step'],
                                 gen_ch=self.cfg['qubit']['channel']))
