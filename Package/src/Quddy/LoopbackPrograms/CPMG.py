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
                        self.us2cycles(cfg['start']/2))

        # Rx (π/2) - half-pulse_length
        self.add_gauss(ch=cfg['qubit']['channel'],
                       name="Rx",
                       sigma=self.us2cycles(cfg['qubit']['pulse_length'] / (2*4)),
                       length=self.us2cycles(cfg['qubit']['pulse_length'] / 2))

        # Ry (π) - full-pulse_length
        self.add_gauss(ch=cfg['qubit']['channel'],
                       name="Ry",
                       sigma=self.us2cycles(cfg['qubit']['pulse_length']/4),
                       length=self.us2cycles(cfg['qubit']['pulse_length']))

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
        ## CPMG loop requirements
        cpmg_count = 16
        c_i = 17

        cfg = self.cfg
        # π/2 (X)
        self.set_pulse_registers(ch=cfg['qubit']['channel'],
                                 waveform='Rx',
                                 phase=self.deg2reg(cfg['qubit']['phase']))
        self.pulse(ch=cfg['qubit']['channel'])

        # π (Y)
        self.set_pulse_registers(ch=cfg['qubit']['channel'],
                                    waveform='Ry',
                                    phase=self.deg2reg(cfg['qubit']['phase'] + 90))
        
        self.regwi(0, cpmg_count, 0)
        self.regwi(0, c_i, self.cfg['CPMG order']-1)

        self.label('LOOP_CPMG')

        #### This need to be in a loop. [wait(tau/2n) --- pulse(pi) --- wait (tau/2)]
        self.sync_all(self.q_rp, self.r_wait)            # τ/2 -> because r_wait is initialized as start/2
        self.pulse(ch=cfg['qubit']['channel'])           #        and updated by step/2 over interations.
        self.sync_all(self.q_rp, self.r_wait)            # τ/2 
        #####

        self.mathi(0, cpmg_count, cpmg_count, "+", 1)
        self.memwi(0, cpmg_count, self.COUNTER_ADDR)
        self.loopnz(0, c_i, 'LOOP_CPMG')

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
                   self.us2cycles(self.cfg['step']/2))
