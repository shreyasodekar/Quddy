# -*- coding: utf-8 -*-
"""
Created on Sun May 25 12:36:46 2025

@author: frolovlab
"""
import warnings
warnings.filterwarnings("ignore")
# ranges = [
#     {'start': 6.553e9, 'stop': 6.559e9, 'points': 10000},
#     {'start': 6.864e9, 'stop': 6.870e9, 'points': 10000},
#     {'start': 7.227e9, 'stop': 7.233e9, 'points': 10000},
#     {'start': 7.624e9, 'stop': 7.630e9, 'points': 10000},
#     {'start': 8.072e9, 'stop': 8.078e9, 'points': 10000},
#     {'start': 8.552e9, 'stop': 8.558e9, 'points': 10000},
#     ]

ranges = [
    {'start': 6.550e9, 'stop': 6.557e9, 'points': 10000},
    {'start': 6.861e9, 'stop': 6.868e9, 'points': 10000},
    {'start': 7.224e9, 'stop': 7.231e9, 'points': 10000},
    {'start': 7.621e9, 'stop': 7.628e9, 'points': 10000},
    {'start': 8.069e9, 'stop': 8.076e9, 'points': 10000},
    {'start': 8.549e9, 'stop': 8.556e9, 'points': 10000},
    ]

# for i in range(6):
    
#     with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\config.json", 'r') as cfg:
#         config = json.load(cfg)
#     config['Device Name'] = f'R{str(i+1)}'
#     with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\config.json", 'w') as cfg:
#         json.dump(config, cfg, indent=4)
    
#     with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\C1_Single_tone.py") as file:
#         expt_cfg = {'start': ranges[i]['start'],
#                 'stop': ranges[i]['stop'],
#                 'points': ranges[i]['points']}
        
#     # with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\C1_1_Single_tone_powerdep.py") as file:
#     #     expt_cfg = {'f_start':  ranges[i]['start'],
#     #                 'f_stop':  ranges[i]['stop'],
#     #                 'f_points':  ranges[i]['points'],
#     #                 'p_start': 0,
#     #                 'p_stop': 19,
#     #                 'p_step' : 2
#     #                 }
    
#     # with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\C1_3_Single_tone_tempdep.py") as file:    
#     #     expt_cfg = {'f_start':  ranges[i]['start'],
#     #             'f_stop':  ranges[i]['stop'],
#     #             'f_points':  ranges[i]['points'],
#     #             't_start': 0.02,
#     #             't_stop': 1.3,
#     #             't_points' : 30
#     #             }

#         exec(file.read())



####### For measuring all resonators in one single temp sweep.
# temp_arr = np.linspace(1.5,7,20)
# temp_arr = np.arange(0.02,6,0.06736842105263158)

# for j in temp_arr[20:]:
#     Proteox.set_MC_T_and_wait(j, 0.01,0.01, 1)
#     for i in range(6):
#         # with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\C1_Single_tone.py") as file:
#         #     expt_cfg = {'start': ranges[i]['start'],
#         #             'stop': ranges[i]['stop'],
#         #             'points': ranges[i]['points']}
        
#         with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\config.json", 'r') as cfg:
#             config = json.load(cfg)
#         config['Device Name'] = f'R{str(i+1)}'
#         with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\config.json", 'w') as cfg:
#             json.dump(config, cfg, indent=4)
            
            
#         with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\C1_1_Single_tone_powerdep.py") as file:
#             expt_cfg = {'f_start':  ranges[i]['start'],
#                         'f_stop':  ranges[i]['stop'],
#                         'f_points':  ranges[i]['points'],
#                         'p_start': -43,
#                         'p_stop': 19,
#                         'p_step' : 4
#                         }
    
#             exec(file.read())
            
# Proteox.Mixing_Chamber_Temperature(0)


########## For B-field sweep
B_arr1 = np.linspace(0.0,-0.05,5)
B_arr2 = np.linspace(-0.05, 1, 105)
B_arr = np.concatenate((B_arr1, B_arr2))
fr_lastrun = [6553233438.105705, 6863179886.388637, 7224985544.653782, 7622310211.945709, 8070450367.727152, 8551467012.35677]

for j in tqdm(range(1,len(B_arr))):
    
    Proteox.set_magnet_target(0,0,0,B_arr[j],'RATE',0.01,False)
    time.sleep(10)
    Proteox.sweep_small_field_step('Z')
    time.sleep(65)
    Proteox.wait_until_field_stable()
    
    for i in range(6):
        
        with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\config.json", 'r') as cfg:
            config = json.load(cfg)
        config['Device Name'] = f'R{str(i+1)}'
        with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\config.json", 'w') as cfg:
            json.dump(config, cfg, indent=4)
            
        with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\C1_Single_tone.py") as file:
            expt_cfg = {'start': fr_lastrun[i]-3e6,
                    'stop': fr_lastrun[i]+3e6,
                    'points': ranges[i]['points']}
            
        # with open(r"C:\Users\frolovlab\Documents\Python Scripts\msmt_new\CW\C1_1_Single_tone_powerdep.py") as file:
        #     expt_cfg = {'f_start':  ranges[i]['start'],
        #                 'f_stop':  ranges[i]['stop'],
        #                 'f_points':  ranges[i]['points'],
        #                 'p_start': -43,
        #                 'p_stop': 19,
        #                 'p_step' : 4
        #                 }
    
            exec(file.read())
            fr_lastrun[i] = resonator.resonance_frequency
            
# Proteox.set_magnet_target(0,0,0,0,'RATE',0.01,False)
# time.sleep(5)
# Proteox.sweep_small_field_step('Z')
# time.sleep(10)
# Proteox.wait_until_field_stable()