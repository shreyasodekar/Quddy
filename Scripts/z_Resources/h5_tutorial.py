import numpy as np
import matplotlib.pyplot as plt
import h5py
import json
from pprint import pprint

path = os.path.abspath('./RFSOC/Data/')
expname = 'single_tone'

with h5py.File(path+'/'expname,'r') as f: 
    x_pts = f['Frequency'][()]
    i_vals = f['I'][()]         #[()] is important as the with... method closes the h5 file after the block ends
    q_vals = f['Q'][()]         #if you only care about getting the nparrays back then this works. 
    metadata = json.loads(f['Metadata'][()].decode('utf-8'))
    amp = f['Amp'][()]

# Want to retrive the metadata too?
metadata = json.loads(metadata.decode('ASCII'))
print(json.dumps(metadata, indent=4))

#Plot your previously saved data
fig = plt.figure(figsize=(8,6))
plt.plot(x_pts,i_vals,'.-', label='I')
# plt.plot(x_pts,q_vals, label='Q')
# plt.plot(x_pts, amp,'.-', label='Amp')
plt.xlabel('Pulse Length (Clock Ticks)')
plt.ylabel('Amp (ADC level)')
plt.title('Length Rabi')
plt.figtext(0.5, -0.3, 'Metadata: \n \n'+'\n'.join([f'{key}: {value}' for key, value in metadata.items()]), 
            wrap=True, horizontalalignment='center', fontsize=10)


# plt.legend()
# # plt.title('This is how you get back stored data from hdf5 files.')
# # plt.show()

# x_pts[np.argmax(i_vals)]
