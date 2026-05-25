# -*- coding: utf-8 -*-
"""
Created on Sun May 25 12:36:46 2025

@author: frolovlab
"""
import warnings
warnings.filterwarnings("ignore")

show_plot = True
ask_save_to_doc = False

cpmg_orders = [1, 2, 4, 10, 50, 65, 85, 100, 150, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
num_iter = 5
T2CPMGs = np.zeros((len(cpmg_orders), num_iter))

for j in range(num_iter):
    for i in tqdm(range(len(cpmg_orders))):
        
        # Change CPMG order
        with open(r"C:\Users\frolovlab\Documents\Python Scripts\Quddy_sandbox\Scripts\RFSOC\config.json", 'r') as cfg:
            config = json.load(cfg)
            config["CPMG order"] = cpmg_orders[i]
        with open(r"C:\Users\frolovlab\Documents\Python Scripts\Quddy_sandbox\Scripts\RFSOC\config.json", 'w') as cfg:
            json.dump(config, cfg, indent=4)
        
        # # Perform Two tone
        # with open(r"C:\Users\frolovlab\Documents\Python Scripts\Quddy_sandbox\Scripts\RFSOC\R2_Two_tone.py") as file:
        #     exec(file.read())
        #     temp = popt[0]
        
        # # Change Drive frequency according to the two tone
        # with open(r"C:\Users\frolovlab\Documents\Python Scripts\Quddy_sandbox\Scripts\RFSOC\config.json", 'r') as cfg:
        #     config = json.load(cfg)
        #     config['qubit']['frequency'] = temp
        # with open(r"C:\Users\frolovlab\Documents\Python Scripts\Quddy_sandbox\Scripts\RFSOC\config.json", 'w') as cfg:
        #     json.dump(config, cfg, indent=4)

        # # Perform Length Rabi      
        # with open(r"C:\Users\frolovlab\Documents\Python Scripts\Quddy_sandbox\Scripts\RFSOC\R4_Length_Rabi.py") as file:
        #     exec(file.read())
        #     temp = (np.pi/2 + np.abs(popt[4]))/popt[2]
        
        # # Change pulse sigma
        # with open(r"C:\Users\frolovlab\Documents\Python Scripts\Quddy_sandbox\Scripts\RFSOC\config.json", 'r') as cfg:
        #     config = json.load(cfg)
        #     config['qubit']['sigma'] = temp
        # with open(r"C:\Users\frolovlab\Documents\Python Scripts\Quddy_sandbox\Scripts\RFSOC\config.json", 'w') as cfg:
        #     json.dump(config, cfg, indent=4)
    
        with open(r"C:\Users\frolovlab\Documents\Python Scripts\Quddy_sandbox\Scripts\RFSOC\R5_CPMG.py") as file:
            exec(file.read())
            T2CPMGs[i,j] = popt[2]
            
        
plt.semilogx(cpmg_orders, T2CPMGs)
plt.xlabel('Number of pulses')
plt.ylabel(r'$T_2^{CPMG}$ ($\mu$s)')
plt.show()

plt.semilogx(cpmg_orders, np.mean(T2CPMGs, axis=1))
plt.xlabel('Number of pulses')
plt.ylabel(r'avg $T_2^{CPMG}$ ($\mu$s)')