"""
HDF5 Live Plotter for Quddy
===========================

Drag-and-drop visualization tool for experiment data.
Supports live updating during measurements (SWMR mode).
Automatic experiment detection with manual axis selection fallback.
Collapsible sidebar for configuration options.

Author: Shreyas Odekar
"""

import sys
import os
import traceback
import h5py
import json
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple, Callable, Dict, List
from enum import Enum, auto

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout,
    QWidget, QComboBox, QPushButton, QFileDialog, QCheckBox,
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QRadioButton,
    QButtonGroup, QSpinBox, QDoubleSpinBox, QLineEdit, QMessageBox,
    QFrame, QScrollArea, QSplitter, QSlider, QToolButton, QSizePolicy,
    QColorDialog, QListWidget, QListWidgetItem
)
from PyQt5.QtGui import QPixmap, QIcon, QFont
from PyQt5.QtCore import Qt, QTimer, QSize, QPropertyAnimation, QEasingCurve

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.widgets import Slider as MplSlider
import matplotlib.colors as mcolors

# Optional: win32com for Word integration (Windows only)
try:
    import win32com.client as win32
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


class ExperimentType(Enum):
    CW_1D = auto()
    CW_2D = auto()
    RFSOC_1D = auto()
    RFSOC_2D = auto()
    CUSTOM_1D = auto()
    CUSTOM_2D = auto()


@dataclass
class ExperimentSpec:
    """Specification for how to plot an experiment type."""
    exp_type: ExperimentType
    x_key: str
    x_label: str
    x_scale: float = 1.0
    y_key: Optional[str] = None
    y_label: Optional[str] = None
    y_scale: float = 1.0
    data_key: str = 'S21'


@dataclass
class PlotSettings:
    """Settings for plot appearance."""
    colormap: str = 'viridis'
    line_color: str = '#1f77b4'
    line_width: float = 1.5
    marker_style: str = 'None'  # None, o, s, ^, v, D, etc.
    marker_size: float = 4.0
    marker_color: str = '#1f77b4'
    grid_enabled: bool = True
    grid_alpha: float = 0.3
    grid_width: float = 0.5
    autoscale: bool = True
    vmin: Optional[float] = None
    vmax: Optional[float] = None
    # Tick settings
    tick_size: float = 6.0
    tick_width: float = 1.0
    tick_font_size: float = 10.0
    x_tick_count: int = 0  # 0 = auto
    y_tick_count: int = 0  # 0 = auto
    # Label settings
    x_label_text: str = ''  # Empty = use default from spec
    y_label_text: str = ''
    z_label_text: str = ''  # For 2D plots - colorbar label
    label_size: float = 12.0
    # Title settings
    title_text: str = ''
    title_size: float = 14.0
    # Y-axis padding for 1D plots (fraction of data range)
    y_padding: float = 0.05
    
    def get_clim(self, data: np.ndarray) -> Tuple[Optional[float], Optional[float]]:
        """Get color limits, using data range if autoscale or values not set."""
        if self.autoscale:
            return None, None
        vmin = self.vmin if self.vmin is not None else np.nanmin(data)
        vmax = self.vmax if self.vmax is not None else np.nanmax(data)
        # Ensure vmin < vmax
        if vmin >= vmax:
            vmin, vmax = np.nanmin(data), np.nanmax(data)
        return vmin, vmax


# Registry of experiment types
EXPERIMENT_REGISTRY: Dict[str, ExperimentSpec] = {
    # CW 1D experiments
    'C1_Single_tone': ExperimentSpec(
        ExperimentType.CW_1D, 'Frequency', 'Frequency (Hz)'),
    'C2_Two_tone': ExperimentSpec(
        ExperimentType.CW_1D, 'Frequency', 'Frequency (Hz)'),
    # CW 2D experiments
    'C1_1_Single_tone_powerdep': ExperimentSpec(
        ExperimentType.CW_2D, 'Frequency', 'Frequency (Hz)', 1.0,
        'Power', 'RF output power (dBm)'),
    'C1_2_Single_tone_gatedep': ExperimentSpec(
        ExperimentType.CW_2D, 'Frequency', 'Frequency (Hz)', 1.0,
        'Gate Voltage', 'Gate Voltage (mV)'),
    'C2_1_Two_tone_powerdep': ExperimentSpec(
        ExperimentType.CW_2D, 'Frequency', 'Frequency (Hz)', 1.0,
        'Power', 'RF output power (dBm)'),
    'C2_2_Two_tone_gatedep': ExperimentSpec(
        ExperimentType.CW_2D, 'Frequency', 'Frequency (Hz)', 1.0,
        'Gate Voltage', 'Gate Voltage (mV)'),
    # RFSOC 1D experiments
    'R0_TOF': ExperimentSpec(
        ExperimentType.RFSOC_1D, 'Time', 'Time (Clock ticks)'),
    'R1_Single_tone': ExperimentSpec(
        ExperimentType.RFSOC_1D, 'Frequency', 'Frequency (MHz)'),
    'R2_Two_tone': ExperimentSpec(
        ExperimentType.RFSOC_1D, 'Frequency', 'Frequency (MHz)'),
    'R4_Length_Rabi': ExperimentSpec(
        ExperimentType.RFSOC_1D, 'Pulse Length', 'Pulse Length (μs)'),
    'R4_Amplitude_Rabi': ExperimentSpec(
        ExperimentType.RFSOC_1D, 'Gain', 'Gain (DAC units)'),
    'R5_T1': ExperimentSpec(
        ExperimentType.RFSOC_1D, 'Time', 'Time (μs)'),
    'R5_T2Ramsey': ExperimentSpec(
        ExperimentType.RFSOC_1D, 'Time', 'Time (μs)'),
    'R5_T2Echo': ExperimentSpec(
        ExperimentType.RFSOC_1D, 'Time', 'Time (μs)'),
    # RFSOC 2D experiments
    'R1_1_Single_tone_powerdep': ExperimentSpec(
        ExperimentType.RFSOC_2D, 'Frequency', 'Frequency (MHz)', 1.0,
        'Gain', 'Gain (DAC units)'),
    'R1_2_Single_tone_gatedep': ExperimentSpec(
        ExperimentType.RFSOC_2D, 'Frequency', 'Frequency (MHz)', 1.0,
        'Gate Voltage', 'Gate Voltage (mV)'),
    'R2_1_Two_tone_powerdep': ExperimentSpec(
        ExperimentType.RFSOC_2D, 'Frequency', 'Frequency (MHz)', 1.0,
        'Gain', 'Gain (DAC units)'),
    'R2_2_Two_tone_gatedep': ExperimentSpec(
        ExperimentType.RFSOC_2D, 'Frequency', 'Frequency (MHz)', 1.0,
        'Gate Voltage', 'Gate Voltage (mV)'),
    'R4_1_2dRabi': ExperimentSpec(
        ExperimentType.RFSOC_2D, 'Gain', 'Gain (DAC units)', 1.0,
        'Pulse Length', 'Pulse Length (μs)'),
    'R4_2_Chevron': ExperimentSpec(
        ExperimentType.RFSOC_2D, 'Frequency', 'Frequency (MHz)', 1.0,
        'Pulse Length', 'Pulse Length (μs)'),
}


class DataTransforms:
    """Data transformation functions for different plot types."""

    @staticmethod
    def get_cw_transforms() -> List[Tuple[str, str, Callable]]:
        return [
            ('S21 (dB)', 'S21 (dB)', lambda d: 20 * np.log10(np.abs(d) + 1e-15)),
            ('∠S21 (deg)', '∠S21 (deg)', lambda d: np.angle(d, deg=True)),
            ('Re[S21]', 'Re[S21]', lambda d: np.real(d)),
            ('Im[S21]', 'Im[S21]', lambda d: np.imag(d)),
        ]

    @staticmethod
    def get_rfsoc_transforms() -> List[Tuple[str, str, Callable]]:
        return [
            ('Magnitude (a.u.)', 'Transmission (a.u.)', lambda d: np.abs(d)),
            ('Phase (deg)', 'Phase (deg)', lambda d: np.angle(d, deg=True)),
            ('I', 'I (a.u.)', lambda d: np.real(d)),
            ('Q', 'Q (a.u.)', lambda d: np.imag(d)),
        ]

    @staticmethod
    def get_generic_transforms() -> List[Tuple[str, str, Callable]]:
        return [
            ('Magnitude', 'Magnitude', lambda d: np.abs(d)),
            ('Magnitude (dB)', 'Magnitude (dB)', lambda d: 20 * np.log10(np.abs(d) + 1e-15)),
            ('Phase (deg)', 'Phase (deg)', lambda d: np.angle(d, deg=True)),
            ('Real', 'Real', lambda d: np.real(d)),
            ('Imaginary', 'Imaginary', lambda d: np.imag(d)),
            ('Raw', 'Raw', lambda d: d),
        ]


class CollapsibleSection(QWidget):
    """A collapsible section widget with header and content."""

    def __init__(self, title: str, parent=None, start_collapsed: bool = False):
        super().__init__(parent)
        self.is_collapsed = start_collapsed

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header button
        self.header = QToolButton()
        self.header.setText(f"{'▶' if start_collapsed else '▼'} {title}")
        self.header.setCheckable(True)
        self.header.setChecked(not start_collapsed)
        self.header.setStyleSheet("""
            QToolButton {
                background-color: #e8e8e8;
                border: none;
                padding: 8px;
                text-align: left;
                font-weight: bold;
                font-size: 11px;
            }
            QToolButton:hover {
                background-color: #d8d8d8;
            }
        """)
        self.header.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.header.clicked.connect(self._toggle)
        layout.addWidget(self.header)

        # Content widget
        self.content = QWidget()
        self.content.setVisible(not start_collapsed)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_layout.setSpacing(6)
        layout.addWidget(self.content)

    def _toggle(self):
        self.is_collapsed = not self.is_collapsed
        self.content.setVisible(not self.is_collapsed)
        title = self.header.text()[2:]  # Remove arrow
        self.header.setText(f"{'▶' if self.is_collapsed else '▼'} {title}")

    def add_widget(self, widget: QWidget):
        self.content_layout.addWidget(widget)

    def add_layout(self, layout):
        self.content_layout.addLayout(layout)


