from qick import *


class SingleShotProgram(RAveragerProgram):
    """Single-shot g/e discrimination — steps qubit gain (0 → π) over 2 expts.

    Uses cfg['qubit']['gain'] as the step:
        expt 0 → gain = 0 (ground state)
        expt 1 → gain = π-pulse gain (excited state)
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

        cfg['start'] = 0
        cfg['step']  = cfg['qubit']['gain']
        cfg['expts'] = 2

        self.q_rp   = self.ch_page(cfg['qubit']['channel'])
        self.r_gain = self.sreg(cfg['qubit']['channel'], 'gain')

        self.add_gauss(ch=cfg['qubit']['channel'],
                       name="qubit",
                       sigma=self.us2cycles(cfg['qubit']['pulse_length'] / 4),
                       length=self.us2cycles(cfg['qubit']['pulse_length']))

        self.set_pulse_registers(ch=cfg['qubit']['channel'],
                                 style="arb",
                                 freq=self.freq2reg(cfg['qubit']['frequency'],
                                        gen_ch=cfg['qubit']['channel']),
                                 phase=self.deg2reg(cfg['qubit']['phase']),
                                 gain=cfg['start'],
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
        self.sync_all()

        self.measure(pulse_ch=cfg['resonator']['channel'],
                     adcs=cfg['ADCs'],
                     adc_trig_offset=cfg['adc_trig_offset'],
                     wait=True,
                     syncdelay=self.us2cycles(cfg['relax_delay']))

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg['step'])

    def acquire(self, soc, progress=False):
        super().acquire(soc, progress=progress)
        return self.collect_shots()

    def collect_shots(self):
        cfg = self.cfg
        shots_i0 = self.di_buf[0].reshape((cfg['expts'], cfg['reps'])) / cfg['readout_length']
        shots_q0 = self.dq_buf[0].reshape((cfg['expts'], cfg['reps'])) / cfg['readout_length']
        shots_i1 = self.di_buf[1].reshape((cfg['expts'], cfg['reps'])) / cfg['readout_length']
        shots_q1 = self.dq_buf[1].reshape((cfg['expts'], cfg['reps'])) / cfg['readout_length']
        return shots_i0, shots_q0, shots_i1, shots_q1

    def analyze(self, shots_i, shots_q):
        import matplotlib.pyplot as plt
        plt.subplot(111, xlabel='I', ylabel='Q', title='Single Shot Histogram')
        plt.plot(shots_i[0], shots_q[0], '.', label='g')
        plt.plot(shots_i[1], shots_q[1], '.', label='e')
        plt.legend()
        plt.gca().set_aspect('equal', 'datalim')
