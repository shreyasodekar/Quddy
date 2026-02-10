from qick import *


class LengthRabiProgram(RAveragerProgram):
    """Length Rabi — sweeps qubit pulse duration.

    Uses a constant (flat-top) qubit pulse so that the length register
    can be swept directly by the firmware.

    Sequence: qubit pulse (variable length) — measure

    Additional cfg keys required:
        cfg['start']  : sweep start length (µs)
        cfg['step']   : length step size (µs)
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

        # --- sweep register setup (length) ---
        self.q_rp    = self.ch_page(cfg['qubit']['channel'])
        self.r_length = self.sreg(cfg['qubit']['channel'], 'length')

        self.set_pulse_registers(ch=cfg['qubit']['channel'],
                                 style="const",
                                 freq=self.freq2reg(cfg['qubit']['frequency'],
                                        gen_ch=cfg['qubit']['channel']),
                                 phase=self.deg2reg(cfg['qubit']['phase']),
                                 gain=cfg['qubit']['gain'],
                                 length=self.us2cycles(cfg['start']))

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
        self.mathi(self.q_rp, self.r_length, self.r_length, '+',
                   self.us2cycles(self.cfg['step']))
