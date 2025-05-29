# -*- coding: utf-8 -*-
"""
Created on Sun May 25 12:36:46 2025

@author: frolovlab
"""

ranges = [
    {'start': 6.862e9, 'stop': 6.867e9, 'points': 10000},
    {'start': 7.225e9, 'stop': 7.228e9, 'points': 10000},
    {'start': 7.620e9, 'stop': 7.625e9, 'points': 10000},
    {'start': 8.072e9, 'stop': 8.078e9, 'points': 10000},
    {'start': 8.551e9, 'stop': 8.556e9, 'points': 10000},
    {'start': 8.568e9, 'stop': 8.575e9, 'points': 10000},
    ]


# for i in range(6):
#     # with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\C1_Single_tone.py") as file:
#     #     expt_cfg = {'start': ranges[i]['start'],
#     #             'stop': ranges[i]['stop'],
#     #             'points': ranges[i]['points']}
        
#     # with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\C1_1_Single_tone_powerdep.py") as file:
#     #     expt_cfg = {'f_start':  ranges[i]['start'],
#     #                 'f_stop':  ranges[i]['stop'],
#     #                 'f_points':  ranges[i]['points'],
#     #                 'p_start': -43,
#     #                 'p_stop': 19,
#     #                 'p_step' : 2
#     #                 }
    
#     with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\C1_3_Single_tone_tempdep.py") as file:    
#         expt_cfg = {'f_start':  ranges[i]['start'],
#                 'f_stop':  ranges[i]['stop'],
#                 'f_points':  ranges[i]['points'],
#                 't_start': 0.02,
#                 't_stop': 1.3,
#                 't_points' : 30
#                 }

#         exec(file.read())



####### For measuring all resonators in one single temp sweep.
temp_arr = np.linspace(0.02,1.3,20)

for j in temp_arr:
    Proteox.set_MC_T_and_wait(j, 0.005,0.005, 2)
    for i in range(6):
        # with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\C1_Single_tone.py") as file:
        #     expt_cfg = {'start': ranges[i]['start'],
        #             'stop': ranges[i]['stop'],
        #             'points': ranges[i]['points']}
        
        with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\config.json", 'r') as cfg:
            config = json.load(cfg)
        config['Device Name'] = f'R{str(i+1)}'
        with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\config.json", 'w') as cfg:
            json.dump(config, cfg, indent=4)
            
            
        with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\C1_1_Single_tone_powerdep.py") as file:
            expt_cfg = {'f_start':  ranges[i]['start'],
                        'f_stop':  ranges[i]['stop'],
                        'f_points':  ranges[i]['points'],
                        'p_start': -43,
                        'p_stop': 19,
                        'p_step' : 4
                        }
    
            exec(file.read())
            
Proteox.Mixing_Chamber_Temperature(0)