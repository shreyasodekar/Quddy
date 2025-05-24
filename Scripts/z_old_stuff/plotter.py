import sys
import os
import traceback
import h5py
import json
import time
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QComboBox, QPushButton, QFileDialog
from PyQt5.QtGui import QClipboard, QPixmap
from PyQt5.QtCore import Qt
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider
import matplotlib.animation as animation
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import win32com.client as win32

all_expts = [#old experiment names
             'E1_1_Single_tone_powerdep',
             'E1_2_Single_tone_gatedep',
             'E2_1_Two_tone_powerdep',
             'E2_1_Two_tone_gatedep',
             'E1_1_single_tone_powerdep',
             'E3_1_Pulse_probe_powerdep',
             
             #new experiment names
             'C1_Single_tone',
             'C1_1_Single_tone_powerdep',
             'C1_2_Single_tone_gatedep',
             'C2_Two_tone',
             'C2_1_Two_tone_powerdep',
             'C2_2_Two_tone_gatedep',
             
             'R0_TOF',
             'R1_Single_tone',
             'R1_1_Single_tone_powerdep',
             'R1_2_Single_tone_gatedep',
             'R2_Two_tone',
             'R2_1_Two_tone_powerdep',
             'R2_2_Two_tone_gatedep',
             'R3_Single_shot', #make a separate one
             'R4_Length_Rabi',
             'R4_Amplitude_Rabi',
             'R4_1_2dRabi',
             'R4_2_Chevron',
             'R5_T1',
             'R5_T2Ramsey',
             'R5_T2Echo'
             ] 

