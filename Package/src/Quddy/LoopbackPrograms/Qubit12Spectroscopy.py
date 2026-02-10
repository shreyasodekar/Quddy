from qick import *


class Qubit12SpectroscopyProgram(RAveragerProgram):
    """0→1→2 three-tone spectroscopy — sweeps the 1→2 drive frequency.

    Fixed π-pulse on 0→1 transition, then swept probe on 1→2.

    Additional cfg keys required:
        cfg['start']  : sweep start frequency for 1→2 probe (MHz)
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
        self.q_rp     = self.ch_page(cfg['qubit']['channel'])
        self.r_freq   = self.sreg(cfg['qubit']['channel'], 'freq')
        # spare register to hold the swept 1→2 frequency
        self.r_freq2  = 7
        self.safe_regwi(self.q_rp, self.r_freq2,
                        self.freq2reg(cfg['start'],
                                      gen_ch=cfg['qubit']['channel']))

        self.add_gauss(ch=cfg['qubit']['channel'],
                       name="qubit",
                       sigma=self.us2cycles(cfg['qubit']['sigma']),
                       length=self.us2cycles(cfg['qubit']['sigma']) * 4)

        self.add_gauss(ch=cfg['qubit']['channel'],
                       name="qubit12",
                       sigma=self.us2cycles(cfg['qubit']['sigma12']),
                       length=self.us2cycles(cfg['qubit']['sigma12']) * 4)

        self.default_pulse_registers(ch=cfg['qubit']['channel'],
                                     style="arb",
                                     gain=cfg['qubit']['gain'],
                                     phase=cfg['qubit']['phase'])

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
        # 0→1 pulse at fixed qubit frequency
        self.set_pulse_registers(ch=cfg['qubit']['channel'],
                                 waveform='qubit',
                                 freq=self.freq2reg(cfg['qubit']['frequency'],
                                        gen_ch=cfg['qubit']['channel']))
        self.pulse(ch=cfg['qubit']['channel'])

        self.sync_all(self.us2cycles(cfg['qubit']['wait_time']))

        # 1→2 pulse at swept frequency: copy r_freq2 → r_freq, then fire
        self.mathi(self.q_rp, self.r_freq, self.r_freq2, '+', 0)
        self.set_pulse_registers(ch=cfg['qubit']['channel'],
                                 waveform='qubit12')
        self.pulse(ch=cfg['qubit']['channel'])

        self.sync_all(self.us2cycles(0.05))

        self.measure(pulse_ch=cfg['resonator']['channel'],
                     adcs=cfg['ADCs'],
                     adc_trig_offset=cfg['adc_trig_offset'],
                     wait=True,
                     syncdelay=self.us2cycles(cfg['relax_delay']))

    def update(self):
        self.mathi(self.q_rp, self.r_freq2, self.r_freq2, '+',
                   self.freq2reg(self.cfg['step'],
                                 gen_ch=self.cfg['qubit']['channel']))
