from qick import *


class DirectDispersiveMonitoring(RAveragerProgram):
    """DirectDispersiveMonitoring — monitors the resonator response continuously. NO register is being swept.
    RAveragerProgram is used to ensure the next shot is collected immediately after relay_delay us after one. Hence, sweep register is not set up and update is empty.
    
    Notes:
        parameter   |         Purpose           |   OCS - Serniak et al.
        relax_delay |  time betweem each shot   |   200 us
        pulse_length|    integration time       |   4.16 us ~ 2600 Clock ticks
        readout_length = pulse_length + buffer

    Additional cfg keys required:
        cfg['expts']  : number of sweep points
        cfg['reps']   : 1 - Single shot measurement
    """
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg['resonator']['channel'], nqz=cfg['resonator']['nqz'])

        for ch in cfg['ADCs']:
            self.declare_readout(ch=ch,
                                 length=cfg['readout_length'],
                                 freq=cfg['resonator']['frequency'],
                                 gen_ch=cfg['resonator']['channel'])

        # # --- sweep register setup ---
        # self.r_rp   = self.ch_page(cfg['resonator']['channel'])
        # self.r_freq = self.sreg(cfg['resonator']['channel'], 'freq')

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
        self.measure(pulse_ch=cfg['resonator']['channel'],
                     adcs=cfg['ADCs'],
                     adc_trig_offset=cfg['adc_trig_offset'],
                     wait=True,
                     syncdelay=self.us2cycles(cfg['relax_delay']))

    def update(self):
        # self.mathi(self.r_rp, self.r_freq, self.r_freq, '+',
        #            self.freq2reg(self.cfg['step'],
        #                          gen_ch=self.cfg['resonator']['channel']))
        pass
