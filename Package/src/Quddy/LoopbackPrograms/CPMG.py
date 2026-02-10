from qick import *


class CPMGProgram(RAveragerProgram):
    """CPMG dynamical decoupling — sweeps the echo time τ.

    Sequence: π/2 — [τ — π(Y) — τ]×N — π/2 — measure

    Additional cfg keys required:
        cfg['start']       : sweep start echo time (µs)
        cfg['step']        : echo time step size (µs)
        cfg['expts']       : number of sweep points
        cfg['reps']        : averages per point
        cfg['qubit']['num_pi_pulses_in_CPMG'] : number of π refocusing pulses (N)
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

        # --- sweep register setup (time) ---
        self.q_rp   = self.ch_page(cfg['qubit']['channel'])
        self.r_wait = 7
        self.safe_regwi(self.q_rp, self.r_wait,
                        self.us2cycles(cfg['start']))

        # Rx (π/2)
        self.add_gauss(ch=cfg['qubit']['channel'],
                       name="Rx",
                       sigma=self.us2cycles(cfg['qubit']['sigma']),
                       length=self.us2cycles(cfg['qubit']['sigma']))

        # Ry (π)
        self.add_gauss(ch=cfg['qubit']['channel'],
                       name="Ry",
                       sigma=self.us2cycles(cfg['qubit']['sigma']),
                       length=self.us2cycles(cfg['qubit']['sigma']) * 3)

        self.default_pulse_registers(ch=cfg['qubit']['channel'],
                                     style="arb",
                                     freq=self.freq2reg(cfg['qubit']['frequency'],
                                            gen_ch=cfg['qubit']['channel']),
                                     gain=cfg['qubit']['gain'])

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
        # π/2 (X)
        self.set_pulse_registers(ch=cfg['qubit']['channel'],
                                 waveform='Rx',
                                 phase=self.deg2reg(cfg['qubit']['phase']))
        self.pulse(ch=cfg['qubit']['channel'])

        # [τ — π(Y) — τ] × N
        for _ in range(cfg['qubit']['num_pi_pulses_in_CPMG']):
            self.sync_all()
            self.sync(self.q_rp, self.r_wait)            # τ

            self.set_pulse_registers(ch=cfg['qubit']['channel'],
                                     waveform='Ry',
                                     phase=self.deg2reg(cfg['qubit']['phase'] + 90))
            self.pulse(ch=cfg['qubit']['channel'])

            self.sync_all()
            self.sync(self.q_rp, self.r_wait)            # τ

        # π/2 (X)
        self.set_pulse_registers(ch=cfg['qubit']['channel'],
                                 waveform='Rx',
                                 phase=self.deg2reg(cfg['qubit']['phase']))
        self.pulse(ch=cfg['qubit']['channel'])

        self.sync_all(self.us2cycles(cfg['qubit']['sync_time']))

        self.measure(pulse_ch=cfg['resonator']['channel'],
                     adcs=cfg['ADCs'],
                     adc_trig_offset=cfg['adc_trig_offset'],
                     wait=True,
                     syncdelay=self.us2cycles(cfg['relax_delay']))

    def update(self):
        self.mathi(self.q_rp, self.r_wait, self.r_wait, '+',
                   self.us2cycles(self.cfg['step']))
