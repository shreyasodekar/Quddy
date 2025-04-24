# Quddy

## Description

A python package and measurement scripts based on [QICK](https://github.com/openquantumhardware/qick) (Quantum Instrumentation Control Kit) which is kit of firmware and software to use the Xilinx RFSOC boards and CW experiments using a VNA a and signal generator through QCODES. This package is tested on RFSOC4x2 but should work on all three of the newest RFSOC boards by Xilinx running QICK.

A single JSON file (config.json) contains all your experimental parameters and all the experimental data is saved in the Scripts/$expt type$/Data directory in HDF5 format. A simple tutorial on how to use the h5py package to extract your data from the HDF5 file is included in the Scripts directory. HDF5 file of every experiment contains a 'Metadata' dataset which contains the parameters passed by you in config.json and a 'datetime' dataset which contains the date and time of the start of the experiment.

## Installation

For seamlessness make sure you are running the same versions of the python packages on both the RFSOC board and the Host PC. (YES!! Even numpy version matters!!) pyproject.toml includes the dependencies of this package with downgraded versions which support qick==0.2.262. If you have a newer version of qick then you might need to manually check for the verisons of dependencies.
 
to install the package on your Host PC, go to the Package directory and run the following script in cmd (we reccommend making a new environment for using this package.)

```
pip install ./
```
You'll also have to install a package called [resonator](https://github.com/danielflanigan/resonator) by [Daniel Flanigan](https://github.com/danielflanigan). Install this package after installing Quddy.

Before running any scripts you need to initialize the pyro4 server on the RFSOC board. To do this, run this script in terminal on your RFSOC baord (easiest way to access the terminal on your board is to use jupyterlab)
```
python home/xilinx/jupyter_notebooks/qick/pyro4/pyro_service.py
```

Leave this terminal running and DO NOT INTERUPT. If this pyro_service.py script doesn't exist on your board by default then just follow the notebooks in the pyro4 directory. (Yes, now you can close the jupyterlab!)

Once you have installed the package and have initialized the pyro4 server on your RFSOC board, you can copy the Scripts direcctory to your prefffered location and run the experiment scripts in order.