class Sidebar(QWidget):
    """Collapsible sidebar with configuration sections."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = PlotSettings()
        self.callbacks = {}

        self.setFixedWidth(280)
        self.setStyleSheet("""
            QLabel {
                font-size: 11px;
            }
            QPushButton {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
            QComboBox {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QCheckBox {
                font-size: 11px;
            }
            QSpinBox, QDoubleSpinBox {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px;
                font-size: 11px;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px;
                font-size: 11px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scroll area for sidebar content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_content)
        self.scroll_layout.setContentsMargins(8, 8, 8, 8)
        self.scroll_layout.setSpacing(8)

        # === Data Section ===
        data_section = CollapsibleSection("Data")
        
        # Transform selector
        transform_layout = QVBoxLayout()
        transform_layout.addWidget(QLabel("Transform:"))
        self.transform_combo = QComboBox()
        self.transform_combo.currentIndexChanged.connect(
            lambda i: self._emit('transform_changed', i))
        transform_layout.addWidget(self.transform_combo)
        data_section.add_layout(transform_layout)

        # Live update
        self.live_checkbox = QCheckBox("Live Update")
        self.live_checkbox.setChecked(False)
        self.live_checkbox.toggled.connect(
            lambda c: self._emit('live_toggled', c))
        data_section.add_widget(self.live_checkbox)

        # Update interval
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("Interval (ms):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(100, 5000)
        self.interval_spin.setValue(500)
        self.interval_spin.setSingleStep(100)
        self.interval_spin.valueChanged.connect(
            lambda v: self._emit('interval_changed', v))
        interval_layout.addWidget(self.interval_spin)
        data_section.add_layout(interval_layout)

        # Stitch files button
        self.stitch_btn = QPushButton("📎 Stitch Files...")
        self.stitch_btn.setToolTip("Combine multiple HDF5 files of the same experiment type")
        self.stitch_btn.clicked.connect(lambda: self._emit('stitch_files'))
        data_section.add_widget(self.stitch_btn)

        # Linecuts toggle (for 2D only) - moved from Appearance
        self.linecuts_checkbox = QCheckBox("Show Linecuts")
        self.linecuts_checkbox.setChecked(False)
        self.linecuts_checkbox.toggled.connect(
            lambda c: self._emit('linecuts_toggled', c))
        data_section.add_widget(self.linecuts_checkbox)

        # Callout mode toggle - moved from Appearance
        self.callout_checkbox = QCheckBox("Callout Mode")
        self.callout_checkbox.setChecked(False)
        self.callout_checkbox.setToolTip("Click on plot to add annotation markers")
        self.callout_checkbox.toggled.connect(
            lambda c: self._emit('callout_toggled', c))
        data_section.add_widget(self.callout_checkbox)

        # Clear callouts button - moved from Appearance
        self.clear_callouts_btn = QPushButton("Clear Callouts")
        self.clear_callouts_btn.clicked.connect(lambda: self._emit('clear_callouts'))
        data_section.add_widget(self.clear_callouts_btn)

        self.scroll_layout.addWidget(data_section)

        # === Color Scale Section (for 2D) ===
        self.scale_section = CollapsibleSection("Color Scale", start_collapsed=True)

        # Colormap (moved from Appearance to top of Color Scale)
        cmap_layout = QVBoxLayout()
        cmap_layout.addWidget(QLabel("Colormap:"))
        self.cmap_combo = QComboBox()
        colormaps = ['viridis', 'viridis_r', 'plasma', 'plasma_r', 
                     'inferno', 'inferno_r', 'magma', 'magma_r', 
                     'cividis', 'cividis_r', 'coolwarm', 'coolwarm_r',
                     'RdBu', 'RdBu_r', 'seismic', 'seismic_r', 
                     'hot', 'hot_r', 'jet', 'jet_r',
                     'gray', 'gray_r', 'bone', 'bone_r']
        self.cmap_combo.addItems(colormaps)
        self.cmap_combo.currentTextChanged.connect(self._on_colormap_changed)
        cmap_layout.addWidget(self.cmap_combo)
        self.scale_section.add_layout(cmap_layout)

        self.autoscale_checkbox = QCheckBox("Auto Scale")
        self.autoscale_checkbox.setChecked(True)
        self.autoscale_checkbox.toggled.connect(self._on_autoscale_toggled)
        self.scale_section.add_widget(self.autoscale_checkbox)

        # Manual scale controls
        self.scale_controls = QWidget()
        scale_layout = QFormLayout(self.scale_controls)
        scale_layout.setContentsMargins(0, 0, 0, 0)

        self.vmin_spin = QDoubleSpinBox()
        self.vmin_spin.setRange(-1e10, 1e10)
        self.vmin_spin.setDecimals(3)
        self.vmin_spin.valueChanged.connect(self._on_scale_changed)
        scale_layout.addRow("Min:", self.vmin_spin)

        self.vmax_spin = QDoubleSpinBox()
        self.vmax_spin.setRange(-1e10, 1e10)
        self.vmax_spin.setDecimals(3)
        self.vmax_spin.valueChanged.connect(self._on_scale_changed)
        scale_layout.addRow("Max:", self.vmax_spin)

        self.vstep_spin = QDoubleSpinBox()
        self.vstep_spin.setRange(1e-10, 1e10)
        self.vstep_spin.setDecimals(6)
        self.vstep_spin.setValue(1.0)
        self.vstep_spin.valueChanged.connect(self._on_step_changed)
        scale_layout.addRow("Step:", self.vstep_spin)

        self.scale_controls.setEnabled(False)
        self.scale_section.add_widget(self.scale_controls)

        # Rescale button - resets limits to current data range
        self.rescale_btn = QPushButton("Rescale to Data")
        self.rescale_btn.setToolTip("Reset color limits to current data range")
        self.rescale_btn.clicked.connect(lambda: self._emit('rescale'))
        self.scale_section.add_widget(self.rescale_btn)

        self.scroll_layout.addWidget(self.scale_section)

        # === Axes Section ===
        axes_section = CollapsibleSection("Axes", start_collapsed=True)

        self.config_axes_btn = QPushButton("Configure Axes...")
        self.config_axes_btn.clicked.connect(
            lambda: self._emit('configure_axes'))
        axes_section.add_widget(self.config_axes_btn)

        # Zoom controls
        zoom_layout = QHBoxLayout()
        self.zoom_btn = QPushButton("🔍 Zoom")
        self.zoom_btn.setCheckable(True)
        self.zoom_btn.setToolTip("Click and drag on plot to zoom")
        self.zoom_btn.toggled.connect(lambda c: self._emit('zoom_toggled', c))
        zoom_layout.addWidget(self.zoom_btn)
        
        self.reset_zoom_btn = QPushButton("↩ Reset")
        self.reset_zoom_btn.setToolTip("Reset to full view")
        self.reset_zoom_btn.clicked.connect(lambda: self._emit('reset_zoom'))
        zoom_layout.addWidget(self.reset_zoom_btn)
        axes_section.add_layout(zoom_layout)

        # Axis flip controls
        flip_layout = QHBoxLayout()
        self.flip_x_btn = QPushButton("⇄ Flip X")
        self.flip_x_btn.setToolTip("Flip X-axis direction")
        self.flip_x_btn.clicked.connect(lambda: self._emit('flip_x'))
        flip_layout.addWidget(self.flip_x_btn)
        
        self.flip_y_btn = QPushButton("⇅ Flip Y")
        self.flip_y_btn.setToolTip("Flip Y-axis direction")
        self.flip_y_btn.clicked.connect(lambda: self._emit('flip_y'))
        flip_layout.addWidget(self.flip_y_btn)
        axes_section.add_layout(flip_layout)
        
        # Interchange X and Y axes
        self.interchange_btn = QPushButton("Interchange x ⇄ y")
        self.interchange_btn.setToolTip("Swap X and Y axes and transpose data")
        self.interchange_btn.clicked.connect(lambda: self._emit('interchange_xy'))
        axes_section.add_widget(self.interchange_btn)

        self.scroll_layout.addWidget(axes_section)

        # === Appearance Section (merged with former Ticks section) ===
        appearance_section = CollapsibleSection("Appearance", start_collapsed=True)

        # Show Grid
        self.grid_checkbox = QCheckBox("Show Grid")
        self.grid_checkbox.setChecked(True)
        self.grid_checkbox.toggled.connect(self._on_grid_toggled)
        appearance_section.add_widget(self.grid_checkbox)

        # Grid width
        grid_width_layout = QHBoxLayout()
        grid_width_layout.addWidget(QLabel("Grid Width:"))
        self.grid_width_spin = QDoubleSpinBox()
        self.grid_width_spin.setRange(0.1, 5.0)
        self.grid_width_spin.setValue(0.5)
        self.grid_width_spin.setSingleStep(0.1)
        self.grid_width_spin.valueChanged.connect(self._on_grid_width_changed)
        grid_width_layout.addWidget(self.grid_width_spin)
        appearance_section.add_layout(grid_width_layout)

        # Tick size
        tick_size_layout = QHBoxLayout()
        tick_size_layout.addWidget(QLabel("Tick Size:"))
        self.tick_size_spin = QDoubleSpinBox()
        self.tick_size_spin.setRange(0, 20.0)
        self.tick_size_spin.setValue(6.0)
        self.tick_size_spin.setSingleStep(1.0)
        self.tick_size_spin.valueChanged.connect(self._on_tick_size_changed)
        tick_size_layout.addWidget(self.tick_size_spin)
        appearance_section.add_layout(tick_size_layout)

        # Tick width
        tick_width_layout = QHBoxLayout()
        tick_width_layout.addWidget(QLabel("Tick Width:"))
        self.tick_width_spin = QDoubleSpinBox()
        self.tick_width_spin.setRange(0.1, 5.0)
        self.tick_width_spin.setValue(1.0)
        self.tick_width_spin.setSingleStep(0.5)
        self.tick_width_spin.valueChanged.connect(self._on_tick_width_changed)
        tick_width_layout.addWidget(self.tick_width_spin)
        appearance_section.add_layout(tick_width_layout)

        # Tick font size
        tick_font_layout = QHBoxLayout()
        tick_font_layout.addWidget(QLabel("Tick Font:"))
        self.tick_font_spin = QDoubleSpinBox()
        self.tick_font_spin.setRange(4, 20)
        self.tick_font_spin.setValue(10.0)
        self.tick_font_spin.setSingleStep(1.0)
        self.tick_font_spin.valueChanged.connect(self._on_tick_font_size_changed)
        tick_font_layout.addWidget(self.tick_font_spin)
        appearance_section.add_layout(tick_font_layout)

        # X tick count
        x_tick_layout = QHBoxLayout()
        x_tick_layout.addWidget(QLabel("X Ticks:"))
        self.x_tick_spin = QSpinBox()
        self.x_tick_spin.setRange(0, 20)
        self.x_tick_spin.setValue(0)
        self.x_tick_spin.setSpecialValueText("Auto")
        self.x_tick_spin.setToolTip("Number of X-axis ticks (0 = auto)")
        self.x_tick_spin.valueChanged.connect(self._on_x_tick_count_changed)
        x_tick_layout.addWidget(self.x_tick_spin)
        appearance_section.add_layout(x_tick_layout)

        # Y tick count
        y_tick_layout = QHBoxLayout()
        y_tick_layout.addWidget(QLabel("Y Ticks:"))
        self.y_tick_spin = QSpinBox()
        self.y_tick_spin.setRange(0, 20)
        self.y_tick_spin.setValue(0)
        self.y_tick_spin.setSpecialValueText("Auto")
        self.y_tick_spin.setToolTip("Number of Y-axis ticks (0 = auto)")
        self.y_tick_spin.valueChanged.connect(self._on_y_tick_count_changed)
        y_tick_layout.addWidget(self.y_tick_spin)
        appearance_section.add_layout(y_tick_layout)

        # Separator
        appearance_section.add_widget(QLabel(""))  # spacer

        # X label
        x_label_layout = QVBoxLayout()
        x_label_layout.addWidget(QLabel("X Label:"))
        self.x_label_edit = QLineEdit()
        self.x_label_edit.setPlaceholderText("(use default)")
        self.x_label_edit.textChanged.connect(self._on_x_label_changed)
        x_label_layout.addWidget(self.x_label_edit)
        appearance_section.add_layout(x_label_layout)

        # Y label
        y_label_layout = QVBoxLayout()
        y_label_layout.addWidget(QLabel("Y Label:"))
        self.y_label_edit = QLineEdit()
        self.y_label_edit.setPlaceholderText("(use default)")
        self.y_label_edit.textChanged.connect(self._on_y_label_changed)
        y_label_layout.addWidget(self.y_label_edit)
        appearance_section.add_layout(y_label_layout)

        # Z label (for 2D plots - colorbar label)
        self.z_label_widget = QWidget()
        z_label_layout = QVBoxLayout(self.z_label_widget)
        z_label_layout.setContentsMargins(0, 0, 0, 0)
        z_label_layout.addWidget(QLabel("Z Label (colorbar):"))
        self.z_label_edit = QLineEdit()
        self.z_label_edit.setPlaceholderText("(use default)")
        self.z_label_edit.textChanged.connect(self._on_z_label_changed)
        z_label_layout.addWidget(self.z_label_edit)
        appearance_section.add_widget(self.z_label_widget)

        # Label size
        label_size_layout = QHBoxLayout()
        label_size_layout.addWidget(QLabel("Label Size:"))
        self.label_size_spin = QDoubleSpinBox()
        self.label_size_spin.setRange(6, 24)
        self.label_size_spin.setValue(12.0)
        self.label_size_spin.setSingleStep(1.0)
        self.label_size_spin.valueChanged.connect(self._on_label_size_changed)
        label_size_layout.addWidget(self.label_size_spin)
        appearance_section.add_layout(label_size_layout)

        # Separator
        appearance_section.add_widget(QLabel(""))  # spacer

        # Title
        title_layout = QVBoxLayout()
        title_layout.addWidget(QLabel("Title:"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("(no title)")
        self.title_edit.textChanged.connect(self._on_title_changed)
        title_layout.addWidget(self.title_edit)
        appearance_section.add_layout(title_layout)

        # Title size
        title_size_layout = QHBoxLayout()
        title_size_layout.addWidget(QLabel("Title Size:"))
        self.title_size_spin = QDoubleSpinBox()
        self.title_size_spin.setRange(6, 30)
        self.title_size_spin.setValue(14.0)
        self.title_size_spin.setSingleStep(1.0)
        self.title_size_spin.valueChanged.connect(self._on_title_size_changed)
        title_size_layout.addWidget(self.title_size_spin)
        appearance_section.add_layout(title_size_layout)

        # Separator
        appearance_section.add_widget(QLabel(""))  # spacer

        # Line color and Marker color side by side
        colors_layout = QHBoxLayout()
        
        # Line color
        line_color_layout = QVBoxLayout()
        line_color_layout.addWidget(QLabel("Line Color:"))
        self.color_button = QPushButton()
        self.color_button.setFixedSize(50, 24)
        self.color_button.setStyleSheet(f"background-color: {self.settings.line_color};")
        self.color_button.clicked.connect(self._pick_color)
        line_color_layout.addWidget(self.color_button)
        colors_layout.addLayout(line_color_layout)
        
        # Marker color
        marker_color_layout = QVBoxLayout()
        marker_color_layout.addWidget(QLabel("Marker Color:"))
        self.marker_color_button = QPushButton()
        self.marker_color_button.setFixedSize(50, 24)
        self.marker_color_button.setStyleSheet(f"background-color: {self.settings.marker_color};")
        self.marker_color_button.clicked.connect(self._pick_marker_color)
        marker_color_layout.addWidget(self.marker_color_button)
        colors_layout.addLayout(marker_color_layout)
        
        colors_layout.addStretch()
        appearance_section.add_layout(colors_layout)

        # Line width
        lw_layout = QHBoxLayout()
        lw_layout.addWidget(QLabel("Line Width:"))
        self.linewidth_spin = QDoubleSpinBox()
        self.linewidth_spin.setRange(0, 5.0)
        self.linewidth_spin.setValue(1.5)
        self.linewidth_spin.setSingleStep(0.5)
        self.linewidth_spin.valueChanged.connect(self._on_linewidth_changed)
        lw_layout.addWidget(self.linewidth_spin)
        appearance_section.add_layout(lw_layout)

        # Marker style
        marker_layout = QHBoxLayout()
        marker_layout.addWidget(QLabel("Marker:"))
        self.marker_combo = QComboBox()
        # Marker styles: (display name, matplotlib marker code)
        self.marker_styles = [
            ('None', 'None'),
            ('Circle', 'o'),
            ('Square', 's'),
            ('Triangle Up', '^'),
            ('Triangle Down', 'v'),
            ('Diamond', 'D'),
            ('Plus', '+'),
            ('Cross', 'x'),
            ('Star', '*'),
            ('Point', '.'),
        ]
        for name, _ in self.marker_styles:
            self.marker_combo.addItem(name)
        self.marker_combo.currentIndexChanged.connect(self._on_marker_style_changed)
        marker_layout.addWidget(self.marker_combo)
        appearance_section.add_layout(marker_layout)

        # Marker size
        ms_layout = QHBoxLayout()
        ms_layout.addWidget(QLabel("Marker Size:"))
        self.markersize_spin = QDoubleSpinBox()
        self.markersize_spin.setRange(0, 20.0)
        self.markersize_spin.setValue(4.0)
        self.markersize_spin.setSingleStep(1.0)
        self.markersize_spin.valueChanged.connect(self._on_markersize_changed)
        ms_layout.addWidget(self.markersize_spin)
        appearance_section.add_layout(ms_layout)

        # Separator
        appearance_section.add_widget(QLabel(""))  # spacer

        # Figure size button
        self.figsize_btn = QPushButton("Figure Size...")
        self.figsize_btn.setToolTip("Change figure dimensions")
        self.figsize_btn.clicked.connect(lambda: self._emit('change_figsize'))
        appearance_section.add_widget(self.figsize_btn)

        # Set axis limits button
        self.set_limits_btn = QPushButton("Set Limits...")
        self.set_limits_btn.setToolTip("Manually set X and Y axis limits")
        self.set_limits_btn.clicked.connect(lambda: self._emit('set_limits'))
        appearance_section.add_widget(self.set_limits_btn)

        self.scroll_layout.addWidget(appearance_section)

        # === Export Section ===
        export_section = CollapsibleSection("Export", start_collapsed=True)

        self.copy_btn = QPushButton("📋 Copy to Clipboard")
        self.copy_btn.clicked.connect(lambda: self._emit('copy_clipboard'))
        export_section.add_widget(self.copy_btn)

        self.copy_metadata_btn = QPushButton("📋 Copy Metadata")
        self.copy_metadata_btn.clicked.connect(lambda: self._emit('copy_metadata'))
        export_section.add_widget(self.copy_metadata_btn)

        self.copy_metadata_dict_btn = QPushButton("📋 Copy Metadata (dict)")
        self.copy_metadata_dict_btn.clicked.connect(lambda: self._emit('copy_metadata_dict'))
        export_section.add_widget(self.copy_metadata_dict_btn)

        self.save_btn = QPushButton("💾 Save Figure...")
        self.save_btn.clicked.connect(lambda: self._emit('save_figure'))
        export_section.add_widget(self.save_btn)

        if HAS_WIN32:
            self.word_btn = QPushButton("📄 Send to Word")
            self.word_btn.clicked.connect(lambda: self._emit('send_word'))
            export_section.add_widget(self.word_btn)

        self.scroll_layout.addWidget(export_section)

        # === Metadata Section ===
        self.metadata_section = CollapsibleSection("Metadata", start_collapsed=True)
        self.metadata_label = QLabel("No file loaded")
        self.metadata_label.setWordWrap(True)
        self.metadata_label.setStyleSheet("font-size: 10px; color: #000000;")
        self.metadata_section.add_widget(self.metadata_label)

        self.scroll_layout.addWidget(self.metadata_section)

        # Add stretch at bottom
        self.scroll_layout.addStretch()

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

    def set_callback(self, name: str, callback: Callable):
        """Register a callback for sidebar events."""
        self.callbacks[name] = callback

    def _emit(self, name: str, *args):
        """Emit a callback event."""
        if name in self.callbacks:
            self.callbacks[name](*args)

    def _pick_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.settings.line_color = color.name()
            self.color_button.setStyleSheet(f"background-color: {color.name()};")
            self._emit('settings_changed', self.settings)

    def _on_colormap_changed(self, cmap: str):
        self.settings.colormap = cmap
        self._emit('settings_changed', self.settings)

    def _on_linewidth_changed(self, width: float):
        self.settings.line_width = width
        self._emit('settings_changed', self.settings)

    def _on_marker_style_changed(self, index: int):
        _, marker_code = self.marker_styles[index]
        self.settings.marker_style = marker_code
        self._emit('settings_changed', self.settings)

    def _on_markersize_changed(self, size: float):
        self.settings.marker_size = size
        self._emit('settings_changed', self.settings)

    def _pick_marker_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.settings.marker_color = color.name()
            self.marker_color_button.setStyleSheet(f"background-color: {color.name()};")
            self._emit('settings_changed', self.settings)

    def _on_grid_toggled(self, enabled: bool):
        self.settings.grid_enabled = enabled
        self._emit('settings_changed', self.settings)

    def _on_autoscale_toggled(self, auto: bool):
        self.settings.autoscale = auto
        self.scale_controls.setEnabled(not auto)
        self._emit('settings_changed', self.settings)

    def _on_scale_changed(self):
        self.settings.vmin = self.vmin_spin.value()
        self.settings.vmax = self.vmax_spin.value()
        self._emit('settings_changed', self.settings)

    def _on_step_changed(self, step: float):
        self.vmin_spin.setSingleStep(step)
        self.vmax_spin.setSingleStep(step)

    # Tick settings callbacks
    def _on_tick_size_changed(self, size: float):
        self.settings.tick_size = size
        self._emit('settings_changed', self.settings)

    def _on_tick_width_changed(self, width: float):
        self.settings.tick_width = width
        self._emit('settings_changed', self.settings)

    def _on_tick_font_size_changed(self, size: float):
        self.settings.tick_font_size = size
        self._emit('settings_changed', self.settings)

    def _on_grid_width_changed(self, width: float):
        self.settings.grid_width = width
        self._emit('settings_changed', self.settings)

    def _on_x_tick_count_changed(self, count: int):
        self.settings.x_tick_count = count
        self._emit('settings_changed', self.settings)

    def _on_y_tick_count_changed(self, count: int):
        self.settings.y_tick_count = count
        self._emit('settings_changed', self.settings)

    def _on_x_label_changed(self, text: str):
        self.settings.x_label_text = text
        self._emit('settings_changed', self.settings)

    def _on_y_label_changed(self, text: str):
        self.settings.y_label_text = text
        self._emit('settings_changed', self.settings)

    def _on_z_label_changed(self, text: str):
        self.settings.z_label_text = text
        self._emit('settings_changed', self.settings)

    def _on_label_size_changed(self, size: float):
        self.settings.label_size = size
        self._emit('settings_changed', self.settings)

    def _on_title_changed(self, text: str):
        self.settings.title_text = text
        self._emit('settings_changed', self.settings)

    def _on_title_size_changed(self, size: float):
        self.settings.title_size = size
        self._emit('settings_changed', self.settings)

    def set_transforms(self, transforms: List[Tuple[str, str, Callable]]):
        """Update available transforms."""
        self.transform_combo.clear()
        for label, _, _ in transforms:
            self.transform_combo.addItem(f"Plot {label}")

    def set_metadata(self, metadata_str: str):
        """Update metadata display."""
        self.metadata_label.setText(metadata_str)

    def set_2d_mode(self, is_2d: bool):
        """Show/hide 2D-specific controls."""
        self.scale_section.setVisible(is_2d)
        self.linecuts_checkbox.setVisible(is_2d)
        self.z_label_widget.setVisible(is_2d)
        # Flip Y and Interchange are now available for both 1D and 2D plots
    
    def update_scale_range(self, vmin: float, vmax: float):
        """Update the scale spinboxes with data range."""
        # Block signals to prevent triggering updates while setting values
        self.vmin_spin.blockSignals(True)
        self.vmax_spin.blockSignals(True)
        
        self.vmin_spin.setValue(vmin)
        self.vmax_spin.setValue(vmax)
        self.settings.vmin = vmin
        self.settings.vmax = vmax
        
        self.vmin_spin.blockSignals(False)
        self.vmax_spin.blockSignals(False)


class AxisSelectionDialog(QDialog):
    """Dialog for manual axis selection."""

    def __init__(self, h5file: h5py.File, metadata: dict,
                 detected_spec: Optional[ExperimentSpec] = None, parent=None):
        super().__init__(parent)
        self.h5file = h5file
        self.metadata = metadata
        self.detected_spec = detected_spec
        self.result_spec: Optional[ExperimentSpec] = None

        self.setWindowTitle("Configure Plot Axes")
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        info_label = QLabel(f"<b>File:</b> {self.metadata.get('Expt ID', 'Unknown')}")
        layout.addWidget(info_label)

        datasets = self._get_available_datasets()
        datasets_info = QLabel(f"<b>Available datasets:</b> {', '.join(datasets)}")
        datasets_info.setWordWrap(True)
        layout.addWidget(datasets_info)

        if self.detected_spec:
            self.use_detected_group = QGroupBox("Use Detected Settings")
            self.use_detected_group.setCheckable(True)
            self.use_detected_group.setChecked(True)
            detected_layout = QFormLayout()
            detected_layout.addRow("X-axis:", QLabel(f"{self.detected_spec.x_key} ({self.detected_spec.x_label})"))
            if self.detected_spec.y_key:
                detected_layout.addRow("Y-axis:", QLabel(f"{self.detected_spec.y_key} ({self.detected_spec.y_label})"))
                detected_layout.addRow("Type:", QLabel("2D"))
            else:
                detected_layout.addRow("Type:", QLabel("1D"))
            self.use_detected_group.setLayout(detected_layout)
            layout.addWidget(self.use_detected_group)
            self.use_detected_group.toggled.connect(self._on_detected_toggled)

        self.manual_group = QGroupBox("Manual Configuration")
        if self.detected_spec:
            self.manual_group.setCheckable(True)
            self.manual_group.setChecked(False)
        manual_layout = QFormLayout()

        type_layout = QHBoxLayout()
        self.type_1d = QRadioButton("1D Plot")
        self.type_2d = QRadioButton("2D Plot")
        self.type_1d.setChecked(True)
        self.type_group = QButtonGroup()
        self.type_group.addButton(self.type_1d)
        self.type_group.addButton(self.type_2d)
        type_layout.addWidget(self.type_1d)
        type_layout.addWidget(self.type_2d)
        type_layout.addStretch()
        manual_layout.addRow("Plot type:", type_layout)
        self.type_1d.toggled.connect(self._on_type_changed)

        self.data_combo = QComboBox()
        self.data_combo.addItems(datasets)
        if 'S21' in datasets:
            self.data_combo.setCurrentText('S21')
        manual_layout.addRow("Data dataset:", self.data_combo)

        x_group = QGroupBox("X-Axis")
        x_layout = QFormLayout()
        self.x_key_combo = QComboBox()
        self.x_key_combo.addItems(datasets)
        self.x_key_combo.setEditable(True)
        if 'Frequency' in datasets:
            self.x_key_combo.setCurrentText('Frequency')
        x_layout.addRow("Dataset:", self.x_key_combo)
        self.x_label_edit = QLineEdit("X")
        x_layout.addRow("Label:", self.x_label_edit)
        self.x_scale_spin = QDoubleSpinBox()
        self.x_scale_spin.setDecimals(12)
        self.x_scale_spin.setRange(1e-15, 1e15)
        self.x_scale_spin.setValue(1.0)
        x_layout.addRow("Scale factor:", self.x_scale_spin)

        x_scale_presets = QHBoxLayout()
        for name, val in [("Hz→GHz", 1e-9), ("s→μs", 1e6), ("s→ns", 1e9), ("1.0", 1.0)]:
            btn = QPushButton(name)
            btn.setFixedWidth(70)
            btn.clicked.connect(lambda checked, v=val: self.x_scale_spin.setValue(v))
            x_scale_presets.addWidget(btn)
        x_scale_presets.addStretch()
        x_layout.addRow("Presets:", x_scale_presets)
        x_group.setLayout(x_layout)
        manual_layout.addRow(x_group)

        self.y_group = QGroupBox("Y-Axis (for 2D plots)")
        y_layout = QFormLayout()
        self.y_key_combo = QComboBox()
        self.y_key_combo.addItems(datasets)
        self.y_key_combo.setEditable(True)
        if 'Power' in datasets:
            self.y_key_combo.setCurrentText('Power')
        elif 'Gate Voltage' in datasets:
            self.y_key_combo.setCurrentText('Gate Voltage')
        y_layout.addRow("Dataset:", self.y_key_combo)
        self.y_label_edit = QLineEdit("Y")
        y_layout.addRow("Label:", self.y_label_edit)
        self.y_scale_spin = QDoubleSpinBox()
        self.y_scale_spin.setDecimals(12)
        self.y_scale_spin.setRange(1e-15, 1e15)
        self.y_scale_spin.setValue(1.0)
        y_layout.addRow("Scale factor:", self.y_scale_spin)

        y_scale_presets = QHBoxLayout()
        for name, val in [("V→mV", 1e3), ("Hz→GHz", 1e-9), ("1.0", 1.0)]:
            btn = QPushButton(name)
            btn.setFixedWidth(70)
            btn.clicked.connect(lambda checked, v=val: self.y_scale_spin.setValue(v))
            y_scale_presets.addWidget(btn)
        y_scale_presets.addStretch()
        y_layout.addRow("Presets:", y_scale_presets)
        self.y_group.setLayout(y_layout)
        self.y_group.setEnabled(False)
        manual_layout.addRow(self.y_group)

        inst_layout = QHBoxLayout()
        self.inst_cw = QRadioButton("CW (VNA)")
        self.inst_rfsoc = QRadioButton("RFSOC")
        self.inst_generic = QRadioButton("Generic")
        self.inst_generic.setChecked(True)
        self.inst_group = QButtonGroup()
        self.inst_group.addButton(self.inst_cw)
        self.inst_group.addButton(self.inst_rfsoc)
        self.inst_group.addButton(self.inst_generic)
        inst_layout.addWidget(self.inst_cw)
        inst_layout.addWidget(self.inst_rfsoc)
        inst_layout.addWidget(self.inst_generic)
        inst_layout.addStretch()
        manual_layout.addRow("Data type:", inst_layout)

        self.manual_group.setLayout(manual_layout)
        layout.addWidget(self.manual_group)

        if self.detected_spec:
            self.manual_group.toggled.connect(self._on_manual_toggled)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.x_key_combo.currentTextChanged.connect(
            lambda t: self.x_label_edit.setText(t) if self.x_label_edit.text() in ("X", "") else None)
        self.y_key_combo.currentTextChanged.connect(
            lambda t: self.y_label_edit.setText(t) if self.y_label_edit.text() in ("Y", "") else None)

    def _get_available_datasets(self) -> List[str]:
        datasets = []
        def visitor(name, obj):
            if isinstance(obj, h5py.Dataset) and name.lower() != 'metadata':
                datasets.append(name)
        self.h5file.visititems(visitor)
        return sorted(datasets)

    def _on_type_changed(self, is_1d: bool):
        self.y_group.setEnabled(not is_1d)

    def _on_detected_toggled(self, checked: bool):
        if checked:
            self.manual_group.setChecked(False)

    def _on_manual_toggled(self, checked: bool):
        if checked and hasattr(self, 'use_detected_group'):
            self.use_detected_group.setChecked(False)

    def _on_accept(self):
        if hasattr(self, 'use_detected_group') and self.use_detected_group.isChecked():
            self.result_spec = self.detected_spec
            self.accept()
            return

        x_key = self.x_key_combo.currentText().strip()
        if not x_key or x_key not in self.h5file:
            QMessageBox.warning(self, "Error", f"Invalid X-axis dataset: {x_key}")
            return

        data_key = self.data_combo.currentText().strip()
        if data_key not in self.h5file:
            QMessageBox.warning(self, "Error", f"Invalid data dataset: {data_key}")
            return

        is_2d = self.type_2d.isChecked()
        y_key, y_label, y_scale = None, None, 1.0

        if is_2d:
            y_key = self.y_key_combo.currentText().strip()
            if not y_key or y_key not in self.h5file:
                QMessageBox.warning(self, "Error", f"Invalid Y-axis dataset: {y_key}")
                return
            y_label = self.y_label_edit.text() or y_key
            y_scale = self.y_scale_spin.value()

        if self.inst_cw.isChecked():
            exp_type = ExperimentType.CW_2D if is_2d else ExperimentType.CW_1D
        elif self.inst_rfsoc.isChecked():
            exp_type = ExperimentType.RFSOC_2D if is_2d else ExperimentType.RFSOC_1D
        else:
            exp_type = ExperimentType.CUSTOM_2D if is_2d else ExperimentType.CUSTOM_1D

        self.result_spec = ExperimentSpec(
            exp_type=exp_type,
            x_key=x_key,
            x_label=self.x_label_edit.text() or x_key,
            x_scale=self.x_scale_spin.value(),
            y_key=y_key,
            y_label=y_label,
            y_scale=y_scale,
            data_key=data_key
        )
        self.accept()


class HDF5DataSource:
    """Manages HDF5 file access with SWMR support."""

    def __init__(self, file_path: str, spec: Optional[ExperimentSpec] = None):
        self.file_path = file_path
        self.file = h5py.File(file_path, 'r', libver='latest', swmr=True)
        self.metadata = self._load_metadata()
        self.spec = spec or self._identify_experiment()

    def _load_metadata(self) -> dict:
        try:
            return json.loads(self.file['Metadata'][()].decode('utf-8'))
        except:
            return {'Expt ID': os.path.basename(self.file_path)}

    def _identify_experiment(self) -> Optional[ExperimentSpec]:
        expt_id = self.metadata.get('Expt ID', '')
        for name, spec in EXPERIMENT_REGISTRY.items():
            if name in expt_id:
                return spec
        return None

    def get_axes(self) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        xs = self.file[self.spec.x_key][:] * self.spec.x_scale
        ys = None
        if self.spec.y_key:
            ys = self.file[self.spec.y_key][:] * self.spec.y_scale
        return xs, ys

    def get_data(self) -> np.ndarray:
        data_key = getattr(self.spec, 'data_key', 'S21')
        self.file[data_key].id.refresh()
        return self.file[data_key][:]

    def close(self):
        self.file.close()

    @property
    def title(self) -> str:
        return self.metadata.get('Expt ID', 'Unknown')
    
    @property
    def file_info(self) -> str:
        """Returns filename | datetime string for display."""
        filename = self.metadata.get('Expt ID', os.path.basename(self.file_path))
        timestamp = self.metadata.get('Timestamp', '')
        if timestamp:
            return f"{filename}  |  {timestamp}"
        return filename

    @property
    def metadata_str(self) -> str:
        return json.dumps(self.metadata, indent=2, separators=('', ': ')
                         ).translate({ord(c): None for c in '{}"'})


class StitchedDataSource:
    """Data source for stitched 2D HDF5 files - stores multiple datasets."""
    
    def __init__(self, datasets: List[Tuple[np.ndarray, np.ndarray, np.ndarray]],
                 spec: ExperimentSpec, metadata: dict, file_paths: List[str]):
        """
        Args:
            datasets: List of (xs, ys, data) tuples, one per file
            spec: ExperimentSpec for the experiment type
            metadata: Metadata from first file
            file_paths: List of file paths
        """
        self.datasets = datasets  # List of (xs, ys, data) tuples
        self.spec = spec
        self.metadata = metadata.copy()
        self.file_paths = file_paths
        self.file_path = file_paths[0]  # Primary file
        
        # Update metadata to indicate stitching
        self.metadata['Stitched'] = f"{len(file_paths)} files"
        self.metadata['Source Files'] = ', '.join([os.path.basename(f) for f in file_paths])
        
        # Compute combined axis ranges across all datasets
        all_xs = np.concatenate([d[0] for d in datasets])
        all_ys = np.concatenate([d[1] for d in datasets])
        self._combined_xlim = (float(np.min(all_xs)), float(np.max(all_xs)))
        self._combined_ylim = (float(np.min(all_ys)), float(np.max(all_ys)))
        
        # For compatibility with existing code, expose first dataset's axes
        self.xs = datasets[0][0]
        self.ys = datasets[0][1]
    
    def close(self):
        """No-op for stitched data (in-memory, nothing to close)."""
        pass
    
    def is_stitched(self) -> bool:
        """Return True to indicate this is stitched data."""
        return True
    
    def get_axes(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return first dataset's axes for compatibility."""
        return self.datasets[0][0], self.datasets[0][1]
    
    def get_data(self) -> np.ndarray:
        """Return first dataset's data for compatibility."""
        return self.datasets[0][2]
    
    def get_all_datasets(self) -> List[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """Get all (xs, ys, data) tuples for stitched plotting."""
        return self.datasets
    
    def get_combined_xlim(self) -> Tuple[float, float]:
        """Get combined x-axis limits across all datasets."""
        return self._combined_xlim
    
    def get_combined_ylim(self) -> Tuple[float, float]:
        """Get combined y-axis limits across all datasets."""
        return self._combined_ylim
    
    @property
    def file_info(self) -> str:
        return f"Stitched: {len(self.file_paths)} files"
    
    @property
    def title(self) -> str:
        return f"Stitched: {len(self.file_paths)} files"
    
    @property
    def metadata_str(self) -> str:
        return json.dumps(self.metadata, indent=2, separators=('', ': ')
                         ).translate({ord(c): None for c in '{}"'})


class StitchDropArea(QListWidget):
    """Drop area for HDF5 files to stitch."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setMinimumHeight(150)
        self.setStyleSheet("""
            QListWidget {
                border: 2px dashed #aaa;
                border-radius: 5px;
                background-color: #f9f9f9;
            }
            QListWidget:hover {
                border-color: #666;
            }
        """)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            # Check if any files are .h5
            for url in event.mimeData().urls():
                if url.toLocalFile().endswith('.h5'):
                    event.acceptProposedAction()
                    return
        event.ignore()
        
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
            
    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path.endswith('.h5'):
                    # Check if already in list
                    existing = [self.item(i).data(Qt.UserRole) for i in range(self.count())]
                    if file_path not in existing:
                        item = QListWidgetItem(os.path.basename(file_path))
                        item.setData(Qt.UserRole, file_path)
                        self.addItem(item)
            event.acceptProposedAction()


class StitchDialog(QDialog):
    """Dialog for stitching multiple HDF5 files together."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.stitch_files = []  # List of validated file paths
        self.detected_expt_type = None  # Set during validation
        self.detected_spec = None  # The ExperimentSpec for the detected type
        
        self.setWindowTitle("Stitch HDF5 Files")
        self.setMinimumWidth(500)
        self.setMinimumHeight(350)
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Instructions
        instructions = QLabel(
            "Drag and drop .h5 files below to stitch together.\n"
            "All files must be the same 2D experiment type (at least 2 files required)."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Drop area
        self.drop_area = StitchDropArea()
        layout.addWidget(self.drop_area)
        
        # Add file button
        add_btn = QPushButton("Add Files...")
        add_btn.clicked.connect(self._add_files)
        layout.addWidget(add_btn)
        
        # Remove selected button
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        layout.addWidget(remove_btn)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: red;")
        layout.addWidget(self.status_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.stitch_btn = QPushButton("Stitch")
        self.stitch_btn.clicked.connect(self._validate_and_accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.stitch_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select HDF5 Files", "", "HDF5 Files (*.h5)"
        )
        for file_path in files:
            existing = [self.drop_area.item(i).data(Qt.UserRole) 
                       for i in range(self.drop_area.count())]
            if file_path not in existing:
                item = QListWidgetItem(os.path.basename(file_path))
                item.setData(Qt.UserRole, file_path)
                self.drop_area.addItem(item)
                
    def _remove_selected(self):
        for item in self.drop_area.selectedItems():
            self.drop_area.takeItem(self.drop_area.row(item))
            
    def _validate_and_accept(self):
        """Validate all files are same 2D experiment type and accept."""
        self.stitch_files = []
        self.status_label.setText("")
        
        if self.drop_area.count() < 2:
            self.status_label.setText("Please add at least 2 files to stitch.")
            return
        
        first_expt_type = None
        
        for i in range(self.drop_area.count()):
            file_path = self.drop_area.item(i).data(Qt.UserRole)
            
            try:
                with h5py.File(file_path, 'r', libver='latest', swmr=True) as f:
                    # Try to detect experiment type - use same logic as load_file
                    try:
                        metadata = json.loads(f['Metadata'][()].decode('utf-8'))
                    except:
                        metadata = {'Expt ID': os.path.basename(file_path)}
                    
                    expt_id = metadata.get('Expt ID', '')
                    # Extract experiment type from ID
                    file_expt_type = None
                    for exp_type in EXPERIMENT_REGISTRY:
                        if exp_type in expt_id:
                            file_expt_type = exp_type
                            break
                    
                    if file_expt_type is None:
                        self.status_label.setText(
                            f"Cannot determine experiment type for:\n{os.path.basename(file_path)}\n"
                            f"(Expt ID: {expt_id})"
                        )
                        return
                    
                    # Check it's a 2D type
                    spec = EXPERIMENT_REGISTRY[file_expt_type]
                    if spec.exp_type not in (ExperimentType.CW_2D, ExperimentType.RFSOC_2D, ExperimentType.CUSTOM_2D):
                        self.status_label.setText(
                            f"Stitch only supports 2D data.\n"
                            f"{os.path.basename(file_path)} is not a 2D experiment."
                        )
                        return
                    
                    # Check all files match each other
                    if first_expt_type is None:
                        first_expt_type = file_expt_type
                    elif file_expt_type != first_expt_type:
                        self.status_label.setText(
                            f"Type mismatch: {os.path.basename(file_path)}\n"
                            f"Expected: {first_expt_type}, Got: {file_expt_type}"
                        )
                        return
                        
                    self.stitch_files.append(file_path)
                    
            except Exception as e:
                self.status_label.setText(f"Error reading {os.path.basename(file_path)}:\n{str(e)}")
                return
        
        self.detected_expt_type = first_expt_type
        self.detected_spec = EXPERIMENT_REGISTRY[first_expt_type]
        self.accept()


class PlotWidget1D(QWidget):
    """Widget for 1D plots."""

    def __init__(self, data_source: HDF5DataSource, transforms: List,
                 settings: PlotSettings, parent=None):
        super().__init__(parent)
        self.data_source = data_source
        self.transforms = transforms
        self.settings = settings
        self._current_transform = 0
        self._zoom_completed_callback = None

        self.figure = plt.figure(figsize=(8, 6))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)

        self.xs, _ = data_source.get_axes()
        
        # Store full data range for reset (preserve original array order)
        self._full_xlim = (self.xs[0], self.xs[-1]) if len(self.xs) > 1 else (0, 1)
        self._full_ylim = None  # Will be computed from data in update_plot
        
        # Track if axes are flipped (for user-initiated flips)
        self._x_flipped = False
        self._y_flipped = False
        
        # Interchange axes state
        self._interchanged = False
        
        # Current zoom limits (None = full range)
        self._xlim = None
        self._ylim = None
        
        # Zoom mode state
        self._zoom_mode = False
        self._zoom_start = None
        self._zoom_rect = None
        
        # Callout mode state
        self._callout_mode = False
        self._callouts = []  # List of (x, y, annotation) tuples
        self._hover_annotation = None
        
        # Connect mouse events for zoom
        self.canvas.mpl_connect('button_press_event', self._on_mouse_press)
        self.canvas.mpl_connect('button_release_event', self._on_mouse_release)
        self.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        self.canvas.mpl_connect('resize_event', self._on_resize)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

        self.figure.tight_layout()

    def _on_resize(self, event):
        """Handle canvas resize to keep labels visible."""
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def set_zoom_completed_callback(self, callback):
        """Set callback to be called when zoom is completed."""
        self._zoom_completed_callback = callback

    def set_zoom_mode(self, enabled: bool):
        """Enable or disable zoom mode."""
        self._zoom_mode = enabled
        if enabled:
            self.canvas.setCursor(Qt.CrossCursor)
        else:
            self.canvas.setCursor(Qt.ArrowCursor)
            if self._zoom_rect is not None:
                self._zoom_rect.remove()
                self._zoom_rect = None
                self.canvas.draw()

    def reset_zoom(self):
        """Reset to full data range."""
        self._xlim = None
        self._ylim = None
        self.update_plot()

    def flip_x(self):
        """Flip the X-axis direction."""
        self._x_flipped = not self._x_flipped
        self.update_plot()

    def flip_y(self):
        """Flip the Y-axis direction."""
        self._y_flipped = not self._y_flipped
        self.update_plot()

    def interchange_xy(self):
        """Interchange X and Y axes."""
        # Toggle the interchange flag
        self._interchanged = not self._interchanged
        
        # Swap flip states
        self._x_flipped, self._y_flipped = self._y_flipped, self._x_flipped
        
        # Swap zoom limits if set
        self._xlim, self._ylim = self._ylim, self._xlim
        
        # Swap full limits (will be recomputed on next update if needed)
        self._full_xlim, self._full_ylim = self._full_ylim, self._full_xlim
        
        # Note: axis labels are computed dynamically in update_plot based on _interchanged flag
        
        self.update_plot()

    def set_callout_mode(self, enabled: bool):
        """Enable or disable callout mode."""
        self._callout_mode = enabled
        if enabled:
            self.canvas.setCursor(Qt.CrossCursor)
            # Disable zoom mode if callout mode is enabled
            self._zoom_mode = False
        else:
            self.canvas.setCursor(Qt.ArrowCursor)
            # Remove hover annotation
            if self._hover_annotation is not None:
                try:
                    self._hover_annotation.remove()
                except:
                    pass
                self._hover_annotation = None
                self.canvas.draw_idle()

    def clear_callouts(self):
        """Remove all callout annotations."""
        self._callouts = []
        self.update_plot()

    def _on_mouse_press(self, event):
        """Handle mouse press for zoom or callout."""
        if event.inaxes != self.ax:
            return
        
        # Callout mode - add annotation on click
        if self._callout_mode and event.button == 1:
            if event.xdata is not None:
                # Find nearest data point
                # Find nearest data point based on interchange state
                data = self.data_source.get_data()
                _, _, transform = self.transforms[self._current_transform]
                try:
                    zs = transform(data)
                except:
                    zs = np.abs(data)
                # Convert Inf to NaN
                zs = np.where(np.isinf(zs), np.nan, zs)
                
                if self._interchanged:
                    # When interchanged: zs on X-axis, xs on Y-axis
                    # Use event.ydata to find nearest xs value
                    idx = np.argmin(np.abs(self.xs - event.ydata))
                else:
                    # Normal: xs on X-axis, zs on Y-axis
                    idx = np.argmin(np.abs(self.xs - event.xdata))
                
                # Always store original data values (x from xs, y from zs)
                x_val = self.xs[idx]
                y_val = zs[idx]
                self._callouts.append((x_val, y_val))
                self.update_plot()
            return
        
        # Zoom mode
        if self._zoom_mode and event.button == 1:
            self._zoom_start = event.xdata

    def _on_mouse_move(self, event):
        """Handle mouse move for zoom rectangle or callout hover."""
        # Callout mode hover
        if self._callout_mode and not self._zoom_mode:
            if event.inaxes == self.ax and event.xdata is not None:
                # Get transformed data
                data = self.data_source.get_data()
                _, _, transform = self.transforms[self._current_transform]
                try:
                    zs = transform(data)
                except:
                    zs = np.abs(data)
                # Convert Inf to NaN
                zs = np.where(np.isinf(zs), np.nan, zs)
                
                if self._interchanged:
                    # When interchanged: zs on X-axis, xs on Y-axis
                    # Use event.ydata to find nearest xs value
                    idx = np.argmin(np.abs(self.xs - event.ydata))
                else:
                    # Normal: xs on X-axis, zs on Y-axis
                    idx = np.argmin(np.abs(self.xs - event.xdata))
                
                # Original data values
                x_val = self.xs[idx]
                y_val = zs[idx]
                
                # Compute plot position based on interchange state
                if self._interchanged:
                    plot_x = y_val if not np.isnan(y_val) else 0
                    plot_y = x_val
                else:
                    plot_x = x_val
                    plot_y = y_val if not np.isnan(y_val) else 0
                
                # Remove old hover annotation
                if self._hover_annotation is not None:
                    try:
                        self._hover_annotation.remove()
                    except:
                        pass
                
                # Create new hover annotation (handle NaN display)
                y_str = 'NaN' if np.isnan(y_val) else f'{y_val:.4g}'
                self._hover_annotation = self.ax.annotate(
                    f'x={x_val:.4g}\ny={y_str}',
                    xy=(plot_x, plot_y),
                    xytext=(10, 10), textcoords='offset points',
                    fontsize=9,
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.8),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0')
                )
                self.canvas.draw_idle()
            else:
                # Remove hover annotation when outside axes
                if self._hover_annotation is not None:
                    try:
                        self._hover_annotation.remove()
                    except:
                        pass
                    self._hover_annotation = None
                    self.canvas.draw_idle()
            return
        
        # Zoom mode rectangle
        if not self._zoom_mode or self._zoom_start is None:
            return
        if event.inaxes != self.ax or event.xdata is None:
            return
        
        x0 = self._zoom_start
        x1 = event.xdata
            
        from matplotlib.patches import Rectangle
        
        # Remove old rectangle if it exists
        if self._zoom_rect is not None:
            try:
                self._zoom_rect.remove()
            except:
                pass
            self._zoom_rect = None
        
        # Draw new rectangle
        ylim = self.ax.get_ylim()
        width = x1 - x0
        height = ylim[1] - ylim[0]
        self._zoom_rect = self.ax.add_patch(
            Rectangle((x0, ylim[0]), width, height,
                      fill=True, facecolor='black', alpha=0.15, 
                      edgecolor='black', linewidth=1.5)
        )
        self.canvas.draw_idle()

    def _on_mouse_release(self, event):
        """Handle mouse release to apply zoom."""
        if not self._zoom_mode or self._zoom_start is None:
            return
        
        # Clean up zoom rectangle first
        if self._zoom_rect is not None:
            try:
                self._zoom_rect.remove()
            except:
                pass
            self._zoom_rect = None
        
        zoomed = False
        if event.button == 1 and event.inaxes == self.ax and event.xdata is not None:
            x0 = self._zoom_start
            x1 = event.xdata
            
            # Determine threshold based on current axis direction
            x_range = abs(self._full_xlim[1] - self._full_xlim[0])
            
            if abs(x1 - x0) > 0.001 * x_range:
                # Keep the order as drawn (don't swap)
                self._xlim = (x0, x1)
                zoomed = True
        
        self._zoom_start = None
        
        # Always exit zoom mode and notify
        self._zoom_mode = False
        self.canvas.setCursor(Qt.ArrowCursor)
        if self._zoom_completed_callback:
            self._zoom_completed_callback()
        
        if zoomed:
            self.update_plot()
        else:
            self.canvas.draw_idle()

    def set_transform(self, index: int):
        self._current_transform = index
        self.update_plot()

    def update_settings(self, settings: PlotSettings):
        self.settings = settings
        self.update_plot()

    def update_plot(self):
        try:
            self.ax.clear()

            label, ylabel, transform = self.transforms[self._current_transform]
            data = self.data_source.get_data()

            try:
                zs = transform(data)
            except Exception as e:
                print(f"Transform error: {e}")
                zs = np.abs(data)

            # Convert Inf to NaN (matplotlib will skip NaN values in line plots)
            zs = np.where(np.isinf(zs), np.nan, zs)
            
            # Compute full y limits from data (ignoring NaN)
            valid_zs = zs[~np.isnan(zs)]
            if len(valid_zs) > 0:
                data_ymin = float(np.min(valid_zs))
                data_ymax = float(np.max(valid_zs))
                # Add padding to y limits
                y_range = data_ymax - data_ymin
                if y_range > 0:
                    padding = y_range * self.settings.y_padding
                else:
                    padding = abs(data_ymax) * self.settings.y_padding if data_ymax != 0 else 0.1
                data_ylim = (data_ymin - padding, data_ymax + padding)
            else:
                data_ylim = (0, 1)
            
            # Update _full_ylim if not interchanged, else it holds x range
            if not self._interchanged:
                self._full_ylim = data_ylim
            
            # Determine what to plot based on interchange state
            if self._interchanged:
                # Swapped: Y-axis shows xs (independent), X-axis shows zs (dependent)
                plot_x = zs
                plot_y = self.xs
                x_label_default = ylabel  # Transform label on X
                y_label_default = self.data_source.spec.x_label  # Original X label on Y
                
                # When interchanged, x limits come from data range, y limits from xs
                x_full = data_ylim
                y_full = (self.xs[0], self.xs[-1]) if len(self.xs) > 1 else (0, 1)
            else:
                # Normal: X-axis shows xs, Y-axis shows zs
                plot_x = self.xs
                plot_y = zs
                x_label_default = self.data_source.spec.x_label
                y_label_default = ylabel
                
                x_full = self._full_xlim
                y_full = data_ylim

            # Build marker kwargs
            marker_kwargs = {}
            if self.settings.marker_style != 'None':
                marker_kwargs['marker'] = self.settings.marker_style
                marker_kwargs['markersize'] = self.settings.marker_size
                marker_kwargs['markerfacecolor'] = self.settings.marker_color
                marker_kwargs['markeredgecolor'] = self.settings.marker_color

            self.ax.plot(plot_x, plot_y, color=self.settings.line_color,
                         linewidth=self.settings.line_width, **marker_kwargs)
            
            # Apply custom or default labels
            x_label = self.settings.x_label_text if self.settings.x_label_text else x_label_default
            y_label_text = self.settings.y_label_text if self.settings.y_label_text else y_label_default
            self.ax.set_xlabel(x_label, fontsize=self.settings.label_size)
            self.ax.set_ylabel(y_label_text, fontsize=self.settings.label_size)
            
            # Apply title if set
            if self.settings.title_text:
                self.ax.set_title(self.settings.title_text, fontsize=self.settings.title_size)
            
            # Apply tick settings
            self.ax.tick_params(axis='both', which='major', 
                               length=self.settings.tick_size, 
                               width=self.settings.tick_width,
                               labelsize=self.settings.tick_font_size)
            
            # Apply tick count if specified
            if self.settings.x_tick_count > 0:
                from matplotlib.ticker import MaxNLocator
                self.ax.xaxis.set_major_locator(MaxNLocator(nbins=self.settings.x_tick_count))
            if self.settings.y_tick_count > 0:
                from matplotlib.ticker import MaxNLocator
                self.ax.yaxis.set_major_locator(MaxNLocator(nbins=self.settings.y_tick_count))
            
            # Apply X limits with flip consideration
            if self._xlim is not None:
                if self._x_flipped:
                    self.ax.set_xlim(self._xlim[1], self._xlim[0])
                else:
                    self.ax.set_xlim(self._xlim[0], self._xlim[1])
            else:
                if self._x_flipped:
                    self.ax.set_xlim(x_full[1], x_full[0])
                else:
                    self.ax.set_xlim(x_full[0], x_full[1])
            
            # Apply Y limits with flip consideration
            if self._ylim is not None:
                if self._y_flipped:
                    self.ax.set_ylim(self._ylim[1], self._ylim[0])
                else:
                    self.ax.set_ylim(self._ylim[0], self._ylim[1])
            else:
                if self._y_flipped:
                    self.ax.set_ylim(y_full[1], y_full[0])
                else:
                    self.ax.set_ylim(y_full[0], y_full[1])

            if self.settings.grid_enabled:
                self.ax.grid(True, alpha=self.settings.grid_alpha, linewidth=self.settings.grid_width)

            # Draw callout annotations
            # Callouts store original data values (x from xs, y from zs)
            for x_val, y_val in self._callouts:
                # Compute plot position based on interchange state
                if self._interchanged:
                    plot_x = y_val if not np.isnan(y_val) else 0
                    plot_y = x_val
                else:
                    plot_x = x_val
                    plot_y = y_val if not np.isnan(y_val) else 0
                
                # Skip drawing marker if position is NaN
                if not np.isnan(plot_x) and not np.isnan(plot_y):
                    self.ax.plot(plot_x, plot_y, 'ro', markersize=5)
                y_str = 'NaN' if np.isnan(y_val) else f'{y_val:.4g}'
                ann = self.ax.annotate(
                    f'x={x_val:.4g}\ny={y_str}',
                    xy=(plot_x, plot_y),
                    xytext=(10, 10), textcoords='offset points',
                    fontsize=9,
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='red', alpha=0.9),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0', color='red')
                )
                ann.draggable()

            self.figure.tight_layout()
            self.canvas.draw()
        except Exception as e:
            print(f"Plot update error: {e}")


class PlotWidget2D(QWidget):
    """Widget for 2D plots with sliders and optional linecuts."""

    def __init__(self, data_source: HDF5DataSource, transforms: List,
                 settings: PlotSettings, parent=None):
        super().__init__(parent)
        self.data_source = data_source
        self.transforms = transforms
        self.settings = settings
        self._current_transform = 0
        self._colorbar = None
        self._cbar_ax = None
        self._pcm = None
        self._zoom_completed_callback = None
        
        # Check if this is stitched data
        self._is_stitched = hasattr(data_source, 'is_stitched') and data_source.is_stitched()
        
        # Disable linecuts for stitched data
        self._show_linecuts = False

        self.figure = plt.figure(figsize=(8, 6))
        self.canvas = FigureCanvas(self.figure)

        self.xs, self.ys = data_source.get_axes()
        
        # Store full data range for reset
        if self._is_stitched:
            # Use combined limits from all datasets
            self._full_xlim = data_source.get_combined_xlim()
            self._full_ylim = data_source.get_combined_ylim()
        else:
            # Preserve original array order
            self._full_xlim = (self.xs[0], self.xs[-1]) if len(self.xs) > 1 else (0, 1)
            self._full_ylim = (self.ys[0], self.ys[-1]) if len(self.ys) > 1 else (0, 1)
        
        # Track if axes are flipped (for user-initiated flips)
        self._x_flipped = False
        self._y_flipped = False
        
        # Current zoom limits (None = full range)
        self._xlim = None
        self._ylim = None
        
        # Zoom mode state
        self._zoom_mode = False
        self._zoom_start = None
        self._zoom_rect = None
        
        # Callout mode state
        self._callout_mode = False
        self._callouts = []  # List of (x, y, z) tuples
        self._hover_annotation = None
        
        # Interchange axes state
        self._interchanged = False

        # Initialize axes (will be configured in _setup_axes)
        self.ax_2d = None
        self.ax_xcut = None
        self.ax_ycut = None
        self.slider_y_ax = None
        self.slider_x_ax = None
        self.slider_y = None
        self.slider_x = None

        self._setup_axes()
        
        # Connect mouse events for zoom
        self.canvas.mpl_connect('button_press_event', self._on_mouse_press)
        self.canvas.mpl_connect('button_release_event', self._on_mouse_release)
        self.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        self.canvas.mpl_connect('resize_event', self._on_resize)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

    def _on_resize(self, event):
        """Handle canvas resize to keep labels visible."""
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def set_zoom_completed_callback(self, callback):
        """Set callback to be called when zoom is completed."""
        self._zoom_completed_callback = callback

    def set_zoom_mode(self, enabled: bool):
        """Enable or disable zoom mode."""
        self._zoom_mode = enabled
        if enabled:
            self.canvas.setCursor(Qt.CrossCursor)
        else:
            self.canvas.setCursor(Qt.ArrowCursor)
            # Clear any existing zoom rectangle
            if self._zoom_rect is not None:
                self._zoom_rect.remove()
                self._zoom_rect = None
                self.canvas.draw()

    def reset_zoom(self):
        """Reset to full data range."""
        self._xlim = None
        self._ylim = None
        self.update_plot()

    def flip_x(self):
        """Flip the X-axis direction."""
        self._x_flipped = not self._x_flipped
        self.update_plot()

    def flip_y(self):
        """Flip the Y-axis direction."""
        self._y_flipped = not self._y_flipped
        self.update_plot()

    def interchange_xy(self):
        """Interchange X and Y axes and transpose data."""
        # Swap xs and ys
        self.xs, self.ys = self.ys, self.xs
        
        # Swap full limits
        self._full_xlim, self._full_ylim = self._full_ylim, self._full_xlim
        
        # Swap current zoom limits if set
        if self._xlim is not None or self._ylim is not None:
            self._xlim, self._ylim = self._ylim, self._xlim
        
        # Swap flip states
        self._x_flipped, self._y_flipped = self._y_flipped, self._x_flipped
        
        # Toggle the interchange flag for data transposition
        self._interchanged = not getattr(self, '_interchanged', False)
        
        # For stitched data, swap the datasets
        if self._is_stitched:
            swapped_datasets = []
            for xs, ys, data in self.data_source.datasets:
                swapped_datasets.append((ys, xs, data.T))
            self.data_source.datasets = swapped_datasets
            # Also swap combined limits
            self.data_source._combined_xlim, self.data_source._combined_ylim = \
                self.data_source._combined_ylim, self.data_source._combined_xlim
        
        # Swap axis labels in spec (create a modified copy)
        spec = self.data_source.spec
        # Swap x_label and y_label
        old_x_label = spec.x_label
        old_y_label = spec.y_label
        spec.x_label = old_y_label
        spec.y_label = old_x_label
        
        self.update_plot()

    def set_callout_mode(self, enabled: bool):
        """Enable or disable callout mode."""
        self._callout_mode = enabled
        if enabled:
            self.canvas.setCursor(Qt.CrossCursor)
            # Disable zoom mode if callout mode is enabled
            self._zoom_mode = False
        else:
            self.canvas.setCursor(Qt.ArrowCursor)
            # Remove hover annotation
            if self._hover_annotation is not None:
                try:
                    self._hover_annotation.remove()
                except:
                    pass
                self._hover_annotation = None
                self.canvas.draw_idle()

    def clear_callouts(self):
        """Remove all callout annotations."""
        self._callouts = []
        self.update_plot()

    def _on_mouse_press(self, event):
        """Handle mouse press for zoom or callout."""
        if event.inaxes != self.ax_2d:
            return
        
        # Callout mode - add annotation on click
        if self._callout_mode and event.button == 1:
            if event.xdata is not None and event.ydata is not None:
                _, _, transform = self.transforms[self._current_transform]
                
                if self._is_stitched:
                    # Search across all datasets to find nearest point
                    best_dist = float('inf')
                    best_point = None
                    
                    for xs, ys, data in self.data_source.get_all_datasets():
                        x_idx = np.argmin(np.abs(xs - event.xdata))
                        y_idx = np.argmin(np.abs(ys - event.ydata))
                        x_val = xs[x_idx]
                        y_val = ys[y_idx]
                        dist = (x_val - event.xdata)**2 + (y_val - event.ydata)**2
                        
                        if dist < best_dist:
                            best_dist = dist
                            try:
                                zs = transform(data)
                            except:
                                zs = np.abs(data)
                            zs = np.where(np.isinf(zs), np.nan, zs)
                            z_val = zs[y_idx, x_idx] if zs.ndim > 1 else zs[x_idx]
                            best_point = (x_val, y_val, z_val)
                    
                    if best_point:
                        self._callouts.append(best_point)
                        self.update_plot()
                else:
                    # Single dataset: original behavior
                    x_idx = np.argmin(np.abs(self.xs - event.xdata))
                    y_idx = np.argmin(np.abs(self.ys - event.ydata))
                    x_val = self.xs[x_idx]
                    y_val = self.ys[y_idx]
                    
                    # Get current z value from transformed data
                    data = self.data_source.get_data()
                    try:
                        zs = transform(data)
                    except:
                        zs = np.abs(data)
                    # Convert Inf to NaN
                    zs = np.where(np.isinf(zs), np.nan, zs)
                    # Transpose if axes have been interchanged
                    if getattr(self, '_interchanged', False):
                        zs = zs.T
                    z_val = zs[y_idx, x_idx] if zs.ndim > 1 else zs[x_idx]
                    
                    # Store callout data (including NaN values)
                    self._callouts.append((x_val, y_val, z_val))
                    self.update_plot()
            return
        
        # Zoom mode
        if self._zoom_mode and event.button == 1:
            self._zoom_start = (event.xdata, event.ydata)

    def _on_mouse_move(self, event):
        """Handle mouse move for zoom rectangle or callout hover."""
        # Callout mode hover
        if self._callout_mode and not self._zoom_mode:
            if event.inaxes == self.ax_2d and event.xdata is not None and event.ydata is not None:
                _, _, transform = self.transforms[self._current_transform]
                
                if self._is_stitched:
                    # Search across all datasets to find nearest point
                    best_dist = float('inf')
                    best_point = None
                    
                    for xs, ys, data in self.data_source.get_all_datasets():
                        x_idx = np.argmin(np.abs(xs - event.xdata))
                        y_idx = np.argmin(np.abs(ys - event.ydata))
                        x_val = xs[x_idx]
                        y_val = ys[y_idx]
                        dist = (x_val - event.xdata)**2 + (y_val - event.ydata)**2
                        
                        if dist < best_dist:
                            best_dist = dist
                            try:
                                zs = transform(data)
                            except:
                                zs = np.abs(data)
                            zs = np.where(np.isinf(zs), np.nan, zs)
                            z_val = zs[y_idx, x_idx] if zs.ndim > 1 else zs[x_idx]
                            best_point = (x_val, y_val, z_val)
                    
                    if best_point:
                        x_val, y_val, z_val = best_point
                    else:
                        return
                else:
                    # Single dataset: original behavior
                    x_idx = np.argmin(np.abs(self.xs - event.xdata))
                    y_idx = np.argmin(np.abs(self.ys - event.ydata))
                    x_val = self.xs[x_idx]
                    y_val = self.ys[y_idx]
                    
                    # Get current z value from transformed data
                    data = self.data_source.get_data()
                    try:
                        zs = transform(data)
                    except:
                        zs = np.abs(data)
                    # Convert Inf to NaN
                    zs = np.where(np.isinf(zs), np.nan, zs)
                    # Transpose if axes have been interchanged
                    if getattr(self, '_interchanged', False):
                        zs = zs.T
                    z_val = zs[y_idx, x_idx] if zs.ndim > 1 else zs[x_idx]
                
                # Remove old hover annotation
                if self._hover_annotation is not None:
                    try:
                        self._hover_annotation.remove()
                    except:
                        pass
                
                # Create new hover annotation (handle NaN display)
                z_str = 'NaN' if np.isnan(z_val) else f'{z_val:.4g}'
                self._hover_annotation = self.ax_2d.annotate(
                    f'x={x_val:.4g}\ny={y_val:.4g}\nz={z_str}',
                    xy=(x_val, y_val),
                    xytext=(10, 10), textcoords='offset points',
                    fontsize=9,
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.8),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0')
                )
                self.canvas.draw_idle()
            else:
                # Remove hover annotation when outside axes
                if self._hover_annotation is not None:
                    try:
                        self._hover_annotation.remove()
                    except:
                        pass
                    self._hover_annotation = None
                    self.canvas.draw_idle()
            return
        
        # Zoom mode rectangle
        if not self._zoom_mode or self._zoom_start is None:
            return
        if event.inaxes != self.ax_2d or event.xdata is None or event.ydata is None:
            return
        
        from matplotlib.patches import Rectangle
        
        # Remove old rectangle if it exists
        if self._zoom_rect is not None:
            try:
                self._zoom_rect.remove()
            except:
                pass
            self._zoom_rect = None
        
        # Draw new rectangle
        x0, y0 = self._zoom_start
        x1, y1 = event.xdata, event.ydata
        
        width = x1 - x0
        height = y1 - y0
        self._zoom_rect = self.ax_2d.add_patch(
            Rectangle((x0, y0), width, height,
                      fill=True, facecolor='black', alpha=0.15,
                      edgecolor='black', linewidth=1.5)
        )
        self.canvas.draw_idle()

    def _on_mouse_release(self, event):
        """Handle mouse release to apply zoom."""
        if not self._zoom_mode or self._zoom_start is None:
            return
        
        # Clean up zoom rectangle first
        if self._zoom_rect is not None:
            try:
                self._zoom_rect.remove()
            except:
                pass
            self._zoom_rect = None
        
        zoomed = False
        if event.button == 1 and event.inaxes == self.ax_2d:
            x0, y0 = self._zoom_start
            x1, y1 = event.xdata, event.ydata
            
            if x1 is not None and y1 is not None:
                # Determine threshold based on current axis range
                x_range = abs(self._full_xlim[1] - self._full_xlim[0])
                y_range = abs(self._full_ylim[1] - self._full_ylim[0])
                
                # Only zoom if selection is meaningful
                if abs(x1 - x0) > 0.001 * x_range and abs(y1 - y0) > 0.001 * y_range:
                    # Keep the order as drawn (don't swap)
                    self._xlim = (x0, x1)
                    self._ylim = (y0, y1)
                    zoomed = True
        
        self._zoom_start = None
        
        # Always exit zoom mode and notify
        self._zoom_mode = False
        self.canvas.setCursor(Qt.ArrowCursor)
        if self._zoom_completed_callback:
            self._zoom_completed_callback()
        
        if zoomed:
            self.update_plot()
        else:
            self.canvas.draw_idle()

    def _setup_axes(self):
        """Setup axes based on linecut visibility."""
        self.figure.clear()
        self._colorbar = None
        self._cbar_ax = None
        self._pcm = None

        if self._show_linecuts:
            # Layout with linecuts: 2x2 grid
            self.ax_2d = self.figure.add_axes([0.08, 0.55, 0.35, 0.38])  # top-left
            self.ax_xcut = self.figure.add_axes([0.55, 0.55, 0.35, 0.38])  # top-right
            self.ax_ycut = self.figure.add_axes([0.08, 0.12, 0.35, 0.35])  # bottom-left
            
            # Colorbar axes (next to 2D plot)
            self._cbar_ax = self.figure.add_axes([0.44, 0.55, 0.015, 0.38])
            
            # Sliders
            self.slider_y_ax = self.figure.add_axes([0.92, 0.55, 0.02, 0.38])
            self.slider_x_ax = self.figure.add_axes([0.08, 0.03, 0.35, 0.02])
        else:
            # Layout without linecuts: single large plot
            self.ax_2d = self.figure.add_axes([0.08, 0.08, 0.75, 0.87])
            self.ax_xcut = None
            self.ax_ycut = None
            
            # Colorbar axes (on the right)
            self._cbar_ax = self.figure.add_axes([0.85, 0.08, 0.03, 0.87])
            
            # No sliders needed
            self.slider_y_ax = None
            self.slider_x_ax = None

        # Create sliders if needed
        if self._show_linecuts:
            self.slider_y = MplSlider(
                self.slider_y_ax, '', 0, max(1, len(self.ys)-1),
                valinit=0, valstep=1, orientation='vertical')
            self.slider_x = MplSlider(
                self.slider_x_ax, '', 0, max(1, len(self.xs)-1),
                valinit=0, valstep=1, orientation='horizontal')
            self.slider_y.on_changed(lambda _: self.update_plot())
            self.slider_x.on_changed(lambda _: self.update_plot())
        else:
            self.slider_y = None
            self.slider_x = None

    def set_show_linecuts(self, show: bool):
        """Toggle linecut visibility. Disabled for stitched data."""
        if self._is_stitched:
            return  # Linecuts not supported for stitched data
        if show != self._show_linecuts:
            self._show_linecuts = show
            self._setup_axes()
            self.update_plot()

    def set_transform(self, index: int):
        self._current_transform = index
        self.update_plot()

    def update_settings(self, settings: PlotSettings):
        self.settings = settings
        self.update_plot()

    def get_current_data_range(self) -> Tuple[float, float]:
        """Get the current transformed data range."""
        try:
            _, _, transform = self.transforms[self._current_transform]
            
            if self._is_stitched:
                # Compute min/max across all datasets
                all_mins = []
                all_maxs = []
                for xs, ys, data in self.data_source.get_all_datasets():
                    zs = transform(data)
                    zs = np.where(np.isinf(zs), np.nan, zs)
                    all_mins.append(float(np.nanmin(zs)))
                    all_maxs.append(float(np.nanmax(zs)))
                return min(all_mins), max(all_maxs)
            else:
                data = self.data_source.get_data()
                zs = transform(data)
                # Convert Inf to NaN, then use nanmin/nanmax to ignore NaN values
                zs = np.where(np.isinf(zs), np.nan, zs)
                return float(np.nanmin(zs)), float(np.nanmax(zs))
        except:
            return 0.0, 1.0

    def update_plot(self):
        try:
            # Clear axes
            self.ax_2d.clear()
            if self._show_linecuts:
                self.ax_xcut.clear()
                self.ax_ycut.clear()
            
            # Clear colorbar axes
            if self._cbar_ax is not None:
                self._cbar_ax.clear()

            label, ylabel, transform = self.transforms[self._current_transform]
            
            # Get slider values if linecuts are shown
            if self._show_linecuts and self.slider_y is not None:
                y_idx = int(self.slider_y.val)
                x_idx = int(self.slider_x.val)
            else:
                y_idx = 0
                x_idx = 0

            # Get axis labels for titles (use custom if set, otherwise spec defaults)
            y_label_default = self.data_source.spec.y_label or 'Y'
            x_label_default = self.data_source.spec.x_label or 'X'
            
            y_label = self.settings.y_label_text if self.settings.y_label_text else y_label_default
            x_label = self.settings.x_label_text if self.settings.x_label_text else x_label_default

            # 2D plot - disable autoscaling so our limits are respected
            self.ax_2d.set_autoscale_on(False)
            
            if self._is_stitched:
                # Stitched data: plot each dataset with separate pcolormesh calls
                # First compute global vmin/vmax across all datasets
                vmin, vmax = self.get_current_data_range()
                if self.settings.vmin is not None:
                    vmin = self.settings.vmin
                if self.settings.vmax is not None:
                    vmax = self.settings.vmax
                
                pcm = None
                for xs, ys, data in self.data_source.get_all_datasets():
                    try:
                        zs = transform(data)
                    except Exception as e:
                        print(f"Transform error: {e}")
                        zs = np.abs(data)
                    
                    # Convert Inf to NaN
                    zs = np.where(np.isinf(zs), np.nan, zs)
                    
                    pcm = self.ax_2d.pcolormesh(xs, ys, zs,
                                                 cmap=self.settings.colormap,
                                                 vmin=vmin, vmax=vmax)
            else:
                # Single dataset: original behavior
                data = self.data_source.get_data()
                try:
                    zs = transform(data)
                except Exception as e:
                    print(f"Transform error: {e}")
                    zs = np.abs(data)

                # Convert Inf to NaN (pcolormesh will show NaN as transparent/empty)
                zs = np.where(np.isinf(zs), np.nan, zs)
                
                # Transpose if axes have been interchanged
                if getattr(self, '_interchanged', False):
                    zs = zs.T

                y_idx = min(y_idx, zs.shape[0] - 1) if zs.ndim > 1 else 0
                x_idx = min(x_idx, zs.shape[1] - 1) if zs.ndim > 1 else min(x_idx, len(zs) - 1)

                # Get color limits
                vmin, vmax = self.settings.get_clim(zs)

                pcm = self.ax_2d.pcolormesh(self.xs, self.ys, zs,
                                             cmap=self.settings.colormap,
                                             vmin=vmin, vmax=vmax)
            
            # Set axis limits to match data order
            if self._xlim is not None:
                if self._x_flipped:
                    self.ax_2d.set_xlim(self._xlim[1], self._xlim[0])
                else:
                    self.ax_2d.set_xlim(self._xlim[0], self._xlim[1])
            else:
                if self._x_flipped:
                    self.ax_2d.set_xlim(self._full_xlim[1], self._full_xlim[0])
                else:
                    self.ax_2d.set_xlim(self._full_xlim[0], self._full_xlim[1])
            
            if self._ylim is not None:
                if self._y_flipped:
                    self.ax_2d.set_ylim(self._ylim[1], self._ylim[0])
                else:
                    self.ax_2d.set_ylim(self._ylim[0], self._ylim[1])
            else:
                if self._y_flipped:
                    self.ax_2d.set_ylim(self._full_ylim[1], self._full_ylim[0])
                else:
                    self.ax_2d.set_ylim(self._full_ylim[0], self._full_ylim[1])
            
            # Add colorbar to dedicated axes
            if pcm is not None:
                self._colorbar = self.figure.colorbar(pcm, cax=self._cbar_ax)
                # Use custom z_label if set, otherwise use transform label
                z_label = self.settings.z_label_text if self.settings.z_label_text else ylabel
                self._cbar_ax.set_ylabel(z_label, fontsize=self.settings.label_size)
            
            if self._show_linecuts and not self._is_stitched:
                # Draw cut lines on 2D plot
                if len(self.ys) > y_idx:
                    self.ax_2d.axhline(self.ys[y_idx], color='r', lw=1, alpha=0.7)
                if len(self.xs) > x_idx:
                    self.ax_2d.axvline(self.xs[x_idx], color='b', lw=1, alpha=0.7)
            
            self.ax_2d.set_xlabel(x_label, fontsize=self.settings.label_size)
            self.ax_2d.set_ylabel(y_label, fontsize=self.settings.label_size)
            
            # Apply title if set
            if self.settings.title_text:
                self.ax_2d.set_title(self.settings.title_text, fontsize=self.settings.title_size)
            
            # Apply tick settings
            self.ax_2d.tick_params(axis='both', which='major',
                                   length=self.settings.tick_size,
                                   width=self.settings.tick_width,
                                   labelsize=self.settings.tick_font_size)
            
            # Apply tick count if specified
            if self.settings.x_tick_count > 0:
                from matplotlib.ticker import MaxNLocator
                self.ax_2d.xaxis.set_major_locator(MaxNLocator(nbins=self.settings.x_tick_count))
            if self.settings.y_tick_count > 0:
                from matplotlib.ticker import MaxNLocator
                self.ax_2d.yaxis.set_major_locator(MaxNLocator(nbins=self.settings.y_tick_count))

            # Linecuts (only if enabled and not stitched)
            if self._show_linecuts and not self._is_stitched:
                # Build marker kwargs for linecuts
                marker_kwargs = {}
                if self.settings.marker_style != 'None':
                    marker_kwargs['marker'] = self.settings.marker_style
                    marker_kwargs['markersize'] = self.settings.marker_size
                    marker_kwargs['markerfacecolor'] = self.settings.marker_color
                    marker_kwargs['markeredgecolor'] = self.settings.marker_color

                # X cut - shows horizontal slice at fixed Y value
                if zs.ndim > 1 and zs.shape[0] > y_idx:
                    self.ax_xcut.plot(self.xs, zs[y_idx], color=self.settings.line_color,
                                      linewidth=self.settings.line_width, **marker_kwargs)
                    self.ax_xcut.set_title(f'{y_label} = {self.ys[y_idx]:.3g}', fontsize=10)
                self.ax_xcut.set_xlabel(x_label, fontsize=self.settings.label_size)
                self.ax_xcut.set_ylabel(ylabel, fontsize=self.settings.label_size)
                # Apply x zoom/flip to x-cut
                if self._xlim is not None:
                    if self._x_flipped:
                        self.ax_xcut.set_xlim(self._xlim[1], self._xlim[0])
                    else:
                        self.ax_xcut.set_xlim(self._xlim[0], self._xlim[1])
                elif len(self.xs) > 1:
                    if self._x_flipped:
                        self.ax_xcut.set_xlim(self._full_xlim[1], self._full_xlim[0])
                    else:
                        self.ax_xcut.set_xlim(self._full_xlim[0], self._full_xlim[1])
                if self.settings.grid_enabled:
                    self.ax_xcut.grid(True, alpha=self.settings.grid_alpha, linewidth=self.settings.grid_width)

                # Y cut - shows vertical slice at fixed X value
                if zs.ndim > 1 and zs.shape[1] > x_idx:
                    self.ax_ycut.plot(self.ys, zs[:, x_idx], color=self.settings.line_color,
                                      linewidth=self.settings.line_width, **marker_kwargs)
                    self.ax_ycut.set_title(f'{x_label} = {self.xs[x_idx]:.3g}', fontsize=10)
                self.ax_ycut.set_xlabel(y_label, fontsize=self.settings.label_size)
                self.ax_ycut.set_ylabel(ylabel, fontsize=self.settings.label_size)
                # Apply y zoom/flip to y-cut
                if self._ylim is not None:
                    if self._y_flipped:
                        self.ax_ycut.set_xlim(self._ylim[1], self._ylim[0])
                    else:
                        self.ax_ycut.set_xlim(self._ylim[0], self._ylim[1])
                elif len(self.ys) > 1:
                    if self._y_flipped:
                        self.ax_ycut.set_xlim(self._full_ylim[1], self._full_ylim[0])
                    else:
                        self.ax_ycut.set_xlim(self._full_ylim[0], self._full_ylim[1])
                if self.settings.grid_enabled:
                    self.ax_ycut.grid(True, alpha=self.settings.grid_alpha, linewidth=self.settings.grid_width)

            # Draw callout annotations on 2D plot
            for x_val, y_val, z_val in self._callouts:
                self.ax_2d.plot(x_val, y_val, 'ro', markersize=5)
                z_str = 'NaN' if np.isnan(z_val) else f'{z_val:.4g}'
                ann = self.ax_2d.annotate(
                    f'x={x_val:.4g}\ny={y_val:.4g}\nz={z_str}',
                    xy=(x_val, y_val),
                    xytext=(10, 10), textcoords='offset points',
                    fontsize=9,
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='red', alpha=0.9),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0', color='red')
                )
                ann.draggable()

            self.figure.tight_layout()
            self.canvas.draw()
        except Exception as e:
            print(f"Plot update error: {e}")


class Plotter(QMainWindow):
    """Main window with collapsible sidebar."""

    def __init__(self, file_path: Optional[str] = None):
        super().__init__()
        self.setWindowTitle("Quddy HDF5 Plotter")
        self.setGeometry(100, 100, 1400, 800)

        self.data_source: Optional[HDF5DataSource] = None
        self.plot_widget: Optional[QWidget] = None
        self.update_timer: Optional[QTimer] = None
        self.settings = PlotSettings()
        self.sidebar_visible = True

        self._setup_ui()
        self.setAcceptDrops(True)

        if file_path:
            self.load_file(file_path)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Main content area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(8, 8, 8, 8)

        # Top bar with file info and sidebar toggle
        top_bar = QHBoxLayout()
        
        # Spacer on left to help center the label
        top_bar.addStretch()
        
        # File info label (centered)
        self.file_info_label = QLabel("")
        self.file_info_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #333;")
        self.file_info_label.setAlignment(Qt.AlignCenter)
        top_bar.addWidget(self.file_info_label)
        
        top_bar.addStretch()
        
        # Toggle sidebar button (on the right)
        self.toggle_btn = QPushButton("☰")
        self.toggle_btn.setFixedSize(32, 32)
        self.toggle_btn.setToolTip("Toggle Sidebar")
        self.toggle_btn.clicked.connect(self._toggle_sidebar)
        top_bar.addWidget(self.toggle_btn)
        
        content_layout.addLayout(top_bar)

        # Drop zone
        self.drop_label = QLabel("Drag and drop your HDF5 file here\n\nor double-click an .h5 file")
        self.drop_label.setAlignment(Qt.AlignCenter)
        self.drop_label.setStyleSheet(
            "border: 2px dashed #aaa; padding: 40px; font-size: 20px; color: #666;"
        )
        self.drop_label.setMinimumHeight(400)
        content_layout.addWidget(self.drop_label)

        # Plot container
        self.plot_container = QVBoxLayout()
        content_layout.addLayout(self.plot_container)

        main_layout.addWidget(content_widget, 1)

        # Sidebar
        self.sidebar = Sidebar()
        self.sidebar.set_callback('transform_changed', self._on_transform_changed)
        self.sidebar.set_callback('live_toggled', self._on_live_toggle)
        self.sidebar.set_callback('interval_changed', self._on_interval_changed)
        self.sidebar.set_callback('settings_changed', self._on_settings_changed)
        self.sidebar.set_callback('configure_axes', self._show_axis_config)
        self.sidebar.set_callback('copy_clipboard', self._copy_to_clipboard)
        self.sidebar.set_callback('copy_metadata', self._copy_metadata_to_clipboard)
        self.sidebar.set_callback('copy_metadata_dict', self._copy_metadata_dict_to_clipboard)
        self.sidebar.set_callback('save_figure', self._save_figure)
        self.sidebar.set_callback('send_word', self._send_to_word)
        self.sidebar.set_callback('rescale', self._on_rescale)
        self.sidebar.set_callback('linecuts_toggled', self._on_linecuts_toggled)
        self.sidebar.set_callback('zoom_toggled', self._on_zoom_toggled)
        self.sidebar.set_callback('reset_zoom', self._on_reset_zoom)
        self.sidebar.set_callback('flip_x', self._on_flip_x)
        self.sidebar.set_callback('flip_y', self._on_flip_y)
        self.sidebar.set_callback('interchange_xy', self._on_interchange_xy)
        self.sidebar.set_callback('callout_toggled', self._on_callout_toggled)
        self.sidebar.set_callback('clear_callouts', self._on_clear_callouts)
        self.sidebar.set_callback('change_figsize', self._on_change_figsize)
        self.sidebar.set_callback('set_limits', self._on_set_limits)
        self.sidebar.set_callback('stitch_files', self._on_stitch_files)
        main_layout.addWidget(self.sidebar)

    def _toggle_sidebar(self):
        self.sidebar_visible = not self.sidebar_visible
        self.sidebar.setVisible(self.sidebar_visible)

    def _on_zoom_toggled(self, enabled: bool):
        """Toggle zoom mode for plots."""
        if self.plot_widget and hasattr(self.plot_widget, 'set_zoom_mode'):
            self.plot_widget.set_zoom_mode(enabled)

    def _on_reset_zoom(self):
        """Reset zoom to full view."""
        if self.plot_widget and hasattr(self.plot_widget, 'reset_zoom'):
            self.plot_widget.reset_zoom()

    def _on_flip_x(self):
        """Flip X-axis direction."""
        if self.plot_widget and hasattr(self.plot_widget, 'flip_x'):
            self.plot_widget.flip_x()

    def _on_flip_y(self):
        """Flip Y-axis direction."""
        if self.plot_widget and hasattr(self.plot_widget, 'flip_y'):
            self.plot_widget.flip_y()

    def _on_interchange_xy(self):
        """Interchange X and Y axes."""
        if self.plot_widget and hasattr(self.plot_widget, 'interchange_xy'):
            self.plot_widget.interchange_xy()

    def _on_callout_toggled(self, enabled: bool):
        """Toggle callout mode for plots."""
        if self.plot_widget and hasattr(self.plot_widget, 'set_callout_mode'):
            self.plot_widget.set_callout_mode(enabled)

    def _on_clear_callouts(self):
        """Clear all callout annotations."""
        if self.plot_widget and hasattr(self.plot_widget, 'clear_callouts'):
            self.plot_widget.clear_callouts()

    def _on_change_figsize(self):
        """Open dialog to change figure size."""
        if not self.plot_widget:
            return
        
        # Get current figure size
        current_size = self.plot_widget.figure.get_size_inches()
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Figure Size")
        layout = QFormLayout(dialog)
        
        width_spin = QDoubleSpinBox()
        width_spin.setRange(4, 30)
        width_spin.setValue(current_size[0])
        width_spin.setSingleStep(0.5)
        width_spin.setSuffix(" in")
        layout.addRow("Width:", width_spin)
        
        height_spin = QDoubleSpinBox()
        height_spin.setRange(4, 30)
        height_spin.setValue(current_size[1])
        height_spin.setSingleStep(0.5)
        height_spin.setSuffix(" in")
        layout.addRow("Height:", height_spin)
        
        buttons = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout.addRow(buttons)
        
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        
        if dialog.exec_() == QDialog.Accepted:
            new_width = width_spin.value()
            new_height = height_spin.value()
            self.plot_widget.figure.set_size_inches(new_width, new_height)
            self.plot_widget.figure.tight_layout()
            self.plot_widget.update_plot()

    def _on_set_limits(self):
        """Open dialog to manually set axis limits."""
        if not self.plot_widget:
            return
        
        # Get current limits from the axes
        ax = self.plot_widget.ax if hasattr(self.plot_widget, 'ax') else self.plot_widget.ax_2d
        current_xlim = ax.get_xlim()
        current_ylim = ax.get_ylim()
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Set Axis Limits")
        layout = QFormLayout(dialog)
        
        # X limits section
        layout.addRow(QLabel("<b>X-Axis Limits</b>"))
        
        xmin_spin = QDoubleSpinBox()
        xmin_spin.setRange(-1e12, 1e12)
        xmin_spin.setDecimals(6)
        xmin_spin.setValue(min(current_xlim))
        xmin_spin.setSingleStep(0.1)
        layout.addRow("X Min:", xmin_spin)
        
        xmax_spin = QDoubleSpinBox()
        xmax_spin.setRange(-1e12, 1e12)
        xmax_spin.setDecimals(6)
        xmax_spin.setValue(max(current_xlim))
        xmax_spin.setSingleStep(0.1)
        layout.addRow("X Max:", xmax_spin)
        
        # Y limits section
        layout.addRow(QLabel("<b>Y-Axis Limits</b>"))
        
        ymin_spin = QDoubleSpinBox()
        ymin_spin.setRange(-1e12, 1e12)
        ymin_spin.setDecimals(6)
        ymin_spin.setValue(min(current_ylim))
        ymin_spin.setSingleStep(0.1)
        layout.addRow("Y Min:", ymin_spin)
        
        ymax_spin = QDoubleSpinBox()
        ymax_spin.setRange(-1e12, 1e12)
        ymax_spin.setDecimals(6)
        ymax_spin.setValue(max(current_ylim))
        ymax_spin.setSingleStep(0.1)
        layout.addRow("Y Max:", ymax_spin)
        
        # Buttons
        buttons = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        reset_btn = QPushButton("Reset to Full")
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(reset_btn)
        layout.addRow(buttons)
        
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        
        def reset_limits():
            # Reset to full data range
            if hasattr(self.plot_widget, 'reset_zoom'):
                self.plot_widget.reset_zoom()
            dialog.reject()
        
        reset_btn.clicked.connect(reset_limits)
        
        if dialog.exec_() == QDialog.Accepted:
            new_xmin = xmin_spin.value()
            new_xmax = xmax_spin.value()
            new_ymin = ymin_spin.value()
            new_ymax = ymax_spin.value()
            
            # Ensure min < max
            if new_xmin >= new_xmax:
                new_xmin, new_xmax = new_xmax, new_xmin
            if new_ymin >= new_ymax:
                new_ymin, new_ymax = new_ymax, new_ymin
            
            # Apply limits to the plot widget
            # Check if axes are flipped and account for it
            if self.plot_widget._x_flipped:
                self.plot_widget._xlim = (new_xmax, new_xmin)
            else:
                self.plot_widget._xlim = (new_xmin, new_xmax)
            
            if hasattr(self.plot_widget, '_y_flipped') and self.plot_widget._y_flipped:
                self.plot_widget._ylim = (new_ymax, new_ymin)
            else:
                self.plot_widget._ylim = (new_ymin, new_ymax)
            
            self.plot_widget.update_plot()

    def _on_stitch_files(self):
        """Open dialog to stitch multiple HDF5 files together."""
        dialog = StitchDialog(self)
        
        if dialog.exec_() == QDialog.Accepted and dialog.stitch_files:
            self._perform_stitch(dialog.stitch_files, dialog.detected_spec)
    
    def _perform_stitch(self, stitch_files: List[str], spec: ExperimentSpec):
        """Combine data from multiple files using multiple pcolormesh calls."""
        try:
            # Close existing data source if any
            if self.data_source and hasattr(self.data_source, 'close'):
                self.data_source.close()
            
            # Load all sources and collect datasets
            datasets = []  # List of (xs, ys, data) tuples
            all_sources = []
            
            for file_path in stitch_files:
                source = HDF5DataSource(file_path, spec)
                all_sources.append(source)
                xs, ys = source.get_axes()
                data = source.get_data()
                datasets.append((xs.copy(), ys.copy(), data.copy()))
            
            # Get metadata from first file
            metadata = all_sources[0].metadata.copy()
            file_paths = [s.file_path for s in all_sources]
            
            # Close all the HDF5 sources
            for source in all_sources:
                source.close()
            
            # Create a stitched data source with multiple datasets
            new_data_source = StitchedDataSource(
                datasets, spec, metadata, file_paths
            )
            
            # Now recreate the plot widget
            if self.update_timer:
                self.update_timer.stop()
            if self.plot_widget:
                self.plot_container.removeWidget(self.plot_widget)
                self.plot_widget.deleteLater()
            
            self.data_source = new_data_source
            
            # Get transforms
            if spec.exp_type in (ExperimentType.CW_1D, ExperimentType.CW_2D):
                transforms = DataTransforms.get_cw_transforms()
            elif spec.exp_type in (ExperimentType.RFSOC_1D, ExperimentType.RFSOC_2D):
                transforms = DataTransforms.get_rfsoc_transforms()
            else:
                transforms = DataTransforms.get_generic_transforms()
            
            # Always 2D for stitch (we only allow 2D types)
            self.plot_widget = PlotWidget2D(self.data_source, transforms, self.settings)
            vmin, vmax = self.plot_widget.get_current_data_range()
            self.sidebar.update_scale_range(vmin, vmax)
            
            self.plot_widget.set_zoom_completed_callback(self._on_zoom_completed)
            
            self.drop_label.hide()
            self.file_info_label.setText(self.data_source.file_info)
            self.sidebar.set_transforms(transforms)
            self.sidebar.set_metadata(self.data_source.metadata_str)
            self.sidebar.set_2d_mode(True)
            
            # Disable live updates for stitched data (it's a snapshot, won't update)
            self.sidebar.live_checkbox.setChecked(False)
            self.sidebar.live_checkbox.setEnabled(False)
            self.sidebar.live_checkbox.setToolTip("Live updates not available for stitched data")
            
            # Disable linecuts for stitched data
            self.sidebar.linecuts_checkbox.setChecked(False)
            self.sidebar.linecuts_checkbox.setEnabled(False)
            self.sidebar.linecuts_checkbox.setToolTip("Linecuts not available for stitched data")
            
            self.plot_container.addWidget(self.plot_widget)
            self.plot_widget.update_plot()
            # Don't start live updates for stitched data
            
        except Exception as e:
            QMessageBox.critical(self, "Stitch Error", f"Failed to stitch files:\n{str(e)}")
            import traceback
            traceback.print_exc()

    def _on_linecuts_toggled(self, show: bool):
        """Toggle linecut display for 2D plots."""
        if self.plot_widget and hasattr(self.plot_widget, 'set_show_linecuts'):
            self.plot_widget.set_show_linecuts(show)

    def _on_rescale(self):
        """Reset color scale to current data range."""
        if self.plot_widget and hasattr(self.plot_widget, 'get_current_data_range'):
            vmin, vmax = self.plot_widget.get_current_data_range()
            self.sidebar.update_scale_range(vmin, vmax)
            # Update settings and replot
            self.settings.vmin = vmin
            self.settings.vmax = vmax
            self.plot_widget.update_settings(self.settings)

    def _on_transform_changed(self, index: int):
        if self.plot_widget:
            self.plot_widget.set_transform(index)

    def _on_live_toggle(self, enabled: bool):
        if enabled and self.update_timer:
            self.update_timer.start(self.sidebar.interval_spin.value())
        elif self.update_timer:
            self.update_timer.stop()

    def _on_interval_changed(self, interval: int):
        if self.update_timer and self.sidebar.live_checkbox.isChecked():
            self.update_timer.setInterval(interval)

    def _on_settings_changed(self, settings: PlotSettings):
        self.settings = settings
        if self.plot_widget:
            self.plot_widget.update_settings(settings)

    def _start_live_updates(self):
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_plot)
        if self.sidebar.live_checkbox.isChecked():
            self.update_timer.start(self.sidebar.interval_spin.value())

    def _update_plot(self):
        if self.plot_widget:
            self.plot_widget.update_plot()

    def _get_figure(self) -> Optional[plt.Figure]:
        if self.plot_widget:
            return self.plot_widget.figure
        return None

    def _show_axis_config(self):
        if not self.data_source:
            return
        # Disable for stitched data
        if hasattr(self.data_source, 'is_stitched') and self.data_source.is_stitched():
            QMessageBox.information(self, "Configure Axes", 
                "Axis configuration is not available for stitched data.")
            return
        dialog = AxisSelectionDialog(
            self.data_source.file, self.data_source.metadata,
            self.data_source.spec, parent=self)
        if dialog.exec_() == QDialog.Accepted and dialog.result_spec:
            file_path = self.data_source.file_path
            self.data_source.close()
            self._setup_plot(file_path, dialog.result_spec)

    def _copy_to_clipboard(self):
        fig = self._get_figure()
        if not fig:
            return
        temp_file = 'temp_clipboard.png'
        fig.savefig(temp_file, dpi=150, bbox_inches='tight')
        QApplication.clipboard().setPixmap(QPixmap(temp_file))
        if os.path.exists(temp_file):
            os.remove(temp_file)

    def _copy_metadata_to_clipboard(self):
        if not self.data_source:
            return
        # Pretty format without curly brackets or quotes
        lines = []
        for key, value in self.data_source.metadata.items():
            lines.append(f"{key}: {value}")
        metadata_str = "\n".join(lines)
        QApplication.clipboard().setText(metadata_str)

    def _copy_metadata_dict_to_clipboard(self):
        if not self.data_source:
            return
        # Copy as JSON dict format
        metadata_str = json.dumps(self.data_source.metadata, indent=2)
        QApplication.clipboard().setText(metadata_str)

    def _send_to_word(self):
        if not HAS_WIN32:
            return
        fig = self._get_figure()
        if not fig:
            return
        temp_file = os.path.abspath('temp_word.png')
        fig.savefig(temp_file, dpi=150, bbox_inches='tight')
        try:
            word = win32.Dispatch('Word.Application')
            doc = word.ActiveDocument
            word.Selection.GoTo(What=3, Which=-1)
            word.Visible = True
            picture = word.Selection.InlineShapes.AddPicture(temp_file)
            picture.Width = 500
            picture.Height = 375
            doc.Save()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error sending to Word: {e}")
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def _save_figure(self):
        fig = self._get_figure()
        if not fig:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Figure", "",
            "PNG Files (*.png);;PDF Files (*.pdf);;SVG Files (*.svg)")
        if path:
            fig.savefig(path, dpi=150, bbox_inches='tight')

    def load_file(self, file_path: str):
        try:
            temp_file = h5py.File(file_path, 'r', libver='latest', swmr=True)
            try:
                metadata = json.loads(temp_file['Metadata'][()].decode('utf-8'))
            except:
                metadata = {'Expt ID': os.path.basename(file_path)}

            detected_spec = None
            expt_id = metadata.get('Expt ID', '')
            for name, spec in EXPERIMENT_REGISTRY.items():
                if name in expt_id:
                    detected_spec = spec
                    break

            if detected_spec is None:
                dialog = AxisSelectionDialog(temp_file, metadata, None, parent=self)
                if dialog.exec_() != QDialog.Accepted or not dialog.result_spec:
                    temp_file.close()
                    return
                spec = dialog.result_spec
            else:
                spec = detected_spec

            temp_file.close()
            self._setup_plot(file_path, spec)

        except Exception as e:
            tb = traceback.format_exc()
            self.drop_label.setText(f"Error loading file:\n{e}\n\n{tb}")
            self.drop_label.show()

    def _setup_plot(self, file_path: str, spec: ExperimentSpec):
        if self.data_source:
            self.data_source.close()
        if self.update_timer:
            self.update_timer.stop()
        if self.plot_widget:
            self.plot_container.removeWidget(self.plot_widget)
            self.plot_widget.deleteLater()

        self.data_source = HDF5DataSource(file_path, spec)

        if spec.exp_type in (ExperimentType.CW_1D, ExperimentType.CW_2D):
            transforms = DataTransforms.get_cw_transforms()
        elif spec.exp_type in (ExperimentType.RFSOC_1D, ExperimentType.RFSOC_2D):
            transforms = DataTransforms.get_rfsoc_transforms()
        else:
            transforms = DataTransforms.get_generic_transforms()

        is_2d = spec.exp_type in (ExperimentType.CW_2D, ExperimentType.RFSOC_2D,
                                   ExperimentType.CUSTOM_2D)

        if is_2d:
            self.plot_widget = PlotWidget2D(self.data_source, transforms, self.settings)
            self.resize(1600, 900)
            # Initialize scale range from data
            vmin, vmax = self.plot_widget.get_current_data_range()
            self.sidebar.update_scale_range(vmin, vmax)
        else:
            self.plot_widget = PlotWidget1D(self.data_source, transforms, self.settings)
            self.resize(1200, 600)

        # Set up zoom completed callback to uncheck the zoom button
        self.plot_widget.set_zoom_completed_callback(self._on_zoom_completed)

        self.drop_label.hide()
        self.file_info_label.setText(self.data_source.file_info)
        self.sidebar.set_transforms(transforms)
        self.sidebar.set_metadata(self.data_source.metadata_str)
        self.sidebar.set_2d_mode(is_2d)
        
        # Re-enable live updates (may have been disabled by stitched data)
        self.sidebar.live_checkbox.setEnabled(True)
        self.sidebar.live_checkbox.setToolTip("")
        
        # Re-enable linecuts (may have been disabled by stitched data)
        self.sidebar.linecuts_checkbox.setEnabled(True)
        self.sidebar.linecuts_checkbox.setToolTip("")

        self.plot_container.addWidget(self.plot_widget)
        self.plot_widget.update_plot()
        self._start_live_updates()

    def _on_zoom_completed(self):
        """Called when zoom is completed to uncheck the zoom button."""
        self.sidebar.zoom_btn.setChecked(False)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        event.setDropAction(Qt.CopyAction)
        event.accept()
        file_path = event.mimeData().urls()[0].toLocalFile()
        self.load_file(file_path)

    def closeEvent(self, event):
        if self.update_timer:
            self.update_timer.stop()
        if self.data_source:
            self.data_source.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Global exception handler to prevent crashes
    def exception_hook(exctype, value, tb):
        """Handle uncaught exceptions without crashing."""
        error_msg = ''.join(traceback.format_exception(exctype, value, tb))
        print(f"Uncaught exception:\n{error_msg}")
        QMessageBox.critical(None, "Error", f"An error occurred:\n\n{value}\n\nSee console for details.")
    
    sys.excepthook = exception_hook

    file_path = sys.argv[1] if len(sys.argv) > 1 else None
    plotter = Plotter(file_path)
    plotter.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()