class Plotter(QMainWindow):
    def __init__(self, file_path=None):
        super().__init__()
        self.setWindowTitle("HDF5 Plotter")
        self.setGeometry(100, 100, 1600, 1200)

        self.centralWidget = QWidget(self)
        self.setCentralWidget(self.centralWidget)
        self.layout = QVBoxLayout(self.centralWidget)
        
        hbox = QHBoxLayout()
        
        self.label = QLabel("Drag and drop your HDF5 file here", self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("border: 2px dashed #aaa; padding: 20px; font-size: 28px;")
        self.layout.addWidget(self.label)

        self.combo_box = QComboBox(self)
        self.combo_box.setFixedWidth(300)
        self.combo_box.hide()
        hbox.addWidget(self.combo_box)
        hbox.addStretch() 
        
        self.copy_button = QPushButton('Copy Figure', self)
        self.copy_button.setFixedWidth(200)
        self.copy_button.clicked.connect(self.copy2clipboard)
        self.copy_button.hide()
        hbox.addWidget(self.copy_button)

        self.word_button = QPushButton('Send to docx', self)
        self.word_button.setFixedWidth(200)
        self.word_button.clicked.connect(self.copy2word)
        self.word_button.hide()
        hbox.addWidget(self.word_button)
        
        self.save_button = QPushButton('Save Figure', self)
        self.save_button.setFixedWidth(200)
        self.save_button.clicked.connect(self.save_button_click_event)
        self.save_button.hide()
        hbox.addWidget(self.save_button)
        
        self.layout.addLayout(hbox)
        
        self.figure = plt.figure(figsize = (16,12))
        self.canvas = FigureCanvas(self.figure)
        self.canvas.hide()
        self.layout.addWidget(self.canvas)
        
        self.setAcceptDrops(True)
        self.anim = None
        if file_path:
            self.load_and_plot_data(file_path)

    def save_button_click_event(self):
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Plot", "", "PNG Files (*.png);;PDF Files (*.pdf);;SVG Files (*.svg)")
        if save_path:
            self.figure.savefig(save_path)
            
    def copy2clipboard(self):
        temp_file = 'temp.png'
        self.figure.savefig(temp_file)
            
        clipboard = QApplication.clipboard()
        pixmap = QPixmap(temp_file)
        clipboard.setPixmap(pixmap, QClipboard.Clipboard)
        
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
    def copy2word(self):
        temp_file = 'temp.png'
        self.figure.savefig(temp_file)
            
        word = win32.Dispatch('Word.Application')
        doc = word.ActiveDocument
        word.Selection.GoTo(What=3, Which=-1)
        word.Visible = True
        selection = word.Selection
        picture = selection.InlineShapes.AddPicture(os.path.abspath(temp_file))
        picture.Width = 500 #648 
        picture.Height = 187.5 #243 
        doc.Save()
        
        if os.path.exists(temp_file):
            os.remove(temp_file)    
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        event.setDropAction(Qt.CopyAction)
        event.accept()

        file_path = event.mimeData().urls()[0].toLocalFile()

        self.load_and_plot_data(file_path)

    def load_and_plot_data(self, file_path):
        try:
            f = h5py.File(file_path,'r', libver = 'latest', swmr = True)
            metadata = json.loads(f['Metadata'][()].decode('utf-8'))
            exptname = [expt for expt in all_expts if expt in metadata["Expt ID"]][0]
            
            if exptname != None:    #Experiment specific axes
            
                ################################## 1D Experiments                
                if exptname == 'C1_Single_tone' or exptname == 'C2_Two_tone':
                    expttype = '1D'
                    exptinst = 'CW'
                    xs = f['Frequency'][:]/1e9
                    ax1_xlabel = 'Frequency (GHz)'
                  
                if exptname == 'R0_TOF':
                    expttype = '1D'
                    exptinst = 'RFSOC'
                    xs = f['Time'][:]
                    ax1_xlabel = 'Time (Clock ticks)'
                    
                if exptname == 'R1_Single_tone' or exptname == 'R2_Two_tone':
                    expttype = '1D'
                    exptinst = 'RFSOC'
                    xs = f['Frequency'][:]/1e9
                    ax1_xlabel = 'Frequency (GHz)'
                    
                if exptname == 'R4_Length_Rabi':
                    expttype = '1D'
                    exptinst = 'RFSOC'
                    xs = f['Pulse Length'][:]
                    ax1_xlabel = 'Pulse Length (ns)'
                    
                if exptname == 'R4_Amplitude_Rabi':
                    expttype = '1D'
                    exptinst = 'RFSOC'
                    xs = f['Gain'][:]  
                    ax1_xlabel = 'Gain (DAC units)'
                    
                if exptname == 'R5_T1' or exptname == 'R5_T2Ramsey' or exptname == 'R5_T2Echo':
                    expttype = '1D'
                    exptinst = 'RFSOC'
                    xs = f['Time'][:]
                    ax1_xlabel = 'Time (us)'
                    
                    
                ################################## 2D Experiments
                if exptname == 'C1_1_Single_tone_powerdep' or exptname == 'C2_1_Two_tone_powerdep':
                    expttype = '2D'
                    exptinst = 'CW'
                    xs = f['Frequency'][:]/1e9
                    ys = f['Power'][:]
                    ax1_xlabel = 'Frequency (GHz)'
                    ax1_ylabel = 'RF output power (dBm)'

                if exptname == 'R1_1_Single_tone_powerdep' or exptname == 'R2_1_Two_tone_powerdep':
                    expttype = '2D'
                    exptinst = 'RFSOC'
                    xs = f['Frequency'][:]/1e9
                    ys = f['Gain'][:]
                    ax1_xlabel = 'Frequency (GHz)'
                    ax1_ylabel = 'Gain (DAC units)'

                if exptname == 'R4_2_Chevron':
                    expttype = '2D'
                    exptinst = 'RFSOC'
                    xs = f['Frequency'][:]/1e9
                    ys = f['PUlse Length'][:]
                    ax1_xlabel = 'Frequency (GHz)'
                    ax1_ylabel = 'Pulse Length (ns)'

                    
                if exptname == 'C1_2_Single_tone_gatedep' or exptname == 'C2_2_Two_tone_gatedep':
                    expttype = '2D'
                    exptinst = 'CW'
                    xs = f['Frequency'][:]/1e9
                    ys = f['Gate Voltage'][:]
                    ax1_xlabel = 'Frequency (GHz)'
                    ax1_ylabel = 'Gate Voltage (mV)'

                if exptname == 'R1_2_Single_tone_gatedep' or exptname == 'R2_2_Two_tone_gatedep':
                    expttype = '2D'
                    exptinst = 'RFSOC'
                    xs = f['Frequency'][:]/1e9
                    ys = f['Gate Voltage'][:]
                    ax1_xlabel = 'Frequency (GHz)'
                    ax1_ylabel = 'Gate Voltage (mV)'
                    
                if exptname == 'R4_1_2dRabi':
                    expttype = '2D'
                    exptinst = 'RFSOC'
                    xs = f['Gain'][:]
                    ys = f['Pulse'][:]
                    ax1_xlabel = 'Gain (DAC units)'
                    ax1_ylabel = 'Pulse Length (ns)'
                    
            ########################
            
            # #Only for old experiment names. Legacy support XD. Comment out if using latest scripts!
            # expttype = '2D'
            # xs = f['Frequency'][:]
            # ys = f['Power'][:]
            # ax1_xlabel = 'Frequency (GHz)'
            # ax1_ylabel = 'RF output power (dBm)'
            
            ######################
            
            self.label.hide()
            self.canvas.show()
            self.figure.clear()
            self.combo_box.show()
            self.save_button.show()
            self.copy_button.show()
            self.word_button.show()
            
            if exptinst == 'CW' and expttype == '1D':
                self.combo_box.clear()
                self.combo_box.addItem("Plot S21 (dB)")
                self.combo_box.addItem("Plot \u2220S21 (deg)")
                self.combo_box.addItem("Plot R[S21]")
                self.combo_box.addItem("Plot I[S21]")
                self.combo_box.setCurrentIndex(0)
                self.resize(1200, 600)
                self.figure.set_size_inches(16, 6)
                self.figure.suptitle(metadata["Expt ID"], fontsize = 16)
                ax1 = self.figure.add_subplot(121)
                plt.subplots_adjust(bottom=0.2)
                self.figure.text(0.6, 0.0,'Metadata: \n \n'+json.dumps(metadata, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '{}"'}) , fontsize=10)
                
                def animate(i):
                    ax1.clear()
                    plot_option = self.combo_box.currentIndex()
                    ax1.set_xlabel(ax1_xlabel)
                    if plot_option == 0:
                        zs = 20*np.log10(np.abs(f['S21'][:]))
                        ax1.set_ylabel('S21 (dBm)')
                    elif plot_option == 1:
                        zs = np.angle(f['S21'][:], deg=True)
                        ax1.set_ylabel('\u2220S21 (deg)')
                    elif plot_option == 2:
                        zs = np.real(f['S21'][:])
                        ax1.set_ylabel('R[S21]')
                    elif plot_option == 3:
                        zs = np.imag(f['S21'][:])
                        ax1.set_ylabel('I[S21]')
                        
                    ax1.plot(xs, zs)
                    ax1.set_xlim([xs[0], xs[-1]])
                
                self.anim = animation.FuncAnimation(self.figure, animate, interval=100, cache_frame_data=False)
    
            if exptinst == 'CW' and expttype == '2D':
                self.combo_box.clear()
                self.combo_box.addItem("Plot S21 (dB)")
                self.combo_box.addItem("Plot \u2220S21 (deg)")
                self.combo_box.addItem("Plot R[S21]")
                self.combo_box.addItem("Plot I[S21]")
                self.combo_box.setCurrentIndex(0)
                self.resize(1600,1200)
                self.figure.suptitle(metadata["Expt ID"], fontsize = 16)
                ax1 = self.figure.add_subplot(221)
                ax2 = self.figure.add_subplot(222)
                ax3 = self.figure.add_subplot(223)
                plt.subplots_adjust(bottom=0.2)
                ys_slider = plt.axes([0.95, 0.574, 0.01, 0.305])
                xs_slider = plt.axes([0.125, 0.515, 0.3525, 0.013])
                self.figure.text(0.6, 0.0,'Metadata: \n \n'+json.dumps(metadata, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '{}"'}) , fontsize=10)
                
                slider1 = Slider(ys_slider, ax1_ylabel, valmin=0, valmax=len(ys)-1, valinit=0, valstep = 1, dragging = True, orientation = 'vertical')
                slider2 = Slider(xs_slider, ax1_xlabel, valmin=0, valmax=len(xs)-1, valinit=0, valstep = 1, dragging = True, orientation = 'horizontal')
        
                def animate(i):
                    ax1.clear()
                    ax2.clear()
                    ax3.clear()
                    plot_option = self.combo_box.currentIndex()
                    ax1.set_xlabel(ax1_xlabel)
                    ax1.set_ylabel(ax1_ylabel)
                    ax2.set_xlabel(ax1_xlabel)
                    ax3.set_xlabel(ax1_ylabel)
                    if plot_option == 0:
                        zs = 20*np.log10(np.abs(f['S21'][:]))
                        ax2.set_ylabel('S21 (dB)')
                        ax3.set_ylabel('S21 (dB)')
                    elif plot_option == 1:
                        zs = np.angle(f['S21'][:], deg=True)
                        ax2.set_ylabel('\u2220S21 (deg)')
                        ax3.set_ylabel('\u2220S21 (deg)')
                    elif plot_option == 2:
                        zs = np.real(f['S21'][:])
                        ax2.set_ylabel('R[S21]')
                        ax3.set_ylabel('R[S21]')
                    elif plot_option == 3:
                        zs = np.imag(f['S21'][:])
                        ax2.set_ylabel('I[S21]')
                        ax3.set_ylabel('I[S21]')
        
                    
                    slider1.valtext.set_text(f'{ys[slider1.val]:.2f}')
                    slider2.valtext.set_text(f'{xs[slider2.val]:.2e}')
                    ax1.pcolormesh(xs, ys, zs)
                    ax1.axhline(ys[slider1.val], color = 'r', lw=1, alpha = 0.75)
                    ax1.axvline(xs[slider2.val], color = 'b', lw=1, alpha = 0.75)
                    ax2.plot(xs, zs[slider1.val].T)
                    ax2.set_xlim([xs[0],xs[-1]])
                    ax3.plot(ys, zs.T[slider2.val].T)
                    ax3.set_xlim([ys[0],ys[-1]])

                    
                self.anim = animation.FuncAnimation(self.figure, animate, interval=100, cache_frame_data=False)
                slider1.on_changed(animate)
                slider2.on_changed(animate)
            
            
            if exptinst == 'RFSOC' and expttype == '1D':
                self.combo_box.clear()
                self.combo_box.addItem("Plot magnitude (a.u.)")
                self.combo_box.addItem("Plot Phase (deg)")
                self.combo_box.addItem("Plot I")
                self.combo_box.addItem("Plot Q")
                self.combo_box.setCurrentIndex(0)
                self.resize(1200, 600)
                self.figure.set_size_inches(16, 6)
                self.figure.suptitle(metadata["Expt ID"], fontsize = 16)
                ax1 = self.figure.add_subplot(121)
                plt.subplots_adjust(bottom=0.2)
                self.figure.text(0.6, 0.0,'Metadata: \n \n'+json.dumps(metadata, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '{}"'}) , fontsize=10)
                
                def animate(i):
                    ax1.clear()
                    plot_option = self.combo_box.currentIndex()
                    ax1.set_xlabel(ax1_xlabel)
                    if plot_option == 0:
                        zs = np.abs(f['S21'][:])
                        ax1.set_ylabel('Transmission (a.u.)')
                    elif plot_option == 1:
                        zs = np.angle(f['S21'][:], deg=True)
                        ax1.set_ylabel('Phase (deg)')
                    elif plot_option == 2:
                        zs = np.real(f['S21'][:])
                        ax1.set_ylabel('I (a.u.)')
                    elif plot_option == 3:
                        zs = np.imag(f['S21'][:])
                        ax1.set_ylabel('Q (a.u.)')
                        
                    ax1.plot(xs, zs)
                    ax1.set_xlim([xs[0], xs[-1]])
                
                self.anim = animation.FuncAnimation(self.figure, animate, interval=100, cache_frame_data=False)
    
            if exptinst == 'RFSOC' and expttype == '2D':    # 2D type plotter
                self.combo_box.clear()
                self.combo_box.addItem("Plot magnitude (a.u.)")
                self.combo_box.addItem("Plot Phase (deg)")
                self.combo_box.addItem("Plot I")
                self.combo_box.addItem("Plot Q")
                self.combo_box.setCurrentIndex(0)
                self.resize(1600,1200)
                self.figure.suptitle(metadata["Expt ID"], fontsize = 16)
                ax1 = self.figure.add_subplot(221)
                ax2 = self.figure.add_subplot(222)
                ax3 = self.figure.add_subplot(223)
                plt.subplots_adjust(bottom=0.2)
                ys_slider = plt.axes([0.95, 0.574, 0.01, 0.305])
                xs_slider = plt.axes([0.125, 0.515, 0.3525, 0.013])
                self.figure.text(0.6, 0.0,'Metadata: \n \n'+json.dumps(metadata, indent=4,separators = ('',' : ')).translate({ord(i): None for i in '{}"'}) , fontsize=10)
                
                slider1 = Slider(ys_slider, ax1_ylabel, valmin=0, valmax=len(ys)-1, valinit=0, valstep = 1, dragging = True, orientation = 'vertical')
                slider2 = Slider(xs_slider, ax1_xlabel, valmin=0, valmax=len(xs)-1, valinit=0, valstep = 1, dragging = True, orientation = 'horizontal')
        
                def animate(i):
                    ax1.clear()
                    ax2.clear()
                    ax3.clear()
                    plot_option = self.combo_box.currentIndex()
                    ax1.set_xlabel(ax1_xlabel)
                    ax1.set_ylabel(ax1_ylabel)
                    ax2.set_xlabel(ax1_xlabel)
                    ax3.set_xlabel(ax1_ylabel)
                    if plot_option == 0:
                        zs = np.abs(f['S21'][:])
                        ax2.set_ylabel('Transmission (a.u.)')
                        ax3.set_ylabel('Transmission (a.u.)')
                    elif plot_option == 1:
                        zs = np.angle(f['S21'][:], deg=True)
                        ax2.set_ylabel('Phase (deg)')
                        ax3.set_ylabel('Phase (deg)')
                    elif plot_option == 2:
                        zs = np.real(f['S21'][:])
                        ax2.set_ylabel('I (a.u.)')
                        ax3.set_ylabel('I (a.u.)')
                    elif plot_option == 3:
                        zs = np.imag(f['S21'][:])
                        ax2.set_ylabel('Q (a.u.)')
                        ax3.set_ylabel('Q (a.u.)')
        
                    
                    slider1.valtext.set_text(f'{ys[slider1.val]:.2f}')
                    slider2.valtext.set_text(f'{xs[slider2.val]:.2e}')
                    ax1.pcolormesh(xs, ys, zs)
                    ax1.axhline(ys[slider1.val], color = 'r', lw=1, alpha = 0.75)
                    ax1.axvline(xs[slider2.val], color = 'b', lw=1, alpha = 0.75)
                    ax2.plot(xs, zs[slider1.val].T)
                    ax2.set_xlim([xs[0],xs[-1]])
                    ax3.plot(ys, zs.T[slider2.val].T)
                    ax3.set_xlim([ys[0],ys[-1]])

                    
                self.anim = animation.FuncAnimation(self.figure, animate, interval=100, cache_frame_data=False)
                slider1.on_changed(animate)
                slider2.on_changed(animate)
            
        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__) 
            file_name, line_number, _, _ = tb[-1] 
            self.label.setText(f"Error: {e} (Line: {line_number})")
            self.label.show()  
            
if __name__ == "__main__":
    app = QApplication(sys.argv)
    file_path = sys.argv[1] if len(sys.argv) > 1 else None
    plotter = Plotter(file_path)
    plotter.show()
    sys.exit(app.exec_())
