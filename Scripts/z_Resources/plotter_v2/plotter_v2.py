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
    QColorDialog, QListWidget, QListWidgetItem, QShortcut
)
from PyQt5.QtGui import QPixmap, QIcon, QFont, QKeySequence
from PyQt5.QtCore import Qt, QTimer, QSize, QPropertyAnimation, QEasingCurve

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.colors as mcolors
from matplotlib.colors import Normalize, PowerNorm, TwoSlopeNorm

# Optional: win32com for Word integration (Windows only)
try:
    import win32com.client as win32
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

# Optional: resonator package for Argand plane fitting
try:
    from resonator import shunt, background as resonator_background
    HAS_RESONATOR = True
except ImportError:
    HAS_RESONATOR = False


class DroppableGroupBox(QGroupBox):
    """QGroupBox that accepts file drops."""
    
    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.setAcceptDrops(True)
        self._drop_callback = None
        self._normal_style = ""
        self._highlight_style = ""
    
    def set_drop_callback(self, callback):
        """Set callback for when files are dropped. Callback receives list of file paths."""
        self._drop_callback = callback
    
    def set_styles(self, normal: str, highlight: str):
        """Set normal and drag-highlight styles."""
        self._normal_style = normal
        self._highlight_style = highlight
        self.setStyleSheet(normal)
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            # Check if any URL is an h5 file
            for url in event.mimeData().urls():
                if url.toLocalFile().endswith(('.h5', '.hdf5')):
                    event.acceptProposedAction()
                    self.setStyleSheet(self._highlight_style)
                    return
        event.ignore()
    
    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._normal_style)
    
    def dropEvent(self, event):
        self.setStyleSheet(self._normal_style)
        if event.mimeData().hasUrls() and self._drop_callback:
            file_paths = []
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path.endswith(('.h5', '.hdf5')):
                    file_paths.append(file_path)
            if file_paths:
                event.acceptProposedAction()
                self._drop_callback(file_paths)
                return
        event.ignore()


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
    data_label: Optional[str] = None  # Label for z-axis / colorbar


@dataclass
class PlotSettings:
    """Settings for plot appearance."""
    colormap: str = 'viridis'
    line_color: str = '#1f77b4'
    line_width: float = 1.5
    marker_style: str = 'None'  # None, o, s, ^, v, D, etc.
    marker_size: float = 4.0
    marker_color: str = '#1f77b4'
    # Fit curve settings
    fit_color: str = '#d62728'  # Red
    fit_line_width: float = 1.5
    fit_line_style: str = '--'  # dashed
    grid_enabled: bool = True
    grid_alpha: float = 0.3
    grid_width: float = 0.5
    autoscale: bool = True
    vmin: Optional[float] = None
    vmax: Optional[float] = None
    # Normalization settings
    norm_type: str = 'linear'  # 'linear', 'twoslope', 'power'
    norm_vcenter: Optional[float] = None  # For twoslope norm
    norm_gamma: float = 0.5  # For power norm
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
    # Colorbar settings
    cbar_shrink: float = 1.0
    # Figure size (inches)
    fig_width: float = 10.0
    fig_height: float = 8.0
    
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


@dataclass
class OverlayData:
    """Data for an overlay trace."""
    xs: np.ndarray              # x-coordinates
    data: np.ndarray            # Raw complex S21 data
    ys: Optional[np.ndarray]    # For 2D overlays (None for 1D)
    label: str                  # Display name (filename by default)
    color: str                  # Line color
    visible: bool               # Show/hide toggle
    source_path: str            # Original file path
    x_label: str                # Axis label from original file
    is_2d: bool = False         # Whether overlay is 2D data


# Colors for auto-assigning to overlays
OVERLAY_COLORS = [
    '#e41a1c',  # red
    '#377eb8',  # blue  
    '#4daf4a',  # green
    '#984ea3',  # purple
    '#ff7f00',  # orange
    '#a65628',  # brown
    '#f781bf',  # pink
    '#999999',  # gray
]


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


# =============================================================================
# Fitting Models and Functions
# =============================================================================

import re
from scipy.optimize import curve_fit


@dataclass
class FitResult:
    """Result of a curve fit."""
    params: np.ndarray
    errors: np.ndarray
    r_squared: float
    x_range: Tuple[float, float]  # (x_min, x_max) that was fitted
    model_name: str
    param_names: List[str]
    param_units: List[str]
    extra_results: Optional[Dict[str, Tuple[float, str]]] = None  # e.g., {'separation': (value, unit)}


def parse_unit(label: str) -> str:
    """Extract unit from axis label like 'Frequency (Hz)' → 'Hz'."""
    match = re.search(r'\(([^)]+)\)', label)
    return match.group(1) if match else ''


# --- Fitting Functions ---

def lorentzian(x, amplitude, center, width, offset):
    """
    Lorentzian peak function.
    f(x) = amplitude * (width/2)² / ((x - center)² + (width/2)²) + offset
    """
    return amplitude * (width/2)**2 / ((x - center)**2 + (width/2)**2) + offset


def double_lorentzian(x, amp1, center1, width1, amp2, center2, width2, offset):
    """
    Sum of two Lorentzian peaks.
    f(x) = L1(x) + L2(x) + offset
    """
    L1 = amp1 * (width1/2)**2 / ((x - center1)**2 + (width1/2)**2)
    L2 = amp2 * (width2/2)**2 / ((x - center2)**2 + (width2/2)**2)
    return L1 + L2 + offset


def exponential_decay(x, amplitude, tau, offset):
    """
    Exponential decay function.
    f(x) = amplitude * exp(-x / tau) + offset
    """
    return amplitude * np.exp(-x / tau) + offset


def sin_exp_decay(x, amplitude, tau, frequency, phase, offset):
    """
    Exponentially decaying sinusoid.
    f(x) = amplitude * exp(-x / tau) * sin(2π * frequency * x + phase) + offset
    """
    return amplitude * np.exp(-x / tau) * np.sin(2 * np.pi * frequency * x + phase) + offset


def linear(x, slope, intercept):
    """
    Linear function.
    f(x) = slope * x + intercept
    """
    return slope * x + intercept


# --- Fit Model Definitions ---

FIT_MODELS = {
    'Lorentzian': {
        'func': lorentzian,
        'param_names': ['amplitude', 'center', 'width', 'offset'],
        'param_units': ['y', 'x', 'x', 'y'],  # y = y-axis unit, x = x-axis unit
    },
    'Double Lorentzian': {
        'func': double_lorentzian,
        'param_names': ['amp1', 'center1', 'width1', 'amp2', 'center2', 'width2', 'offset'],
        'param_units': ['y', 'x', 'x', 'y', 'x', 'x', 'y'],
        'extra_results': ['separation'],  # |center2 - center1|
    },
    'Exponential Decay': {
        'func': exponential_decay,
        'param_names': ['amplitude', 'tau', 'offset'],
        'param_units': ['y', 'x', 'y'],
    },
    'Sin Exp Decay': {
        'func': sin_exp_decay,
        'param_names': ['amplitude', 'tau', 'frequency', 'phase', 'offset'],
        'param_units': ['y', 'x', '1/x', 'none', 'y'],
    },
    'Linear': {
        'func': linear,
        'param_names': ['slope', 'intercept'],
        'param_units': ['y/x', 'y'],
    },
}


class Fitter:
    """Curve fitting engine."""
    
    @staticmethod
    def fit(x: np.ndarray, y: np.ndarray, model_name: str, 
            initial_guesses: Dict[str, Optional[float]],
            x_unit: str = '', y_unit: str = '') -> FitResult:
        """
        Perform curve fit.
        
        Args:
            x, y: Data arrays
            model_name: Key in FIT_MODELS
            initial_guesses: Dict of param_name -> value (None for unset)
            x_unit, y_unit: Units for display
            
        Returns:
            FitResult object
            
        Raises:
            ValueError: If fit fails
        """
        model = FIT_MODELS[model_name]
        func = model['func']
        param_names = model['param_names']
        
        # Build p0 from initial_guesses
        p0 = []
        for name in param_names:
            val = initial_guesses.get(name)
            if val is None:
                raise ValueError(f"Initial guess required for '{name}'")
            p0.append(val)
        
        # Perform fit
        try:
            popt, pcov = curve_fit(func, x, y, p0=p0, maxfev=10000)
            perr = np.sqrt(np.diag(pcov))
        except Exception as e:
            raise ValueError(f"Fit failed: {str(e)}")
        
        # Calculate R²
        y_fit = func(x, *popt)
        ss_res = np.sum((y - y_fit)**2)
        ss_tot = np.sum((y - np.mean(y))**2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        # Resolve units
        def resolve_unit(unit_type: str) -> str:
            if unit_type == 'x':
                return x_unit
            elif unit_type == 'y':
                return y_unit
            elif unit_type == '1/x':
                return f"1/{x_unit}" if x_unit else ''
            elif unit_type == 'y/x':
                if y_unit and x_unit:
                    return f"{y_unit}/{x_unit}"
                return ''
            else:  # 'none' or unknown
                return ''
        
        param_units_resolved = [resolve_unit(u) for u in model['param_units']]
        
        # Calculate extra results
        extra_results = None
        if 'extra_results' in model:
            extra_results = {}
            if 'separation' in model['extra_results']:
                # For double Lorentzian: |center2 - center1|
                center1_idx = param_names.index('center1')
                center2_idx = param_names.index('center2')
                separation = abs(popt[center2_idx] - popt[center1_idx])
                # Error propagation: sqrt(err1² + err2²)
                sep_error = np.sqrt(perr[center1_idx]**2 + perr[center2_idx]**2)
                extra_results['separation'] = (separation, sep_error, x_unit)
        
        return FitResult(
            params=popt,
            errors=perr,
            r_squared=r_squared,
            x_range=(float(x.min()), float(x.max())),
            model_name=model_name,
            param_names=param_names,
            param_units=param_units_resolved,
            extra_results=extra_results
        )


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


def rotate_s21(data: np.ndarray) -> np.ndarray:
    """
    Rotate S21 complex data to minimize imaginary variance.
    
    Finds the optimal rotation angle that minimizes the variance of the
    imaginary component, then ensures the mean phase is within ±90°.
    Handles NaN values by ignoring them in variance/mean calculations.
    """
    angles = np.linspace(0, 2 * np.pi, 1000)
    variances = [np.nanvar(np.imag(data * np.exp(-1j * angle))) for angle in angles]
    optimal_angle = angles[np.argmin(variances)]
    rotated_data = data * np.exp(-1j * optimal_angle)
    new_angle = np.angle(np.nanmean(rotated_data), deg=True)
    if new_angle > 90 or new_angle < -90:
        rotated_data = rotated_data * np.exp(1j * np.pi)
    return rotated_data


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
        self._is_2d_mode = False  # Track if in 2D mode for fitting

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

        # Linecuts toggle (for 2D only)
        self.linecuts_checkbox = QCheckBox("Show Linecuts")
        self.linecuts_checkbox.setChecked(False)
        self.linecuts_checkbox.toggled.connect(
            lambda c: self._emit('linecuts_toggled', c))
        data_section.add_widget(self.linecuts_checkbox)

        # Rotate S21 checkbox
        self.rotate_s21_checkbox = QCheckBox("Rotate S21")
        self.rotate_s21_checkbox.setToolTip("Rotate complex S21 data to minimize imaginary variance")
        self.rotate_s21_checkbox.toggled.connect(
            lambda c: self._emit('rotate_s21_toggled', c))
        data_section.add_widget(self.rotate_s21_checkbox)

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
        # Stitch and Overlay buttons side by side
        stitch_overlay_layout = QHBoxLayout()
        self.stitch_btn = QPushButton("📎 Stitch")
        self.stitch_btn.setToolTip("Combine multiple HDF5 files of the same experiment type")
        self.stitch_btn.clicked.connect(lambda: self._emit('stitch_files'))
        stitch_overlay_layout.addWidget(self.stitch_btn)
        
        self.overlay_btn = QPushButton("📊 Overlay")
        self.overlay_btn.setToolTip("Add overlay trace from another file (Shift+Drop also works)")
        self.overlay_btn.clicked.connect(lambda: self._emit('add_overlay'))
        stitch_overlay_layout.addWidget(self.overlay_btn)
        data_section.add_layout(stitch_overlay_layout)
        
        # Overlay list manager (hidden by default, shown when overlays exist)
        self._overlay_groupbox_normal_style = """
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
                border: 1px solid #aaa;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
                background-color: rgba(0, 0, 0, 0.03);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
        """
        self._overlay_groupbox_highlight_style = """
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
                border: 2px solid #4a90d9;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
                background-color: rgba(74, 144, 217, 0.1);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
        """
        self.overlay_container = DroppableGroupBox("Overlays")
        self.overlay_container.set_styles(
            self._overlay_groupbox_normal_style,
            self._overlay_groupbox_highlight_style
        )
        overlay_container_layout = QVBoxLayout(self.overlay_container)
        overlay_container_layout.setContentsMargins(6, 6, 6, 6)
        overlay_container_layout.setSpacing(2)
        
        # List widget for overlays
        self.overlay_list_widget = QWidget()
        self.overlay_list_widget.setAttribute(Qt.WA_TranslucentBackground)
        self.overlay_list_layout = QVBoxLayout(self.overlay_list_widget)
        self.overlay_list_layout.setContentsMargins(0, 0, 0, 0)
        self.overlay_list_layout.setSpacing(2)
        overlay_container_layout.addWidget(self.overlay_list_widget)
        
        # Clear all button
        self.clear_overlays_btn = QPushButton("Clear All")
        self.clear_overlays_btn.setFixedHeight(24)
        self.clear_overlays_btn.clicked.connect(lambda: self._emit('clear_overlays'))
        overlay_container_layout.addWidget(self.clear_overlays_btn)
        
        self.overlay_container.hide()  # Hidden by default
        data_section.add_widget(self.overlay_container)
        
        # Stitch list manager (hidden by default, shown when files are stitched)
        self._stitch_groupbox_normal_style = """
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
                border: 1px solid #aaa;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
                background-color: rgba(0, 0, 0, 0.03);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
        """
        self._stitch_groupbox_highlight_style = """
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
                border: 2px solid #4a90d9;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
                background-color: rgba(74, 144, 217, 0.1);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
        """
        self.stitch_container = DroppableGroupBox("Stitched Files")
        self.stitch_container.set_styles(
            self._stitch_groupbox_normal_style,
            self._stitch_groupbox_highlight_style
        )
        stitch_container_layout = QVBoxLayout(self.stitch_container)
        stitch_container_layout.setContentsMargins(6, 6, 6, 6)
        stitch_container_layout.setSpacing(2)
        
        # List widget for stitched files
        self.stitch_list_widget = QWidget()
        self.stitch_list_widget.setAttribute(Qt.WA_TranslucentBackground)
        self.stitch_list_layout = QVBoxLayout(self.stitch_list_widget)
        self.stitch_list_layout.setContentsMargins(0, 0, 0, 0)
        self.stitch_list_layout.setSpacing(2)
        stitch_container_layout.addWidget(self.stitch_list_widget)
        
        # Clear all button
        self.clear_stitch_btn = QPushButton("Clear All")
        self.clear_stitch_btn.setFixedHeight(24)
        self.clear_stitch_btn.clicked.connect(lambda: self._emit('clear_stitch'))
        stitch_container_layout.addWidget(self.clear_stitch_btn)
        
        self.stitch_container.hide()  # Hidden by default
        data_section.add_widget(self.stitch_container)
        
        # Argand mode checkbox
        self.argand_checkbox = QCheckBox("Argand (Complex Plane)")
        self.argand_checkbox.setToolTip("Plot Re[S21] vs Im[S21] - useful for resonator visualization")
        self.argand_checkbox.toggled.connect(lambda c: self._emit('argand_toggled', c))
        data_section.add_widget(self.argand_checkbox)
        
        # Derivative mode controls
        deriv_layout = QHBoxLayout()
        self.derivative_checkbox = QCheckBox("Derivative")
        self.derivative_checkbox.setToolTip("Plot derivative of data with respect to x-axis")
        self.derivative_checkbox.toggled.connect(lambda c: self._emit('derivative_toggled', c))
        deriv_layout.addWidget(self.derivative_checkbox)
        
        deriv_layout.addWidget(QLabel("Smooth:"))
        self.derivative_smoothing_spin = QSpinBox()
        self.derivative_smoothing_spin.setRange(0, 101)
        self.derivative_smoothing_spin.setSingleStep(2)  # Odd numbers work best for Savitzky-Golay
        self.derivative_smoothing_spin.setValue(0)
        self.derivative_smoothing_spin.setToolTip("Smoothing window (0=none, odd values recommended)")
        self.derivative_smoothing_spin.valueChanged.connect(lambda v: self._emit('derivative_smoothing_changed', v))
        self.derivative_smoothing_spin.setFixedWidth(60)
        deriv_layout.addWidget(self.derivative_smoothing_spin)
        deriv_layout.addStretch()
        data_section.add_layout(deriv_layout)

        self.scroll_layout.addWidget(data_section)

        # === Fitting Section (for 1D and 2D linecuts) ===
        self.fitting_section = CollapsibleSection("Fitting", start_collapsed=True)
        
        # --- Standard fitting controls (hidden in Argand mode) ---
        self.standard_fit_container = QWidget()
        standard_fit_layout = QVBoxLayout(self.standard_fit_container)
        standard_fit_layout.setContentsMargins(0, 0, 0, 0)
        standard_fit_layout.setSpacing(4)
        
        # Function selector
        fit_func_layout = QVBoxLayout()
        fit_func_layout.addWidget(QLabel("Function:"))
        self.fit_func_combo = QComboBox()
        self.fit_func_combo.addItems(list(FIT_MODELS.keys()))
        self.fit_func_combo.currentTextChanged.connect(self._on_fit_func_changed)
        fit_func_layout.addWidget(self.fit_func_combo)
        standard_fit_layout.addLayout(fit_func_layout)
        
        # Initial guesses container (will be populated dynamically)
        self.fit_guesses_container = QWidget()
        self.fit_guesses_layout = QFormLayout(self.fit_guesses_container)
        self.fit_guesses_layout.setContentsMargins(0, 0, 0, 0)
        self.fit_guesses_layout.setSpacing(4)
        self.fit_guess_edits = {}  # param_name -> QLineEdit
        standard_fit_layout.addWidget(self.fit_guesses_container)
        
        self.fitting_section.add_widget(self.standard_fit_container)
        
        # --- Resonator fitting controls (shown in Argand mode) ---
        self.resonator_fit_container = QWidget()
        resonator_fit_layout = QVBoxLayout(self.resonator_fit_container)
        resonator_fit_layout.setContentsMargins(0, 0, 0, 0)
        resonator_fit_layout.setSpacing(4)
        
        # Resonator info label
        if HAS_RESONATOR:
            resonator_info = QLabel("Uses resonator package for\nshunt resonator fitting\n(MagnitudeSlopeOffsetPhaseDelay)")
        else:
            resonator_info = QLabel("⚠ resonator package not installed\nInstall with: pip install resonator")
            resonator_info.setStyleSheet("color: #dc2626;")
        resonator_info.setStyleSheet(resonator_info.styleSheet() + "font-size: 10px; font-style: italic;")
        resonator_fit_layout.addWidget(resonator_info)
        
        self.resonator_fit_container.hide()  # Hidden by default
        self.fitting_section.add_widget(self.resonator_fit_container)
        
        # --- Shared fit controls ---
        # Fit buttons
        fit_buttons_layout = QHBoxLayout()
        self.fit_visible_btn = QPushButton("Fit Visible")
        self.fit_visible_btn.setToolTip("Fit data within current view")
        self.fit_visible_btn.clicked.connect(lambda: self._emit('fit_visible'))
        fit_buttons_layout.addWidget(self.fit_visible_btn)
        
        self.fit_all_btn = QPushButton("Fit All")
        self.fit_all_btn.setToolTip("Fit entire dataset")
        self.fit_all_btn.clicked.connect(lambda: self._emit('fit_all'))
        fit_buttons_layout.addWidget(self.fit_all_btn)
        
        self.fit_clear_btn = QPushButton("Clear")
        self.fit_clear_btn.setToolTip("Clear fit results")
        self.fit_clear_btn.clicked.connect(lambda: self._emit('fit_clear'))
        fit_buttons_layout.addWidget(self.fit_clear_btn)
        self.fitting_section.add_layout(fit_buttons_layout)
        
        # Show fit curve checkbox
        self.show_fit_checkbox = QCheckBox("Show fit curve")
        self.show_fit_checkbox.setChecked(True)
        self.show_fit_checkbox.toggled.connect(lambda c: self._emit('show_fit_toggled', c))
        self.fitting_section.add_widget(self.show_fit_checkbox)
        
        # Show residuals checkbox
        self.show_residuals_checkbox = QCheckBox("Show residuals")
        self.show_residuals_checkbox.setChecked(False)
        self.show_residuals_checkbox.toggled.connect(lambda c: self._emit('show_residuals_toggled', c))
        self.fitting_section.add_widget(self.show_residuals_checkbox)
        
        # Results display
        self.fit_results_label = QLabel("")
        self.fit_results_label.setWordWrap(True)
        self.fit_results_label.setStyleSheet("font-family: monospace; font-size: 11px; background: #f5f5f5; padding: 8px; border-radius: 4px;")
        self.fit_results_label.hide()
        self.fitting_section.add_widget(self.fit_results_label)
        
        # Error display (red text)
        self.fit_error_label = QLabel("")
        self.fit_error_label.setWordWrap(True)
        self.fit_error_label.setStyleSheet("color: #dc2626; font-size: 11px;")
        self.fit_error_label.hide()
        self.fitting_section.add_widget(self.fit_error_label)
        
        # Copy results button
        self.copy_fit_btn = QPushButton("Copy Results")
        self.copy_fit_btn.setToolTip("Copy fit results to clipboard")
        self.copy_fit_btn.clicked.connect(lambda: self._emit('copy_fit_results'))
        self.copy_fit_btn.hide()
        self.fitting_section.add_widget(self.copy_fit_btn)
        
        self.scroll_layout.addWidget(self.fitting_section)
        
        # Populate initial guesses for default function
        self._update_fit_guess_fields()
        
        # Track Argand mode state
        self._argand_mode = False

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
                     'gray', 'gray_r', 'bone', 'bone_r', 'Blues', 'Blues_r']
        self.cmap_combo.addItems(colormaps)
        self.cmap_combo.currentTextChanged.connect(self._on_colormap_changed)
        cmap_layout.addWidget(self.cmap_combo)
        self.scale_section.add_layout(cmap_layout)

        # Normalization dropdown
        norm_layout = QVBoxLayout()
        norm_layout.addWidget(QLabel("Normalization:"))
        self.norm_combo = QComboBox()
        self.norm_combo.addItems(['Linear', 'Two Slope', 'Power'])
        self.norm_combo.currentTextChanged.connect(self._on_norm_changed)
        norm_layout.addWidget(self.norm_combo)
        self.scale_section.add_layout(norm_layout)

        # Two Slope controls (vcenter)
        self.twoslope_controls = QWidget()
        twoslope_layout = QFormLayout(self.twoslope_controls)
        twoslope_layout.setContentsMargins(0, 0, 0, 0)
        self.vcenter_edit = QLineEdit()
        self.vcenter_edit.setPlaceholderText("auto (median)")
        self.vcenter_edit.setToolTip("Center value for two-slope normalization. Leave empty for auto (median).")
        self.vcenter_edit.editingFinished.connect(self._on_vcenter_changed)
        twoslope_layout.addRow("Center:", self.vcenter_edit)
        self.twoslope_controls.hide()
        self.scale_section.add_widget(self.twoslope_controls)

        # Power norm controls (gamma)
        self.power_controls = QWidget()
        power_layout = QFormLayout(self.power_controls)
        power_layout.setContentsMargins(0, 0, 0, 0)
        self.gamma_spin = QDoubleSpinBox()
        self.gamma_spin.setRange(0.1, 3.0)
        self.gamma_spin.setDecimals(2)
        self.gamma_spin.setValue(0.5)
        self.gamma_spin.setSingleStep(0.1)
        self.gamma_spin.setToolTip("Gamma < 1 enhances weak features, > 1 emphasizes peaks")
        self.gamma_spin.valueChanged.connect(self._on_gamma_changed)
        power_layout.addRow("Gamma:", self.gamma_spin)
        self.power_controls.hide()
        self.scale_section.add_widget(self.power_controls)

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

        # Set Limits button
        self.set_limits_btn = QPushButton("Set Limits...")
        self.set_limits_btn.setToolTip("Manually set X and Y axis limits")
        self.set_limits_btn.clicked.connect(lambda: self._emit('set_limits'))
        axes_section.add_widget(self.set_limits_btn)

        # Zoom controls
        zoom_layout = QHBoxLayout()
        self.zoom_btn = QPushButton("🔍 Zoom")
        self.zoom_btn.setToolTip("Click and drag on plot to zoom. Press Escape to cancel.")
        self.zoom_btn.clicked.connect(lambda: self._emit('start_zoom'))
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

        # Colorbar shrink (for 2D plots)
        self.cbar_shrink_widget = QWidget()
        cbar_shrink_layout = QHBoxLayout(self.cbar_shrink_widget)
        cbar_shrink_layout.setContentsMargins(0, 0, 0, 0)
        cbar_shrink_layout.addWidget(QLabel("Colorbar Shrink:"))
        self.cbar_shrink_spin = QDoubleSpinBox()
        self.cbar_shrink_spin.setRange(0.1, 1.0)
        self.cbar_shrink_spin.setValue(1.0)
        self.cbar_shrink_spin.setSingleStep(0.05)
        self.cbar_shrink_spin.setToolTip("Shrink factor for colorbar (1.0 = full size)")
        self.cbar_shrink_spin.valueChanged.connect(self._on_cbar_shrink_changed)
        cbar_shrink_layout.addWidget(self.cbar_shrink_spin)
        appearance_section.add_widget(self.cbar_shrink_widget)

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
        
        # Fit color (initially hidden)
        self.fit_color_layout = QVBoxLayout()
        self.fit_color_label = QLabel("Fit Color:")
        self.fit_color_layout.addWidget(self.fit_color_label)
        self.fit_color_button = QPushButton()
        self.fit_color_button.setFixedSize(50, 24)
        self.fit_color_button.setStyleSheet(f"background-color: {self.settings.fit_color};")
        self.fit_color_button.clicked.connect(self._pick_fit_color)
        self.fit_color_layout.addWidget(self.fit_color_button)
        colors_layout.addLayout(self.fit_color_layout)
        self.fit_color_label.hide()
        self.fit_color_button.hide()
        
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

        # Fit line style controls (initially hidden, shown when fit is successful)
        self.fit_style_container = QWidget()
        fit_style_layout = QVBoxLayout(self.fit_style_container)
        fit_style_layout.setContentsMargins(0, 0, 0, 0)
        fit_style_layout.setSpacing(4)
        
        # Fit line width
        fit_lw_layout = QHBoxLayout()
        fit_lw_layout.addWidget(QLabel("Fit Line Width:"))
        self.fit_linewidth_spin = QDoubleSpinBox()
        self.fit_linewidth_spin.setRange(0.5, 5.0)
        self.fit_linewidth_spin.setValue(1.5)
        self.fit_linewidth_spin.setSingleStep(0.5)
        self.fit_linewidth_spin.valueChanged.connect(self._on_fit_linewidth_changed)
        fit_lw_layout.addWidget(self.fit_linewidth_spin)
        fit_style_layout.addLayout(fit_lw_layout)
        
        # Fit line style
        fit_ls_layout = QHBoxLayout()
        fit_ls_layout.addWidget(QLabel("Fit Line Style:"))
        self.fit_linestyle_combo = QComboBox()
        self.fit_line_styles = [
            ('Solid', '-'),
            ('Dashed', '--'),
            ('Dotted', ':'),
            ('Dash-Dot', '-.'),
        ]
        for name, _ in self.fit_line_styles:
            self.fit_linestyle_combo.addItem(name)
        self.fit_linestyle_combo.setCurrentIndex(1)  # Default to Dashed
        self.fit_linestyle_combo.currentIndexChanged.connect(self._on_fit_linestyle_changed)
        fit_ls_layout.addWidget(self.fit_linestyle_combo)
        fit_style_layout.addLayout(fit_ls_layout)
        
        self.fit_style_container.hide()
        appearance_section.add_widget(self.fit_style_container)

        # Separator
        appearance_section.add_widget(QLabel(""))  # spacer

        # Figure size button
        self.figsize_btn = QPushButton("Figure Size...")
        self.figsize_btn.setToolTip("Change figure dimensions")
        self.figsize_btn.clicked.connect(lambda: self._emit('change_figsize'))
        appearance_section.add_widget(self.figsize_btn)

        # Import/Export style buttons
        style_buttons_layout = QHBoxLayout()
        self.import_style_btn = QPushButton("📥 Import Style")
        self.import_style_btn.setToolTip("Load appearance settings from JSON file (Ctrl+T)")
        self.import_style_btn.clicked.connect(lambda: self._emit('import_style'))
        style_buttons_layout.addWidget(self.import_style_btn)
        
        self.export_style_btn = QPushButton("📤 Export Style")
        self.export_style_btn.setToolTip("Save appearance settings to JSON file (Ctrl+Shift+E)")
        self.export_style_btn.clicked.connect(lambda: self._emit('export_style'))
        style_buttons_layout.addWidget(self.export_style_btn)
        appearance_section.add_layout(style_buttons_layout)

        self.scroll_layout.addWidget(appearance_section)

        # === Annotate Section ===
        annotate_section = CollapsibleSection("Annotate", start_collapsed=True)

        # Add Callout and Add Delta Callout buttons side by side
        callout_buttons_layout = QHBoxLayout()
        self.add_callout_btn = QPushButton("Add Callout")
        self.add_callout_btn.setToolTip("Click on plot to add one annotation marker. Ctrl+click to delete. Escape to cancel.")
        self.add_callout_btn.clicked.connect(lambda: self._emit('add_callout'))
        callout_buttons_layout.addWidget(self.add_callout_btn)
        
        self.add_delta_callout_btn = QPushButton("Add Δ Callout")
        self.add_delta_callout_btn.setToolTip("Click two points to show difference. Escape to cancel.")
        self.add_delta_callout_btn.clicked.connect(lambda: self._emit('add_delta_callout'))
        callout_buttons_layout.addWidget(self.add_delta_callout_btn)
        annotate_section.add_layout(callout_buttons_layout)
        
        # Clear all callouts button
        self.clear_callouts_btn = QPushButton("Clear All Callouts")
        self.clear_callouts_btn.setToolTip("Clear all callout markers (point and delta)")
        self.clear_callouts_btn.clicked.connect(lambda: self._emit('clear_callouts'))
        annotate_section.add_widget(self.clear_callouts_btn)

        # Add V-Line and H-Line buttons side by side
        line_buttons_layout = QHBoxLayout()
        self.add_vline_btn = QPushButton("Add V-Line")
        self.add_vline_btn.setToolTip("Add a vertical line at a specified x value")
        self.add_vline_btn.clicked.connect(lambda: self._emit('add_vline'))
        line_buttons_layout.addWidget(self.add_vline_btn)
        
        self.add_hline_btn = QPushButton("Add H-Line")
        self.add_hline_btn.setToolTip("Add a horizontal line at a specified y value")
        self.add_hline_btn.clicked.connect(lambda: self._emit('add_hline'))
        line_buttons_layout.addWidget(self.add_hline_btn)
        annotate_section.add_layout(line_buttons_layout)

        # Clear lines button
        self.clear_lines_btn = QPushButton("Clear Lines")
        self.clear_lines_btn.clicked.connect(lambda: self._emit('clear_lines'))
        annotate_section.add_widget(self.clear_lines_btn)

        self.scroll_layout.addWidget(annotate_section)

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

    def _pick_fit_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.settings.fit_color = color.name()
            self.fit_color_button.setStyleSheet(f"background-color: {color.name()};")
            self._emit('settings_changed', self.settings)
    
    def _on_fit_linewidth_changed(self, width: float):
        self.settings.fit_line_width = width
        self._emit('settings_changed', self.settings)
    
    def _on_fit_linestyle_changed(self, index: int):
        _, style_code = self.fit_line_styles[index]
        self.settings.fit_line_style = style_code
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

    def _on_norm_changed(self, norm_text: str):
        """Handle normalization type change."""
        norm_map = {'Linear': 'linear', 'Two Slope': 'twoslope', 'Power': 'power'}
        self.settings.norm_type = norm_map.get(norm_text, 'linear')
        
        # Show/hide relevant controls
        self.twoslope_controls.setVisible(norm_text == 'Two Slope')
        self.power_controls.setVisible(norm_text == 'Power')
        
        self._emit('settings_changed', self.settings)

    def _on_vcenter_changed(self):
        """Handle vcenter value change for two-slope norm."""
        text = self.vcenter_edit.text().strip()
        if text == '':
            self.settings.norm_vcenter = None  # Auto (median)
        else:
            try:
                self.settings.norm_vcenter = float(text)
            except ValueError:
                self.settings.norm_vcenter = None
        self._emit('settings_changed', self.settings)

    def _on_gamma_changed(self, gamma: float):
        """Handle gamma value change for power norm."""
        self.settings.norm_gamma = gamma
        self._emit('settings_changed', self.settings)

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

    def _on_cbar_shrink_changed(self, value: float):
        self.settings.cbar_shrink = value
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

    def _on_fit_func_changed(self, func_name: str):
        """Handle fit function selection change."""
        self._update_fit_guess_fields()
        self._emit('fit_func_changed', func_name)
    
    def _update_fit_guess_fields(self):
        """Update initial guess fields based on selected function."""
        # Clear existing fields
        while self.fit_guesses_layout.count():
            item = self.fit_guesses_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.fit_guess_edits.clear()
        
        # Get selected function
        func_name = self.fit_func_combo.currentText()
        if func_name not in FIT_MODELS:
            return
        
        model = FIT_MODELS[func_name]
        param_names = model['param_names']
        
        # Add label
        header = QLabel("Initial Guesses:")
        header.setStyleSheet("font-weight: bold; font-size: 11px;")
        self.fit_guesses_layout.addRow(header)
        
        # Create QLineEdit for each parameter
        for param in param_names:
            edit = QLineEdit()
            edit.setPlaceholderText("required")
            edit.setToolTip(f"Initial guess for {param}")
            self.fit_guess_edits[param] = edit
            self.fit_guesses_layout.addRow(f"{param}:", edit)
    
    def get_fit_guesses(self) -> Dict[str, Optional[float]]:
        """Get current initial guesses from the UI."""
        guesses = {}
        for param, edit in self.fit_guess_edits.items():
            text = edit.text().strip()
            if text:
                try:
                    guesses[param] = float(text)
                except ValueError:
                    guesses[param] = None
            else:
                guesses[param] = None
        return guesses
    
    def show_fit_results(self, result: 'FitResult'):
        """Display fit results in the sidebar."""
        self.fit_error_label.hide()
        
        lines = []
        for i, (name, value, error, unit) in enumerate(zip(
                result.param_names, result.params, result.errors, result.param_units)):
            unit_str = f" {unit}" if unit else ""
            lines.append(f"{name}: {value:.4g} ± {error:.2g}{unit_str}")
        
        # Add extra results (e.g., separation for double Lorentzian)
        if result.extra_results:
            lines.append("")  # blank line
            for name, (value, error, unit) in result.extra_results.items():
                unit_str = f" {unit}" if unit else ""
                lines.append(f"{name}: {value:.4g} ± {error:.2g}{unit_str}")
        
        lines.append("")
        lines.append(f"R²: {result.r_squared:.6f}")
        
        self.fit_results_label.setText("\n".join(lines))
        self.fit_results_label.show()
        self.copy_fit_btn.show()
        
        # Show fit style controls
        self.fit_color_label.show()
        self.fit_color_button.show()
        self.fit_style_container.show()
    
    def show_fit_error(self, message: str):
        """Display fit error message."""
        self.fit_results_label.hide()
        self.copy_fit_btn.hide()
        self.fit_error_label.setText(f"⚠ {message}")
        self.fit_error_label.show()
    
    def clear_fit_display(self):
        """Clear fit results and error displays."""
        self.fit_results_label.hide()
        self.fit_error_label.hide()
        self.copy_fit_btn.hide()
        
        # Hide fit style controls
        self.fit_color_label.hide()
        self.fit_color_button.hide()
        self.fit_style_container.hide()
    
    def add_overlay_row(self, index: int, label: str, color: str):
        """Add a row to the overlay list for managing an overlay."""
        row_widget = QWidget()
        row_widget.setProperty('overlay_index', index)
        row_widget.setAttribute(Qt.WA_TranslucentBackground)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        
        # Visibility checkbox with label (truncated filename - prioritize ending)
        display_label = label if len(label) <= 20 else "..." + label[-17:]
        visible_cb = QCheckBox(display_label)
        visible_cb.setChecked(True)
        visible_cb.setToolTip(label)  # Full filename in tooltip
        visible_cb.toggled.connect(lambda checked, idx=index: self._emit('overlay_visibility_changed', idx, checked))
        row_layout.addWidget(visible_cb, 1)
        
        # Color button
        color_btn = QPushButton()
        color_btn.setFixedSize(20, 20)
        color_btn.setStyleSheet(f"background-color: {color}; border: 1px solid #888;")
        color_btn.setToolTip("Change overlay color")
        color_btn.clicked.connect(lambda _, idx=index, btn=color_btn: self._pick_overlay_color(idx, btn))
        row_layout.addWidget(color_btn)
        
        # Remove button
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(20, 20)
        remove_btn.setToolTip("Remove this overlay")
        remove_btn.clicked.connect(lambda _, idx=index: self._emit('remove_overlay', idx))
        row_layout.addWidget(remove_btn)
        
        self.overlay_list_layout.addWidget(row_widget)
        
        # Show overlay container if hidden
        self.overlay_container.show()
    
    def _pick_overlay_color(self, index: int, btn: QPushButton):
        """Open color picker for an overlay."""
        color = QColorDialog.getColor()
        if color.isValid():
            btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #888;")
            self._emit('overlay_color_changed', index, color.name())
    
    def remove_overlay_row(self, index: int):
        """Remove a row from the overlay list."""
        # Find and remove the widget with matching index
        for i in range(self.overlay_list_layout.count()):
            widget = self.overlay_list_layout.itemAt(i).widget()
            if widget and widget.property('overlay_index') == index:
                widget.deleteLater()
                break
        
        # Hide container if no overlays left
        if self.overlay_list_layout.count() <= 1:  # Account for pending deleteLater
            QTimer.singleShot(100, self._check_hide_overlay_container)
    
    def _check_hide_overlay_container(self):
        """Check if overlay container should be hidden."""
        if self.overlay_list_layout.count() == 0:
            self.overlay_container.hide()
    
    def clear_overlay_list(self):
        """Clear all overlay rows from the list."""
        while self.overlay_list_layout.count():
            item = self.overlay_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.overlay_container.hide()
    
    def update_overlay_indices(self, overlays: list):
        """Rebuild overlay list with current indices after removal (sorted alphabetically)."""
        self.clear_overlay_list()
        # Sort by filename
        sorted_overlays = sorted(enumerate(overlays), key=lambda x: x[1].label.lower())
        for new_idx, (orig_idx, overlay) in enumerate(sorted_overlays):
            self.add_overlay_row(orig_idx, overlay.label, overlay.color)
        if overlays:
            self.overlay_container.show()
    
    def add_stitch_row(self, index: int, label: str):
        """Add a row to the stitch list for managing a stitched file."""
        row_widget = QWidget()
        row_widget.setProperty('stitch_index', index)
        row_widget.setAttribute(Qt.WA_TranslucentBackground)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        
        # Visibility checkbox with label (truncated filename - prioritize ending)
        display_label = label if len(label) <= 20 else "..." + label[-17:]
        visible_cb = QCheckBox(display_label)
        visible_cb.setChecked(True)
        visible_cb.setToolTip(label)  # Full filename in tooltip
        visible_cb.toggled.connect(lambda checked, idx=index: self._emit('stitch_visibility_changed', idx, checked))
        row_layout.addWidget(visible_cb, 1)
        
        # Remove button
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(20, 20)
        remove_btn.setToolTip("Remove this file from stitch")
        remove_btn.clicked.connect(lambda _, idx=index: self._emit('remove_stitch_file', idx))
        row_layout.addWidget(remove_btn)
        
        self.stitch_list_layout.addWidget(row_widget)
        
        # Show stitch container if hidden
        self.stitch_container.show()
    
    def remove_stitch_row(self, index: int):
        """Remove a row from the stitch list."""
        for i in range(self.stitch_list_layout.count()):
            widget = self.stitch_list_layout.itemAt(i).widget()
            if widget and widget.property('stitch_index') == index:
                widget.deleteLater()
                break
    
    def clear_stitch_list(self):
        """Clear all stitch rows from the list."""
        while self.stitch_list_layout.count():
            item = self.stitch_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.stitch_container.hide()
    
    def update_stitch_list(self, file_paths: list):
        """Rebuild stitch list with current files (sorted alphabetically)."""
        self.clear_stitch_list()
        # Sort by filename
        sorted_paths = sorted(enumerate(file_paths), key=lambda x: os.path.basename(x[1]).lower())
        for new_idx, (orig_idx, path) in enumerate(sorted_paths):
            label = os.path.basename(path)
            self.add_stitch_row(orig_idx, label)
        if file_paths:
            self.stitch_container.show()
    
    def set_stitch_mode(self, enabled: bool):
        """Enable or disable stitch mode - disables overlay when stitching."""
        if enabled:
            self.overlay_btn.setEnabled(False)
            self.overlay_btn.setToolTip("Overlay not available for stitched data")
        else:
            self.overlay_btn.setEnabled(True)
            self.overlay_btn.setToolTip("Add overlay trace from another file (Shift+Drop also works)")
    
    def set_fit_enabled(self, enabled: bool):
        """Enable or disable fitting controls."""
        self.fit_func_combo.setEnabled(enabled)
        self.fit_guesses_container.setEnabled(enabled)
        self.fit_visible_btn.setEnabled(enabled)
        self.fit_all_btn.setEnabled(enabled)
        self.show_fit_checkbox.setEnabled(enabled)
        self.show_residuals_checkbox.setEnabled(enabled)
        if not enabled:
            self.fit_visible_btn.setToolTip("Fitting disabled during live update")
            self.fit_all_btn.setToolTip("Fitting disabled during live update")
        else:
            self.fit_visible_btn.setToolTip("Fit data within current view")
            self.fit_all_btn.setToolTip("Fit entire dataset")
    
    def set_argand_mode(self, argand_on: bool):
        """Switch between standard fitting and resonator fitting UI."""
        self._argand_mode = argand_on
        
        if argand_on:
            # Show resonator controls, hide standard controls
            self.standard_fit_container.hide()
            self.resonator_fit_container.show()
            # Disable fitting if resonator package not installed
            if not HAS_RESONATOR:
                self.fit_visible_btn.setEnabled(False)
                self.fit_all_btn.setEnabled(False)
                self.fit_visible_btn.setToolTip("resonator package not installed")
                self.fit_all_btn.setToolTip("resonator package not installed")
            # Disable derivative in Argand mode
            self.derivative_checkbox.setChecked(False)
            self.derivative_checkbox.setEnabled(False)
            self.derivative_smoothing_spin.setEnabled(False)
        else:
            # Show standard controls, hide resonator controls
            self.standard_fit_container.show()
            self.resonator_fit_container.hide()
            self.fit_visible_btn.setEnabled(True)
            self.fit_all_btn.setEnabled(True)
            self.fit_visible_btn.setToolTip("Fit data within current view")
            self.fit_all_btn.setToolTip("Fit entire dataset")
            # Re-enable derivative controls
            self.derivative_checkbox.setEnabled(True)
            self.derivative_smoothing_spin.setEnabled(True)
        
        # Clear any existing fit display
        self.clear_fit_display()
    
    def set_derivative_mode(self, enabled: bool):
        """Handle derivative mode - disables fitting when enabled."""
        if enabled:
            # Disable fitting when showing derivative
            self.fit_visible_btn.setEnabled(False)
            self.fit_all_btn.setEnabled(False)
            self.fit_visible_btn.setToolTip("Fitting disabled in derivative mode")
            self.fit_all_btn.setToolTip("Fitting disabled in derivative mode")
            # Clear any existing fit display
            self.clear_fit_display()
        else:
            # Re-enable fitting (unless in Argand mode without resonator)
            if self._argand_mode:
                if HAS_RESONATOR:
                    self.fit_visible_btn.setEnabled(True)
                    self.fit_all_btn.setEnabled(True)
                    self.fit_visible_btn.setToolTip("Fit data within current view")
                    self.fit_all_btn.setToolTip("Fit entire dataset")
            else:
                self.fit_visible_btn.setEnabled(True)
                self.fit_all_btn.setEnabled(True)
                self.fit_visible_btn.setToolTip("Fit data within current view")
                self.fit_all_btn.setToolTip("Fit entire dataset")
    
    def show_resonator_results(self, f_r: float, Q_i: float, Q_c: float, Q_t: float, freq_unit: str = 'Hz'):
        """Display resonator fit results in the sidebar."""
        self.fit_error_label.hide()
        
        lines = [
            f"f_r: {f_r:.6e} {freq_unit}",
            f"Q_i: {Q_i:.0f}",
            f"Q_c: {Q_c:.0f}",
            f"Q_t: {Q_t:.0f}",
        ]
        
        self.fit_results_label.setText("\n".join(lines))
        self.fit_results_label.show()
        self.copy_fit_btn.show()
        
        # Show fit style controls
        self.fit_color_label.show()
        self.fit_color_button.show()
        self.fit_style_container.show()
    
    def get_background_model(self) -> str:
        """Get the background model name (fixed to MagnitudeSlopeOffsetPhaseDelay)."""
        return 'MagnitudeSlopeOffsetPhaseDelay'

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
        self._is_2d_mode = is_2d
        self.scale_section.setVisible(is_2d)
        self.linecuts_checkbox.setVisible(is_2d)
        self.z_label_widget.setVisible(is_2d)
        self.cbar_shrink_widget.setVisible(is_2d)
        # Flip Y and Interchange are now available for both 1D and 2D plots
        
        # Fitting: always available for 1D, requires linecuts for 2D
        if is_2d:
            # For 2D, fitting depends on linecuts state
            linecuts_on = self.linecuts_checkbox.isChecked()
            self.set_fit_enabled(linecuts_on)
            if not linecuts_on:
                self.fit_visible_btn.setToolTip("Enable linecuts to use fitting")
                self.fit_all_btn.setToolTip("Enable linecuts to use fitting")
        else:
            # For 1D, fitting is always available
            self.set_fit_enabled(True)
    
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
        # Default to detected plot type if available
        if self.detected_spec and self.detected_spec.y_key:
            self.type_2d.setChecked(True)
        else:
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
        if self.detected_spec and self.detected_spec.data_key in datasets:
            self.data_combo.setCurrentText(self.detected_spec.data_key)
        elif 'S21' in datasets:
            self.data_combo.setCurrentText('S21')
        manual_layout.addRow("Data dataset:", self.data_combo)
        
        # Data label - defaults to dataset name
        default_data_label = self.data_combo.currentText()
        self.data_label_edit = QLineEdit(default_data_label)
        manual_layout.addRow("Data label:", self.data_label_edit)

        x_group = QGroupBox("X-Axis")
        x_layout = QFormLayout()
        self.x_key_combo = QComboBox()
        self.x_key_combo.addItems(datasets)
        self.x_key_combo.setEditable(True)
        # Default to detected x_key if available
        if self.detected_spec and self.detected_spec.x_key in datasets:
            self.x_key_combo.setCurrentText(self.detected_spec.x_key)
        elif 'Frequency' in datasets:
            self.x_key_combo.setCurrentText('Frequency')
        x_layout.addRow("Dataset:", self.x_key_combo)
        # Default label to detected label or dataset name
        default_x_label = self.detected_spec.x_label if self.detected_spec else self.x_key_combo.currentText()
        self.x_label_edit = QLineEdit(default_x_label)
        x_layout.addRow("Label:", self.x_label_edit)
        self.x_scale_spin = QDoubleSpinBox()
        self.x_scale_spin.setDecimals(12)
        self.x_scale_spin.setRange(1e-15, 1e15)
        # Default to detected scale if available
        if self.detected_spec:
            self.x_scale_spin.setValue(self.detected_spec.x_scale)
        else:
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
        # Default to detected y_key if available
        if self.detected_spec and self.detected_spec.y_key and self.detected_spec.y_key in datasets:
            self.y_key_combo.setCurrentText(self.detected_spec.y_key)
        elif 'Power' in datasets:
            self.y_key_combo.setCurrentText('Power')
        elif 'Gate Voltage' in datasets:
            self.y_key_combo.setCurrentText('Gate Voltage')
        y_layout.addRow("Dataset:", self.y_key_combo)
        # Default label to detected label or dataset name
        if self.detected_spec and self.detected_spec.y_label:
            default_y_label = self.detected_spec.y_label
        else:
            default_y_label = self.y_key_combo.currentText()
        self.y_label_edit = QLineEdit(default_y_label)
        y_layout.addRow("Label:", self.y_label_edit)
        self.y_scale_spin = QDoubleSpinBox()
        self.y_scale_spin.setDecimals(12)
        self.y_scale_spin.setRange(1e-15, 1e15)
        # Default to detected scale if available
        if self.detected_spec and self.detected_spec.y_scale:
            self.y_scale_spin.setValue(self.detected_spec.y_scale)
        else:
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
        # Enable/disable Y-axis group based on plot type
        self.y_group.setEnabled(self.type_2d.isChecked())
        manual_layout.addRow(self.y_group)

        inst_layout = QHBoxLayout()
        self.inst_cw = QRadioButton("CW (VNA)")
        self.inst_rfsoc = QRadioButton("RFSOC")
        self.inst_generic = QRadioButton("Generic")
        # Default to detected data type if available
        if self.detected_spec:
            exp_type = self.detected_spec.exp_type
            if exp_type in (ExperimentType.CW_1D, ExperimentType.CW_2D):
                self.inst_cw.setChecked(True)
            elif exp_type in (ExperimentType.RFSOC_1D, ExperimentType.RFSOC_2D):
                self.inst_rfsoc.setChecked(True)
            else:
                self.inst_generic.setChecked(True)
        else:
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

        # Auto-update labels when dataset changes (if label matches old dataset name or is generic)
        def update_data_label(new_text):
            current = self.data_label_edit.text()
            # Update if label is empty or matches any dataset name
            if current == "" or current in datasets:
                self.data_label_edit.setText(new_text)
        
        def update_x_label(new_text):
            current = self.x_label_edit.text()
            # Update if label is generic, empty, or matches any dataset name
            if current in ("X", "") or current in datasets:
                self.x_label_edit.setText(new_text)
        
        def update_y_label(new_text):
            current = self.y_label_edit.text()
            # Update if label is generic, empty, or matches any dataset name
            if current in ("Y", "") or current in datasets:
                self.y_label_edit.setText(new_text)
        
        self.data_combo.currentTextChanged.connect(update_data_label)
        self.x_key_combo.currentTextChanged.connect(update_x_label)
        self.y_key_combo.currentTextChanged.connect(update_y_label)

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
            data_key=data_key,
            data_label=self.data_label_edit.text() or data_key
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
        self.visibility = [True] * len(datasets)  # Track visibility per file
        
        # Update metadata to indicate stitching
        self.metadata['Stitched'] = f"{len(file_paths)} files"
        self.metadata['Source Files'] = ', '.join([os.path.basename(f) for f in file_paths])
        
        # Compute combined axis ranges across all datasets
        self._update_combined_limits()
        
        # For compatibility with existing code, expose first dataset's axes
        self.xs = datasets[0][0]
        self.ys = datasets[0][1]
    
    def _update_combined_limits(self):
        """Recompute combined axis limits from visible datasets."""
        visible_datasets = [d for d, v in zip(self.datasets, self.visibility) if v]
        if visible_datasets:
            all_xs = np.concatenate([d[0] for d in visible_datasets])
            all_ys = np.concatenate([d[1] for d in visible_datasets])
            self._combined_xlim = (float(np.min(all_xs)), float(np.max(all_xs)))
            self._combined_ylim = (float(np.min(all_ys)), float(np.max(all_ys)))
        else:
            # Fallback if nothing visible
            all_xs = np.concatenate([d[0] for d in self.datasets])
            all_ys = np.concatenate([d[1] for d in self.datasets])
            self._combined_xlim = (float(np.min(all_xs)), float(np.max(all_xs)))
            self._combined_ylim = (float(np.min(all_ys)), float(np.max(all_ys)))
    
    def set_visibility(self, index: int, visible: bool):
        """Set visibility of a stitched file."""
        if 0 <= index < len(self.visibility):
            self.visibility[index] = visible
            self._update_combined_limits()
    
    def add_file(self, xs: np.ndarray, ys: np.ndarray, data: np.ndarray, file_path: str):
        """Add a new file to the stitch."""
        self.datasets.append((xs, ys, data))
        self.file_paths.append(file_path)
        self.visibility.append(True)
        self._update_combined_limits()
        # Update metadata
        self.metadata['Stitched'] = f"{len(self.file_paths)} files"
        self.metadata['Source Files'] = ', '.join([os.path.basename(f) for f in self.file_paths])
    
    def remove_file(self, index: int):
        """Remove a file from the stitch by index."""
        if 0 <= index < len(self.datasets) and len(self.datasets) > 1:
            del self.datasets[index]
            del self.file_paths[index]
            del self.visibility[index]
            self._update_combined_limits()
            # Update metadata
            self.metadata['Stitched'] = f"{len(self.file_paths)} files"
            self.metadata['Source Files'] = ', '.join([os.path.basename(f) for f in self.file_paths])
            # Update primary file if needed
            self.file_path = self.file_paths[0]
            self.xs = self.datasets[0][0]
            self.ys = self.datasets[0][1]
    
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
    
    def get_visible_datasets(self) -> List[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """Get only visible (xs, ys, data) tuples for stitched plotting."""
        return [d for d, v in zip(self.datasets, self.visibility) if v]
    
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
        self._callout_added_callback = None

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
        
        # Delta callout mode state
        self._delta_callout_mode = False
        self._delta_callouts = []  # List of ((x1, y1), (x2, y2)) tuples
        self._delta_callout_first_point = None  # Stores first point while waiting for second
        self._delta_callout_added_callback = None
        
        # Rotate S21 state
        self._rotate_s21 = False
        
        # Annotation lines storage - each entry is (value, color, linestyle, linewidth)
        self._vlines = []  # List of (x_value, color, linestyle, linewidth) tuples
        self._hlines = []  # List of (y_value, color, linestyle, linewidth) tuples
        
        # Fitting state
        self._fit_result = None  # FitResult object
        self._fit_line = None    # matplotlib Line2D for fit curve
        self._show_fit = True
        self._show_residuals = False
        self._fit_x_data = None  # x data used for fit
        self._fit_y_data = None  # y data used for fit
        
        # Argand mode state
        self._argand_mode = False
        self._resonator_fitter = None  # Stores resonator.LinearShuntFitter object
        
        # Derivative mode state
        self._show_derivative = False
        self._derivative_smoothing = 0  # 0 = no smoothing
        
        # Overlay state
        self._overlays: List[OverlayData] = []
        
        # Connect mouse events for zoom
        self.canvas.mpl_connect('button_press_event', self._on_mouse_press)
        self.canvas.mpl_connect('button_release_event', self._on_mouse_release)
        self.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        self.canvas.mpl_connect('resize_event', self._on_resize)
        
        # Make widget focusable for keyboard events
        self.setFocusPolicy(Qt.StrongFocus)

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

    def set_callout_added_callback(self, callback):
        """Set callback to be called when a callout is added."""
        self._callout_added_callback = callback

    def set_delta_callout_added_callback(self, callback):
        """Set callback to be called when a delta callout is added."""
        self._delta_callout_added_callback = callback

    def set_zoom_mode(self, enabled: bool):
        """Enable or disable zoom mode."""
        self._zoom_mode = enabled
        if enabled:
            self.canvas.setCursor(Qt.CrossCursor)
            self.setFocus()  # Grab keyboard focus for Escape key
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
            self.setFocus()  # Grab keyboard focus for Escape key
            # Disable zoom mode and delta callout mode
            self._zoom_mode = False
            self._delta_callout_mode = False
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

    def set_delta_callout_mode(self, enabled: bool):
        """Enable or disable delta callout mode."""
        self._delta_callout_mode = enabled
        if enabled:
            self.canvas.setCursor(Qt.CrossCursor)
            self.setFocus()  # Grab keyboard focus for Escape key
            # Disable zoom mode and regular callout mode
            self._zoom_mode = False
            self._callout_mode = False
            self._delta_callout_first_point = None  # Reset first point
        else:
            self.canvas.setCursor(Qt.ArrowCursor)
            self._delta_callout_first_point = None  # Reset first point
            # Remove hover annotation
            if self._hover_annotation is not None:
                try:
                    self._hover_annotation.remove()
                except:
                    pass
                self._hover_annotation = None
                self.canvas.draw_idle()

    def clear_callouts(self):
        """Remove all callout annotations (point and delta)."""
        self._callouts = []
        self._delta_callouts = []
        self.update_plot()

    def set_rotate_s21(self, enabled: bool):
        """Enable or disable S21 rotation."""
        self._rotate_s21 = enabled
        self.update_plot()

    def add_vline(self, x_value: float, color: str = 'green', linestyle: str = '--', linewidth: float = 1.5):
        """Add a vertical line at specified x value with style options."""
        self._vlines.append((x_value, color, linestyle, linewidth))
        self.update_plot()

    def add_hline(self, y_value: float, color: str = 'blue', linestyle: str = '--', linewidth: float = 1.5):
        """Add a horizontal line at specified y value with style options."""
        self._hlines.append((y_value, color, linestyle, linewidth))
        self.update_plot()

    def clear_lines(self):
        """Remove all annotation lines."""
        self._vlines = []
        self._hlines = []
        self.update_plot()

    def _on_mouse_press(self, event):
        """Handle mouse press for zoom or callout."""
        if event.inaxes != self.ax:
            return
        
        # Check for Ctrl key using Qt (more reliable than matplotlib's event.key)
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt
        modifiers = QApplication.keyboardModifiers()
        ctrl_pressed = modifiers == Qt.ControlModifier
        
        # Ctrl+click to delete nearest callout
        if event.button == 1 and ctrl_pressed and self._callouts:
            if event.xdata is not None and event.ydata is not None:
                # Calculate tolerance as 2% of axis range
                xlim = self.ax.get_xlim()
                ylim = self.ax.get_ylim()
                x_tol = abs(xlim[1] - xlim[0]) * 0.02
                y_tol = abs(ylim[1] - ylim[0]) * 0.02
                
                # Find nearest callout (considering interchange state for display)
                min_dist = float('inf')
                nearest_idx = None
                for i, (x_val, y_val) in enumerate(self._callouts):
                    if self._interchanged:
                        # When interchanged: y on X-axis, x on Y-axis
                        dx = (y_val - event.xdata) / x_tol if x_tol > 0 else 0
                        dy = (x_val - event.ydata) / y_tol if y_tol > 0 else 0
                    else:
                        # Normal: x on X-axis, y on Y-axis
                        dx = (x_val - event.xdata) / x_tol if x_tol > 0 else 0
                        dy = (y_val - event.ydata) / y_tol if y_tol > 0 else 0
                    dist = (dx**2 + dy**2) ** 0.5
                    if dist < min_dist:
                        min_dist = dist
                        nearest_idx = i
                
                # If within tolerance (normalized distance < 1), remove it
                if nearest_idx is not None and min_dist < 1.0:
                    self._callouts.pop(nearest_idx)
                    self.update_plot()
            return
        
        # Callout mode - add annotation on click
        if self._callout_mode and event.button == 1:
            if event.xdata is not None:
                # Find nearest data point
                # Find nearest data point based on interchange state
                data = self.data_source.get_data()
                # Apply S21 rotation if enabled
                if self._rotate_s21:
                    data = rotate_s21(data)
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
                # Notify that callout was added (for single-add mode)
                if self._callout_added_callback:
                    self._callout_added_callback()
            return
        
        # Delta callout mode - two clicks to show difference
        if self._delta_callout_mode and event.button == 1:
            if event.xdata is not None:
                # Find nearest data point
                data = self.data_source.get_data()
                if self._rotate_s21:
                    data = rotate_s21(data)
                _, _, transform = self.transforms[self._current_transform]
                try:
                    zs = transform(data)
                except:
                    zs = np.abs(data)
                zs = np.where(np.isinf(zs), np.nan, zs)
                
                if self._interchanged:
                    idx = np.argmin(np.abs(self.xs - event.ydata))
                else:
                    idx = np.argmin(np.abs(self.xs - event.xdata))
                
                x_val = self.xs[idx]
                y_val = zs[idx]
                
                if self._delta_callout_first_point is None:
                    # First click - store first point
                    self._delta_callout_first_point = (x_val, y_val)
                    self.update_plot()  # Show first point marker
                else:
                    # Second click - create delta callout
                    first_point = self._delta_callout_first_point
                    second_point = (x_val, y_val)
                    self._delta_callouts.append((first_point, second_point))
                    self._delta_callout_first_point = None
                    self.update_plot()
                    # Notify that delta callout was added
                    if self._delta_callout_added_callback:
                        self._delta_callout_added_callback()
            return
        
        # Zoom mode
        if self._zoom_mode and event.button == 1:
            self._zoom_start = event.xdata

    def _on_mouse_move(self, event):
        """Handle mouse move for zoom rectangle or callout hover."""
        # Callout mode hover (also works in delta callout mode)
        if (self._callout_mode or self._delta_callout_mode) and not self._zoom_mode:
            if event.inaxes == self.ax and event.xdata is not None:
                # Get transformed data
                data = self.data_source.get_data()
                # Apply S21 rotation if enabled
                if self._rotate_s21:
                    data = rotate_s21(data)
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

    # --- Fitting Methods ---
    
    def fit_data(self, model_name: str, initial_guesses: Dict[str, Optional[float]], 
                 visible_only: bool = False) -> FitResult:
        """
        Perform curve fit on data.
        
        Args:
            model_name: Name of fit model from FIT_MODELS
            initial_guesses: Dict of parameter name -> initial value
            visible_only: If True, fit only visible data range
            
        Returns:
            FitResult object
            
        Raises:
            ValueError: If fit fails
        """
        # Get current data
        label, ylabel, transform = self.transforms[self._current_transform]
        data = self.data_source.get_data()
        
        if self._rotate_s21:
            data = rotate_s21(data)
        
        try:
            y_data = transform(data)
        except Exception:
            y_data = np.abs(data)
        
        x_data = self.xs.copy()
        y_data = np.where(np.isinf(y_data), np.nan, y_data)
        
        # Handle interchanged axes
        if self._interchanged:
            x_data, y_data = y_data, x_data
        
        # Filter to visible range if requested
        if visible_only and self._xlim is not None:
            x_min, x_max = min(self._xlim), max(self._xlim)
            mask = (x_data >= x_min) & (x_data <= x_max)
            x_data = x_data[mask]
            y_data = y_data[mask]
        
        # Remove NaN values
        valid_mask = ~np.isnan(x_data) & ~np.isnan(y_data)
        x_data = x_data[valid_mask]
        y_data = y_data[valid_mask]
        
        if len(x_data) < len(FIT_MODELS[model_name]['param_names']):
            raise ValueError("Not enough data points for fit")
        
        # Store data for residuals
        self._fit_x_data = x_data
        self._fit_y_data = y_data
        
        # Get units from axis labels
        if self._interchanged:
            x_unit = parse_unit(ylabel)
            y_unit = parse_unit(self.data_source.spec.x_label)
        else:
            x_unit = parse_unit(self.data_source.spec.x_label)
            y_unit = parse_unit(ylabel)
        
        # Perform fit
        result = Fitter.fit(x_data, y_data, model_name, initial_guesses, x_unit, y_unit)
        self._fit_result = result
        
        # Redraw to show fit curve
        self.update_plot()
        
        return result
    
    def clear_fit(self):
        """Clear fit results."""
        self._fit_result = None
        self._fit_line = None
        self._fit_x_data = None
        self._fit_y_data = None
        self.update_plot()
    
    def set_show_fit(self, show: bool):
        """Set whether to show fit curve."""
        self._show_fit = show
        self.update_plot()
    
    def set_show_residuals(self, show: bool):
        """Set whether to show residuals plot."""
        self._show_residuals = show
        self.update_plot()
    
    def get_fit_result(self) -> Optional[FitResult]:
        """Get current fit result."""
        return self._fit_result
    
    def _draw_fit_curve(self):
        """Draw fit curve on the plot."""
        if not self._show_fit:
            return
        
        # Argand mode: draw resonator fit
        if self._argand_mode and self._resonator_fitter is not None:
            # Generate fit curve from resonator model using lmfit's eval
            freq = self.xs
            # Use the model's eval method with fitted parameters
            fit_s21 = self._resonator_fitter.model.eval(
                params=self._resonator_fitter.result.params,
                frequency=freq
            )
            
            # Plot the fitted circle
            self.ax.plot(np.real(fit_s21), np.imag(fit_s21),
                         color=self.settings.fit_color,
                         linestyle=self.settings.fit_line_style,
                         linewidth=self.settings.fit_line_width,
                         label='Fit', zorder=10)
            
            # Mark the resonance frequency point
            f_r = self._resonator_fitter.resonance_frequency
            s21_at_resonance = self._resonator_fitter.model.eval(
                params=self._resonator_fitter.result.params,
                frequency=np.array([f_r])
            )
            self.ax.plot(np.real(s21_at_resonance), np.imag(s21_at_resonance),
                         'o', color=self.settings.fit_color,
                         markersize=8, markeredgecolor='white',
                         markeredgewidth=1.5, zorder=11)
            return
        
        # Normal mode: draw standard fit
        if self._fit_result is None:
            return
        
        model = FIT_MODELS[self._fit_result.model_name]
        func = model['func']
        
        # Generate smooth x values for fit curve within the fitted range
        x_min, x_max = self._fit_result.x_range
        x_fit = np.linspace(x_min, x_max, 500)
        y_fit = func(x_fit, *self._fit_result.params)
        
        self.ax.plot(x_fit, y_fit, 
                     color=self.settings.fit_color,
                     linestyle=self.settings.fit_line_style,
                     linewidth=self.settings.fit_line_width, 
                     label='Fit', zorder=10)

    def set_argand_mode(self, enabled: bool):
        """Enable or disable Argand (complex plane) plotting mode."""
        if self._argand_mode != enabled:
            self._argand_mode = enabled
            # Reset zoom when switching modes (axis meaning changes)
            self._xlim = None
            self._ylim = None
            # Reset full limits - they'll be recalculated in update_plot
            self._full_xlim = (self.xs[0], self.xs[-1]) if len(self.xs) > 1 else (0, 1)
            self._full_ylim = None  # Will be computed from data
            # Clear fits when switching modes
            self.clear_fit()
            self._resonator_fitter = None
            # Clear callouts (they have different meaning in each mode)
            self._callouts = []
            self._delta_callouts = []
            self._delta_callout_first_point = None
            self.update_plot()
    
    def set_derivative_mode(self, enabled: bool):
        """Enable or disable derivative plotting mode."""
        if self._show_derivative != enabled:
            self._show_derivative = enabled
            # Reset zoom - y limits will be different for derivative
            self._ylim = None
            self._full_ylim = None
            # Clear fits when switching modes
            self.clear_fit()
            self._resonator_fitter = None
            self.update_plot()
    
    def set_derivative_smoothing(self, window: int):
        """Set the smoothing window for derivative computation."""
        if self._derivative_smoothing != window:
            self._derivative_smoothing = window
            # Only update if derivative mode is on
            if self._show_derivative:
                self._ylim = None
                self._full_ylim = None
                self.update_plot()
    
    def add_overlay(self, overlay: OverlayData):
        """Add an overlay trace."""
        self._overlays.append(overlay)
        self.update_plot()
    
    def remove_overlay(self, index: int):
        """Remove an overlay by index."""
        if 0 <= index < len(self._overlays):
            del self._overlays[index]
            self.update_plot()
    
    def set_overlay_visibility(self, index: int, visible: bool):
        """Set visibility of an overlay."""
        if 0 <= index < len(self._overlays):
            self._overlays[index].visible = visible
            self.update_plot()
    
    def set_overlay_color(self, index: int, color: str):
        """Set color of an overlay."""
        if 0 <= index < len(self._overlays):
            self._overlays[index].color = color
            self.update_plot()
    
    def clear_overlays(self):
        """Remove all overlays."""
        self._overlays.clear()
        self.update_plot()
    
    def get_overlays(self) -> List[OverlayData]:
        """Return list of overlays."""
        return self._overlays
    
    def fit_resonator(self, background_model: str = 'MagnitudeSlopeOffsetPhaseDelay',
                      visible_only: bool = False) -> Tuple[float, float, float, float]:
        """
        Fit resonator data using the resonator package.
        
        Args:
            background_model: Name of background model to use
            visible_only: If True, fit only visible frequency range
            
        Returns:
            Tuple of (f_r, Q_i, Q_c, Q_t)
            
        Raises:
            ImportError: If resonator package not installed
            ValueError: If fit fails
        """
        if not HAS_RESONATOR:
            raise ImportError("resonator package not installed. Install with: pip install resonator")
        
        # Get frequency and complex data
        freq = self.xs.copy()
        data = self.data_source.get_data()
        
        # Apply S21 rotation if enabled
        if self._rotate_s21:
            data = rotate_s21(data)
        
        # Filter to visible range if requested
        if visible_only and self._xlim is not None:
            x_min, x_max = min(self._xlim), max(self._xlim)
            mask = (freq >= x_min) & (freq <= x_max)
            freq = freq[mask]
            data = data[mask]
        
        # Remove NaN values
        valid_mask = ~np.isnan(data)
        freq = freq[valid_mask]
        data = data[valid_mask]
        
        if len(freq) < 10:
            raise ValueError("Not enough data points for resonator fit")
        
        # Use MagnitudeSlopeOffsetPhaseDelay - the most comprehensive background model
        # Dynamically get the class to avoid AttributeError if module structure differs
        try:
            bg_class = getattr(resonator_background, 'MagnitudeSlopeOffsetPhaseDelay')
        except AttributeError:
            raise ValueError("MagnitudeSlopeOffsetPhaseDelay not found in resonator.background module")
        
        try:
            self._resonator_fitter = shunt.LinearShuntFitter(
                frequency=freq,
                data=data,
                background_model=bg_class()
            )
            
            f_r = self._resonator_fitter.resonance_frequency
            Q_i = self._resonator_fitter.Q_i
            Q_c = self._resonator_fitter.Q_c
            Q_t = self._resonator_fitter.Q_t
            
            self.update_plot()
            
            return (f_r, Q_i, Q_c, Q_t)
            
        except Exception as e:
            self._resonator_fitter = None
            raise ValueError(f"Resonator fit failed: {str(e)}")
    
    def clear_resonator_fit(self):
        """Clear resonator fit result."""
        self._resonator_fitter = None
        self.update_plot()

    def set_transform(self, index: int):
        self._current_transform = index
        self.clear_fit()  # Clear fit on transform change
        self.update_plot()

    def update_settings(self, settings: PlotSettings):
        self.settings = settings
        self.update_plot()

    def update_plot(self):
        try:
            self.ax.clear()

            label, ylabel, transform = self.transforms[self._current_transform]
            data = self.data_source.get_data()
            
            # Apply S21 rotation if enabled
            if self._rotate_s21:
                data = rotate_s21(data)

            # Check if Argand mode (complex plane plot)
            if self._argand_mode:
                # Argand plane: plot Re vs Im
                plot_x = np.real(data)
                plot_y = np.imag(data)
                
                # Convert Inf to NaN
                plot_x = np.where(np.isinf(plot_x), np.nan, plot_x)
                plot_y = np.where(np.isinf(plot_y), np.nan, plot_y)
                
                # Determine axis labels based on experiment type
                exp_type = self.data_source.spec.exp_type
                if exp_type in (ExperimentType.RFSOC_1D, ExperimentType.RFSOC_2D):
                    x_label_default = 'I (a.u.)'
                    y_label_default = 'Q (a.u.)'
                else:
                    x_label_default = 'Re[S21]'
                    y_label_default = 'Im[S21]'
                
                # Compute limits with padding
                valid_x = plot_x[~np.isnan(plot_x)]
                valid_y = plot_y[~np.isnan(plot_y)]
                
                if len(valid_x) > 0 and len(valid_y) > 0:
                    x_min, x_max = float(np.min(valid_x)), float(np.max(valid_x))
                    y_min, y_max = float(np.min(valid_y)), float(np.max(valid_y))
                    
                    x_range = x_max - x_min
                    y_range = y_max - y_min
                    
                    x_padding = x_range * self.settings.y_padding if x_range > 0 else 0.1
                    y_padding = y_range * self.settings.y_padding if y_range > 0 else 0.1
                    
                    x_full = (x_min - x_padding, x_max + x_padding)
                    y_full = (y_min - y_padding, y_max + y_padding)
                else:
                    x_full = (-1, 1)
                    y_full = (-1, 1)
                
                # Store for zoom reset
                self._full_xlim = x_full
                self._full_ylim = y_full
            else:
                # Normal transform plot
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
                    
                    # Expand y-limits to include visible overlays
                    if self._overlays and not self._argand_mode:
                        combined_ymin = data_ylim[0]
                        combined_ymax = data_ylim[1]
                        for overlay in self._overlays:
                            if not overlay.visible:
                                continue
                            try:
                                overlay_y = transform(overlay.data)
                                # Apply derivative if enabled
                                if self._show_derivative:
                                    if self._derivative_smoothing > 0:
                                        from scipy.signal import savgol_filter
                                        window = self._derivative_smoothing
                                        if window % 2 == 0:
                                            window += 1
                                        if window > len(overlay_y):
                                            window = len(overlay_y) if len(overlay_y) % 2 == 1 else len(overlay_y) - 1
                                        if window >= 3:
                                            dx = np.mean(np.abs(np.diff(overlay.xs)))
                                            if dx > 0:
                                                overlay_y = savgol_filter(overlay_y, window_length=window, polyorder=min(3, window-1), deriv=1, delta=dx)
                                    else:
                                        overlay_y = np.gradient(overlay_y, overlay.xs)
                                overlay_y = np.where(np.isinf(overlay_y), np.nan, overlay_y)
                                valid_overlay = overlay_y[~np.isnan(overlay_y)]
                                if len(valid_overlay) > 0:
                                    combined_ymin = min(combined_ymin, float(np.min(valid_overlay)))
                                    combined_ymax = max(combined_ymax, float(np.max(valid_overlay)))
                            except:
                                pass
                        # Add padding
                        y_range = combined_ymax - combined_ymin
                        padding = y_range * self.settings.y_padding if y_range > 0 else 0.1
                        self._full_ylim = (combined_ymin - padding, combined_ymax + padding)
                
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
                    
                    # Expand x-limits to include visible overlays
                    x_full = self._full_xlim
                    if self._overlays and not self._argand_mode:
                        xmin, xmax = x_full
                        for overlay in self._overlays:
                            if overlay.visible:
                                xmin = min(xmin, float(np.min(overlay.xs)))
                                xmax = max(xmax, float(np.max(overlay.xs)))
                        x_full = (xmin, xmax)
                        self._full_xlim = x_full
                    y_full = data_ylim

            # Apply derivative if enabled (not in Argand mode)
            if self._show_derivative and not self._argand_mode:
                # Apply smoothing if window > 0
                if self._derivative_smoothing > 0:
                    from scipy.signal import savgol_filter
                    window = self._derivative_smoothing
                    # Ensure window is odd
                    if window % 2 == 0:
                        window += 1
                    # Window must be <= data length
                    if window > len(plot_y):
                        window = len(plot_y) if len(plot_y) % 2 == 1 else len(plot_y) - 1
                    if window >= 3:
                        # Compute derivative using Savitzky-Golay filter
                        dx = np.mean(np.abs(np.diff(plot_x)))
                        if dx > 0:
                            plot_y = savgol_filter(plot_y, window_length=window, polyorder=min(3, window-1), deriv=1, delta=dx)
                else:
                    # Use numpy gradient for unsmoothed derivative
                    plot_y = np.gradient(plot_y, plot_x)
                
                # Update y-axis label to indicate derivative
                y_label_default = f"d({y_label_default})/d({x_label_default})"
                
                # Recompute y limits for derivative data
                valid_deriv = plot_y[~np.isnan(plot_y)]
                if len(valid_deriv) > 0:
                    d_min, d_max = float(np.min(valid_deriv)), float(np.max(valid_deriv))
                    d_range = d_max - d_min
                    d_padding = d_range * self.settings.y_padding if d_range > 0 else 0.1
                    y_full = (d_min - d_padding, d_max + d_padding)
                    self._full_ylim = y_full

            # Build marker kwargs
            marker_kwargs = {}
            if self.settings.marker_style != 'None':
                marker_kwargs['marker'] = self.settings.marker_style
                marker_kwargs['markersize'] = self.settings.marker_size
                marker_kwargs['markerfacecolor'] = self.settings.marker_color
                marker_kwargs['markeredgecolor'] = self.settings.marker_color

            self.ax.plot(plot_x, plot_y, color=self.settings.line_color,
                         linewidth=self.settings.line_width, **marker_kwargs)
            
            # Draw overlays (not in Argand mode)
            if not self._argand_mode:
                label, ylabel_orig, transform = self.transforms[self._current_transform]
                for overlay in self._overlays:
                    if not overlay.visible:
                        continue
                    try:
                        # Apply same transform to overlay data
                        overlay_y = transform(overlay.data)
                        overlay_x = overlay.xs
                        
                        # Apply derivative if enabled
                        if self._show_derivative:
                            if self._derivative_smoothing > 0:
                                from scipy.signal import savgol_filter
                                window = self._derivative_smoothing
                                if window % 2 == 0:
                                    window += 1
                                if window > len(overlay_y):
                                    window = len(overlay_y) if len(overlay_y) % 2 == 1 else len(overlay_y) - 1
                                if window >= 3:
                                    dx = np.mean(np.abs(np.diff(overlay_x)))
                                    if dx > 0:
                                        overlay_y = savgol_filter(overlay_y, window_length=window, polyorder=min(3, window-1), deriv=1, delta=dx)
                            else:
                                overlay_y = np.gradient(overlay_y, overlay_x)
                        
                        # Handle interchange
                        if self._interchanged:
                            self.ax.plot(overlay_y, overlay_x, color=overlay.color,
                                         linewidth=self.settings.line_width, alpha=0.8)
                        else:
                            self.ax.plot(overlay_x, overlay_y, color=overlay.color,
                                         linewidth=self.settings.line_width, alpha=0.8)
                    except Exception as e:
                        print(f"Overlay plot error: {e}")
            
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
            
            # Set aspect ratio BEFORE applying limits
            # For Argand plots, equal aspect makes circles look like circles
            if self._argand_mode:
                self.ax.set_aspect('equal', adjustable='box')
            else:
                self.ax.set_aspect('auto')
            
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

            # Draw annotation lines
            for x_val, color, linestyle, linewidth in self._vlines:
                self.ax.axvline(x=x_val, color=color, linestyle=linestyle, linewidth=linewidth, alpha=0.8)
            for y_val, color, linestyle, linewidth in self._hlines:
                self.ax.axhline(y=y_val, color=color, linestyle=linestyle, linewidth=linewidth, alpha=0.8)

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

            # Draw delta callout first point marker (while waiting for second click)
            if self._delta_callout_first_point is not None:
                x1, y1 = self._delta_callout_first_point
                if self._interchanged:
                    plot_x1 = y1 if not np.isnan(y1) else 0
                    plot_y1 = x1
                else:
                    plot_x1 = x1
                    plot_y1 = y1 if not np.isnan(y1) else 0
                if not np.isnan(plot_x1) and not np.isnan(plot_y1):
                    self.ax.plot(plot_x1, plot_y1, 'ro', markersize=7, markeredgecolor='darkred', markeredgewidth=2)

            # Draw delta callouts (connecting lines with difference annotation)
            for (x1, y1), (x2, y2) in self._delta_callouts:
                # Compute plot positions based on interchange state
                if self._interchanged:
                    plot_x1 = y1 if not np.isnan(y1) else 0
                    plot_y1 = x1
                    plot_x2 = y2 if not np.isnan(y2) else 0
                    plot_y2 = x2
                else:
                    plot_x1 = x1
                    plot_y1 = y1 if not np.isnan(y1) else 0
                    plot_x2 = x2
                    plot_y2 = y2 if not np.isnan(y2) else 0
                
                # Draw markers at both points
                if not np.isnan(plot_x1) and not np.isnan(plot_y1):
                    self.ax.plot(plot_x1, plot_y1, 'ro', markersize=5)
                if not np.isnan(plot_x2) and not np.isnan(plot_y2):
                    self.ax.plot(plot_x2, plot_y2, 'ro', markersize=5)
                
                # Draw connecting line
                self.ax.plot([plot_x1, plot_x2], [plot_y1, plot_y2], 'r-', linewidth=1.5, alpha=0.7)
                
                # Calculate deltas
                dx = x2 - x1
                dy = y2 - y1
                
                # Create annotation at midpoint
                mid_x = (plot_x1 + plot_x2) / 2
                mid_y = (plot_y1 + plot_y2) / 2
                dy_str = 'NaN' if (np.isnan(y1) or np.isnan(y2)) else f'{dy:.4g}'
                ann = self.ax.annotate(
                    f'Δx={dx:.4g}\nΔy={dy_str}',
                    xy=(mid_x, mid_y),
                    xytext=(10, 10), textcoords='offset points',
                    fontsize=9,
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='red', alpha=0.9),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0', color='red')
                )
                ann.draggable()

            # Draw fit curve if available
            self._draw_fit_curve()

            self.figure.tight_layout()
            
            # For Argand mode, reapply limits after tight_layout since it can affect them
            if self._argand_mode:
                if self._xlim is not None:
                    if self._x_flipped:
                        self.ax.set_xlim(self._xlim[1], self._xlim[0])
                    else:
                        self.ax.set_xlim(self._xlim[0], self._xlim[1])
                if self._ylim is not None:
                    if self._y_flipped:
                        self.ax.set_ylim(self._ylim[1], self._ylim[0])
                    else:
                        self.ax.set_ylim(self._ylim[0], self._ylim[1])
            
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
        self._callout_added_callback = None
        
        # Check if this is stitched data
        self._is_stitched = hasattr(data_source, 'is_stitched') and data_source.is_stitched()
        
        # Disable linecuts for stitched data
        self._show_linecuts = False

        self.figure = plt.figure(figsize=(10, 8))
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
        
        # Delta callout mode state
        self._delta_callout_mode = False
        self._delta_callouts = []  # List of ((x1, y1, z1), (x2, y2, z2)) tuples
        self._delta_callout_first_point = None  # Stores first point while waiting for second
        self._delta_callout_added_callback = None
        
        # Rotate S21 state
        self._rotate_s21 = False
        
        # Annotation lines storage - each entry is (value, color, linestyle, linewidth)
        self._vlines = []  # List of (x_value, color, linestyle, linewidth) tuples
        self._hlines = []  # List of (y_value, color, linestyle, linewidth) tuples
        
        # Interchange axes state
        self._interchanged = False
        
        # Fitting state (for horizontal linecut - ax_xcut)
        self._fit_result = None  # FitResult object
        self._fit_line = None    # matplotlib Line2D for fit curve
        self._show_fit = True
        self._show_residuals = False
        self._fit_x_data = None  # x data used for fit
        self._fit_y_data = None  # y data used for fit
        
        # Argand mode state
        self._argand_mode = False
        self._resonator_fitter = None  # Stores resonator.LinearShuntFitter object
        
        # Derivative mode state
        self._show_derivative = False
        self._derivative_smoothing = 0  # 0 = no smoothing
        
        # Overlay state
        self._overlays: List[OverlayData] = []

        # Initialize axes (will be configured in _setup_axes)
        self.ax_2d = None
        self.ax_xcut = None
        self.ax_ycut = None
        self._cbar_ax = None

        self._setup_axes()
        
        # Connect mouse events for zoom
        self.canvas.mpl_connect('button_press_event', self._on_mouse_press)
        self.canvas.mpl_connect('button_release_event', self._on_mouse_release)
        self.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        self.canvas.mpl_connect('resize_event', self._on_resize)
        self.canvas.mpl_connect('draw_event', self._on_draw)
        
        # Make widget focusable for keyboard events
        self.setFocusPolicy(Qt.StrongFocus)

        # Modern thin-bar slider style
        self._slider_style_v = """
            QSlider::groove:vertical {
                background: transparent;
                width: 20px;
            }
            QSlider::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #94a3b8, stop:0.5 #64748b, stop:1 #94a3b8);
                height: 6px;
                margin: 0 4px;
                border-radius: 2px;
            }
            QSlider::handle:vertical:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #64748b, stop:0.5 #475569, stop:1 #64748b);
            }
            QSlider::add-page:vertical {
                background: rgba(100, 116, 139, 0.25);
                margin: 0 7px;
                border-radius: 3px;
            }
            QSlider::sub-page:vertical {
                background: rgba(100, 116, 139, 0.1);
                margin: 0 7px;
                border-radius: 3px;
            }
        """
        
        self._slider_style_h = """
            QSlider::groove:horizontal {
                background: transparent;
                height: 20px;
            }
            QSlider::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #94a3b8, stop:0.5 #64748b, stop:1 #94a3b8);
                width: 6px;
                margin: 4px 0;
                border-radius: 2px;
            }
            QSlider::handle:horizontal:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #64748b, stop:0.5 #475569, stop:1 #64748b);
            }
            QSlider::add-page:horizontal {
                background: rgba(100, 116, 139, 0.1);
                margin: 7px 0;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: rgba(100, 116, 139, 0.25);
                margin: 7px 0;
                border-radius: 3px;
            }
        """

        # Build layout with integrated sliders
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Top row: canvas + Y slider
        top_row = QHBoxLayout()
        top_row.setSpacing(2)
        top_row.addWidget(self.canvas, 1)
        
        # Y slider container (for top/bottom spacing)
        self.slider_y_container = QWidget()
        slider_y_layout = QVBoxLayout(self.slider_y_container)
        slider_y_layout.setContentsMargins(0, 0, 0, 0)
        slider_y_layout.setSpacing(0)
        
        self.slider_y_top_spacer = QWidget()
        self.slider_y_top_spacer.setFixedHeight(0)
        slider_y_layout.addWidget(self.slider_y_top_spacer)
        
        self.slider_y = QSlider(Qt.Vertical)
        self.slider_y.setMinimum(0)
        self.slider_y.setMaximum(max(1, len(self.ys) - 1))
        self.slider_y.setValue(0)
        self.slider_y.setInvertedAppearance(True)
        self.slider_y.setFixedWidth(20)
        self.slider_y.valueChanged.connect(self._on_slider_changed)
        self.slider_y.setStyleSheet(self._slider_style_v)
        slider_y_layout.addWidget(self.slider_y, 1)
        
        self.slider_y_bottom_spacer = QWidget()
        self.slider_y_bottom_spacer.setFixedHeight(0)
        slider_y_layout.addWidget(self.slider_y_bottom_spacer)
        
        self.slider_y_container.hide()
        top_row.addWidget(self.slider_y_container)
        
        main_layout.addLayout(top_row, 1)
        
        # Bottom row: X slider + spacer
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(2)
        
        # X slider container (for left/right spacing)
        self.slider_x_container = QWidget()
        slider_x_layout = QHBoxLayout(self.slider_x_container)
        slider_x_layout.setContentsMargins(0, 0, 0, 0)
        slider_x_layout.setSpacing(0)
        
        self.slider_x_left_spacer = QWidget()
        self.slider_x_left_spacer.setFixedWidth(0)
        slider_x_layout.addWidget(self.slider_x_left_spacer)
        
        self.slider_x = QSlider(Qt.Horizontal)
        self.slider_x.setMinimum(0)
        self.slider_x.setMaximum(max(1, len(self.xs) - 1))
        self.slider_x.setValue(0)
        self.slider_x.setFixedHeight(20)
        self.slider_x.valueChanged.connect(self._on_slider_changed)
        self.slider_x.setStyleSheet(self._slider_style_h)
        slider_x_layout.addWidget(self.slider_x, 1)
        
        self.slider_x_right_spacer = QWidget()
        self.slider_x_right_spacer.setFixedWidth(0)
        slider_x_layout.addWidget(self.slider_x_right_spacer)
        
        self.slider_x_container.hide()
        bottom_row.addWidget(self.slider_x_container, 1)
        
        # Corner spacer to align with Y slider
        self.slider_corner_spacer = QWidget()
        self.slider_corner_spacer.setFixedSize(20, 20)
        self.slider_corner_spacer.hide()
        bottom_row.addWidget(self.slider_corner_spacer)
        
        main_layout.addLayout(bottom_row)

    def _update_slider_alignment(self):
        """Update slider spacers to match the 2D plot axes bounds."""
        if self.ax_2d is None:
            return
            
        # Get the axes bounding box in figure coordinates (0-1)
        bbox = self.ax_2d.get_position()
        canvas_width = self.canvas.width()
        canvas_height = self.canvas.height()
        
        # Y slider spacers (top and bottom margins)
        top_margin = int((1 - bbox.y1) * canvas_height)
        bottom_margin = int(bbox.y0 * canvas_height)
        self.slider_y_top_spacer.setFixedHeight(top_margin)
        self.slider_y_bottom_spacer.setFixedHeight(bottom_margin)
        
        # X slider spacers (left and right margins)
        left_margin = int(bbox.x0 * canvas_width)
        right_margin = int((1 - bbox.x1) * canvas_width)
        self.slider_x_left_spacer.setFixedWidth(left_margin)
        self.slider_x_right_spacer.setFixedWidth(right_margin)

    def _on_draw(self, event):
        """Handle canvas draw to update slider alignment."""
        if self._show_linecuts:
            self._update_slider_alignment()

    def _on_slider_changed(self, value):
        """Handle Qt slider value change."""
        # Clear fit when slider moves (data changes)
        self._fit_result = None
        self._fit_line = None
        self._fit_x_data = None
        self._fit_y_data = None
        self._resonator_fitter = None  # Also clear resonator fit
        self.update_plot()

    def _on_resize(self, event):
        """Handle canvas resize by re-applying tight_layout."""
        if self.ax_2d is None:
            return
        
        if self._show_linecuts:
            self.figure.tight_layout(rect=[0, 0, 1.0, 1.0])
        else:
            self.figure.tight_layout(rect=[0, 0, 0.82, 1.0])
        
        self.canvas.draw_idle()

    def set_zoom_completed_callback(self, callback):
        """Set callback to be called when zoom is completed."""
        self._zoom_completed_callback = callback

    def set_callout_added_callback(self, callback):
        """Set callback to be called when a callout is added."""
        self._callout_added_callback = callback

    def set_delta_callout_added_callback(self, callback):
        """Set callback to be called when a delta callout is added."""
        self._delta_callout_added_callback = callback

    def set_zoom_mode(self, enabled: bool):
        """Enable or disable zoom mode."""
        self._zoom_mode = enabled
        if enabled:
            self.canvas.setCursor(Qt.CrossCursor)
            self.setFocus()  # Grab keyboard focus for Escape key
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
        
        # Swap slider max values and current values
        if hasattr(self, 'slider_x') and hasattr(self, 'slider_y'):
            old_x_max = self.slider_x.maximum()
            old_y_max = self.slider_y.maximum()
            old_x_val = self.slider_x.value()
            old_y_val = self.slider_y.value()
            
            self.slider_x.setMaximum(old_y_max)
            self.slider_y.setMaximum(old_x_max)
            self.slider_x.setValue(min(old_y_val, old_y_max))
            self.slider_y.setValue(min(old_x_val, old_x_max))
        
        self.update_plot()

    def set_callout_mode(self, enabled: bool):
        """Enable or disable callout mode."""
        self._callout_mode = enabled
        if enabled:
            self.canvas.setCursor(Qt.CrossCursor)
            self.setFocus()  # Grab keyboard focus for Escape key
            # Disable zoom mode and delta callout mode
            self._zoom_mode = False
            self._delta_callout_mode = False
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

    def set_delta_callout_mode(self, enabled: bool):
        """Enable or disable delta callout mode."""
        self._delta_callout_mode = enabled
        if enabled:
            self.canvas.setCursor(Qt.CrossCursor)
            self.setFocus()  # Grab keyboard focus for Escape key
            # Disable zoom mode and regular callout mode
            self._zoom_mode = False
            self._callout_mode = False
            self._delta_callout_first_point = None  # Reset first point
        else:
            self.canvas.setCursor(Qt.ArrowCursor)
            self._delta_callout_first_point = None  # Reset first point
            # Remove hover annotation
            if self._hover_annotation is not None:
                try:
                    self._hover_annotation.remove()
                except:
                    pass
                self._hover_annotation = None
                self.canvas.draw_idle()

    def clear_callouts(self):
        """Remove all callout annotations (point and delta)."""
        self._callouts = []
        self._delta_callouts = []
        self.update_plot()

    def set_rotate_s21(self, enabled: bool):
        """Enable or disable S21 rotation."""
        self._rotate_s21 = enabled
        self.update_plot()

    def add_vline(self, x_value: float, color: str = 'green', linestyle: str = '--', linewidth: float = 1.5):
        """Add a vertical line at specified x value with style options."""
        self._vlines.append((x_value, color, linestyle, linewidth))
        self.update_plot()

    def add_hline(self, y_value: float, color: str = 'blue', linestyle: str = '--', linewidth: float = 1.5):
        """Add a horizontal line at specified y value with style options."""
        self._hlines.append((y_value, color, linestyle, linewidth))
        self.update_plot()

    def clear_lines(self):
        """Remove all annotation lines."""
        self._vlines = []
        self._hlines = []
        self.update_plot()

    def _on_mouse_press(self, event):
        """Handle mouse press for zoom or callout."""
        if event.inaxes != self.ax_2d:
            return
        
        # Check for Ctrl key using Qt (more reliable than matplotlib's event.key)
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt
        modifiers = QApplication.keyboardModifiers()
        ctrl_pressed = modifiers == Qt.ControlModifier
        
        # Ctrl+click to delete nearest callout
        if event.button == 1 and ctrl_pressed and self._callouts:
            if event.xdata is not None and event.ydata is not None:
                # Calculate tolerance as 2% of axis range
                xlim = self.ax_2d.get_xlim()
                ylim = self.ax_2d.get_ylim()
                x_tol = abs(xlim[1] - xlim[0]) * 0.02
                y_tol = abs(ylim[1] - ylim[0]) * 0.02
                
                # Find nearest callout
                min_dist = float('inf')
                nearest_idx = None
                for i, (x_val, y_val, z_val) in enumerate(self._callouts):
                    # Normalized distance
                    dx = (x_val - event.xdata) / x_tol if x_tol > 0 else 0
                    dy = (y_val - event.ydata) / y_tol if y_tol > 0 else 0
                    dist = (dx**2 + dy**2) ** 0.5
                    if dist < min_dist:
                        min_dist = dist
                        nearest_idx = i
                
                # If within tolerance (normalized distance < 1), remove it
                if nearest_idx is not None and min_dist < 1.0:
                    self._callouts.pop(nearest_idx)
                    self.update_plot()
            return
        
        # Callout mode - add annotation on click
        if self._callout_mode and event.button == 1:
            if event.xdata is not None and event.ydata is not None:
                _, _, transform = self.transforms[self._current_transform]
                
                if self._is_stitched:
                    # Search across all datasets to find nearest point
                    best_dist = float('inf')
                    best_point = None
                    
                    for xs, ys, data in self.data_source.get_visible_datasets():
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
                        # Notify that callout was added (for single-add mode)
                        if self._callout_added_callback:
                            self._callout_added_callback()
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
                    # Notify that callout was added (for single-add mode)
                    if self._callout_added_callback:
                        self._callout_added_callback()
            return
        
        # Delta callout mode - two clicks to show difference
        if self._delta_callout_mode and event.button == 1:
            if event.xdata is not None and event.ydata is not None:
                _, _, transform = self.transforms[self._current_transform]
                
                if self._is_stitched:
                    # Search across all datasets to find nearest point
                    best_dist = float('inf')
                    best_point = None
                    
                    for xs, ys, data in self.data_source.get_visible_datasets():
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
                        if self._delta_callout_first_point is None:
                            self._delta_callout_first_point = best_point
                            self.update_plot()
                        else:
                            self._delta_callouts.append((self._delta_callout_first_point, best_point))
                            self._delta_callout_first_point = None
                            self.update_plot()
                            if self._delta_callout_added_callback:
                                self._delta_callout_added_callback()
                else:
                    # Single dataset
                    x_idx = np.argmin(np.abs(self.xs - event.xdata))
                    y_idx = np.argmin(np.abs(self.ys - event.ydata))
                    x_val = self.xs[x_idx]
                    y_val = self.ys[y_idx]
                    
                    data = self.data_source.get_data()
                    try:
                        zs = transform(data)
                    except:
                        zs = np.abs(data)
                    zs = np.where(np.isinf(zs), np.nan, zs)
                    if getattr(self, '_interchanged', False):
                        zs = zs.T
                    z_val = zs[y_idx, x_idx] if zs.ndim > 1 else zs[x_idx]
                    
                    point = (x_val, y_val, z_val)
                    
                    if self._delta_callout_first_point is None:
                        self._delta_callout_first_point = point
                        self.update_plot()
                    else:
                        self._delta_callouts.append((self._delta_callout_first_point, point))
                        self._delta_callout_first_point = None
                        self.update_plot()
                        if self._delta_callout_added_callback:
                            self._delta_callout_added_callback()
            return
        
        # Zoom mode
        if self._zoom_mode and event.button == 1:
            self._zoom_start = (event.xdata, event.ydata)

    def _on_mouse_move(self, event):
        """Handle mouse move for zoom rectangle or callout hover."""
        # Callout mode hover (also works in delta callout mode)
        if (self._callout_mode or self._delta_callout_mode) and not self._zoom_mode:
            if event.inaxes == self.ax_2d and event.xdata is not None and event.ydata is not None:
                _, _, transform = self.transforms[self._current_transform]
                
                if self._is_stitched:
                    # Search across all datasets to find nearest point
                    best_dist = float('inf')
                    best_point = None
                    
                    for xs, ys, data in self.data_source.get_visible_datasets():
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
        """Setup axes based on linecut visibility.
        
        Uses subplots for main plots (tight_layout compatible) and 
        manual add_axes for colorbar.
        """
        self.figure.clear()
        self._colorbar = None
        self._cbar_ax = None
        self._pcm = None

        if self._show_linecuts:
            # Layout with linecuts: 2x2 grid using subplots
            self.ax_2d = self.figure.add_subplot(2, 2, 1)   # top-left
            self.ax_xcut = self.figure.add_subplot(2, 2, 2) # top-right
            self.ax_ycut = self.figure.add_subplot(2, 2, 3) # bottom-left
            # bottom-right (2,2,4) is where we'll put the horizontal colorbar
            
            # Apply tight_layout
            self.figure.tight_layout(rect=[0, 0, 1.0, 1.0])
            
            # Horizontal colorbar placeholder (position will be set in update_plot to match ax_xcut)
            self._cbar_ax = self.figure.add_axes([0.57, 0.45, 0.33, 0.03])
            
            # Show slider containers
            if hasattr(self, 'slider_y_container'):
                self.slider_y_container.show()
                self.slider_x_container.show()
                self.slider_corner_spacer.show()
        else:
            # Layout without linecuts: single plot using subplot
            self.ax_2d = self.figure.add_subplot(111)
            self.ax_xcut = None
            self.ax_ycut = None
            
            # Apply tight_layout with rect to leave room for colorbar on right
            self.figure.tight_layout(rect=[0, 0, 0.82, 1.0])
            
            # Vertical colorbar
            self._cbar_ax = self.figure.add_axes([0.83, 0.15, 0.03, 0.73])
            
            # Hide slider containers
            if hasattr(self, 'slider_y_container'):
                self.slider_y_container.hide()
                self.slider_x_container.hide()
                self.slider_corner_spacer.hide()

    def set_show_linecuts(self, show: bool):
        """Toggle linecut visibility. Disabled for stitched data."""
        if self._is_stitched:
            return  # Linecuts not supported for stitched data
        if show != self._show_linecuts:
            self._show_linecuts = show
            self._setup_axes()
            self.update_plot()

    # --- Fitting Methods (for horizontal linecut) ---
    
    def fit_data(self, model_name: str, initial_guesses: Dict[str, Optional[float]], 
                 visible_only: bool = False) -> FitResult:
        """
        Perform curve fit on horizontal linecut data.
        
        Args:
            model_name: Name of fit model from FIT_MODELS
            initial_guesses: Dict of parameter name -> initial value
            visible_only: If True, fit only visible data range
            
        Returns:
            FitResult object
            
        Raises:
            ValueError: If fit fails or linecuts not shown
        """
        if not self._show_linecuts:
            raise ValueError("Enable linecuts to use fitting")
        
        if self._is_stitched:
            raise ValueError("Fitting not supported for stitched data")
        
        # Get current linecut data
        label, ylabel, transform = self.transforms[self._current_transform]
        data = self.data_source.get_data()
        
        if self._rotate_s21:
            data = rotate_s21(data)
        
        try:
            zs = transform(data)
        except Exception:
            zs = np.abs(data)
        
        zs = np.where(np.isinf(zs), np.nan, zs)
        
        # Transpose data if interchanged (same as update_plot does)
        if self._interchanged:
            zs = zs.T
        
        # Always take horizontal linecut at slider_y position
        # (self.xs and self.ys have already been swapped by interchange)
        y_idx = int(self.slider_y.value())
        y_idx = max(0, min(y_idx, zs.shape[0] - 1))
        
        x_data = self.xs.copy()
        y_data = zs[y_idx, :]
        
        # Units come from current spec labels (already swapped by interchange)
        x_label_for_unit = self.data_source.spec.x_label
        
        # Filter to visible range if requested
        if visible_only and self._xlim is not None:
            x_min, x_max = min(self._xlim), max(self._xlim)
            mask = (x_data >= x_min) & (x_data <= x_max)
            x_data = x_data[mask]
            y_data = y_data[mask]
        
        # Remove NaN values
        valid_mask = ~np.isnan(x_data) & ~np.isnan(y_data)
        x_data = x_data[valid_mask]
        y_data = y_data[valid_mask]
        
        if len(x_data) < len(FIT_MODELS[model_name]['param_names']):
            raise ValueError("Not enough data points for fit")
        
        # Store data for residuals
        self._fit_x_data = x_data
        self._fit_y_data = y_data
        
        # Get units from axis labels
        x_unit = parse_unit(x_label_for_unit)
        y_unit = parse_unit(ylabel)
        
        # Perform fit
        result = Fitter.fit(x_data, y_data, model_name, initial_guesses, x_unit, y_unit)
        self._fit_result = result
        
        # Redraw to show fit curve
        self.update_plot()
        
        return result
    
    def clear_fit(self):
        """Clear fit results."""
        self._fit_result = None
        self._fit_line = None
        self._fit_x_data = None
        self._fit_y_data = None
        self.update_plot()
    
    def set_show_fit(self, show: bool):
        """Set whether to show fit curve."""
        self._show_fit = show
        self.update_plot()
    
    def set_show_residuals(self, show: bool):
        """Set whether to show residuals plot."""
        self._show_residuals = show
        self.update_plot()
    
    def get_fit_result(self) -> Optional[FitResult]:
        """Get current fit result."""
        return self._fit_result
    
    def _draw_fit_curve(self):
        """Draw fit curve on the horizontal linecut plot."""
        if not self._show_fit:
            return
        
        if not self._show_linecuts or self.ax_xcut is None:
            return
        
        # Argand mode: draw resonator fit
        if self._argand_mode and self._resonator_fitter is not None:
            # Generate fit curve from resonator model using lmfit's eval
            freq = self.xs
            fit_s21 = self._resonator_fitter.model.eval(
                params=self._resonator_fitter.result.params,
                frequency=freq
            )
            
            # Plot the fitted circle
            self.ax_xcut.plot(np.real(fit_s21), np.imag(fit_s21),
                              color=self.settings.fit_color,
                              linestyle=self.settings.fit_line_style,
                              linewidth=self.settings.fit_line_width,
                              label='Fit', zorder=10)
            
            # Mark the resonance frequency point
            f_r = self._resonator_fitter.resonance_frequency
            s21_at_resonance = self._resonator_fitter.model.eval(
                params=self._resonator_fitter.result.params,
                frequency=np.array([f_r])
            )
            self.ax_xcut.plot(np.real(s21_at_resonance), np.imag(s21_at_resonance),
                              'o', color=self.settings.fit_color,
                              markersize=8, markeredgecolor='white',
                              markeredgewidth=1.5, zorder=11)
            return
        
        # Normal mode: draw standard fit
        if self._fit_result is None:
            return
        
        model = FIT_MODELS[self._fit_result.model_name]
        func = model['func']
        
        # Generate smooth x values for fit curve within the fitted range
        x_min, x_max = self._fit_result.x_range
        x_fit = np.linspace(x_min, x_max, 500)
        y_fit = func(x_fit, *self._fit_result.params)
        
        self.ax_xcut.plot(x_fit, y_fit, 
                          color=self.settings.fit_color,
                          linestyle=self.settings.fit_line_style,
                          linewidth=self.settings.fit_line_width, 
                          label='Fit', zorder=10)

    def set_argand_mode(self, enabled: bool):
        """Enable or disable Argand (complex plane) plotting mode for linecut."""
        if self._argand_mode != enabled:
            self._argand_mode = enabled
            # Clear fits when switching modes
            self.clear_fit()
            self._resonator_fitter = None
            self.update_plot()
    
    def set_derivative_mode(self, enabled: bool):
        """Enable or disable derivative plotting mode."""
        if self._show_derivative != enabled:
            self._show_derivative = enabled
            # Clear fits when switching modes
            self.clear_fit()
            self._resonator_fitter = None
            self.update_plot()
    
    def set_derivative_smoothing(self, window: int):
        """Set the smoothing window for derivative computation."""
        if self._derivative_smoothing != window:
            self._derivative_smoothing = window
            # Only update if derivative mode is on
            if self._show_derivative:
                self.update_plot()
    
    def add_overlay(self, overlay: OverlayData):
        """Add an overlay trace."""
        self._overlays.append(overlay)
        self.update_plot()
    
    def remove_overlay(self, index: int):
        """Remove an overlay by index."""
        if 0 <= index < len(self._overlays):
            del self._overlays[index]
            self.update_plot()
    
    def set_overlay_visibility(self, index: int, visible: bool):
        """Set visibility of an overlay."""
        if 0 <= index < len(self._overlays):
            self._overlays[index].visible = visible
            self.update_plot()
    
    def set_overlay_color(self, index: int, color: str):
        """Set color of an overlay."""
        if 0 <= index < len(self._overlays):
            self._overlays[index].color = color
            self.update_plot()
    
    def clear_overlays(self):
        """Remove all overlays."""
        self._overlays.clear()
        self.update_plot()
    
    def get_overlays(self) -> List[OverlayData]:
        """Return list of overlays."""
        return self._overlays
    
    def fit_resonator(self, background_model: str = 'MagnitudeSlopeOffsetPhaseDelay',
                      visible_only: bool = False) -> Tuple[float, float, float, float]:
        """
        Fit resonator data using the resonator package.
        
        Args:
            background_model: Name of background model to use
            visible_only: If True, fit only visible frequency range
            
        Returns:
            Tuple of (f_r, Q_i, Q_c, Q_t)
            
        Raises:
            ImportError: If resonator package not installed
            ValueError: If fit fails
        """
        if not HAS_RESONATOR:
            raise ImportError("resonator package not installed. Install with: pip install resonator")
        
        if self._is_stitched:
            raise ValueError("Resonator fitting not supported for stitched data")
        
        # Get frequency array and current slice complex data
        raw_data = self.data_source.get_data()
        
        if self._rotate_s21:
            raw_data = rotate_s21(raw_data)
        
        # Transpose if interchanged
        if self._interchanged:
            raw_data = raw_data.T
        
        # Get horizontal slice at current slider position
        y_idx = int(self.slider_y.value())
        y_idx = max(0, min(y_idx, raw_data.shape[0] - 1))
        
        freq = self.xs.copy()
        data = raw_data[y_idx, :]
        
        # Filter to visible range if requested
        if visible_only and self._xlim is not None:
            x_min, x_max = min(self._xlim), max(self._xlim)
            mask = (freq >= x_min) & (freq <= x_max)
            freq = freq[mask]
            data = data[mask]
        
        # Remove NaN values
        valid_mask = ~np.isnan(data)
        freq = freq[valid_mask]
        data = data[valid_mask]
        
        if len(freq) < 10:
            raise ValueError("Not enough data points for resonator fit")
        
        # Use MagnitudeSlopeOffsetPhaseDelay - the most comprehensive background model
        # Dynamically get the class to avoid AttributeError if module structure differs
        try:
            bg_class = getattr(resonator_background, 'MagnitudeSlopeOffsetPhaseDelay')
        except AttributeError:
            raise ValueError("MagnitudeSlopeOffsetPhaseDelay not found in resonator.background module")
        
        try:
            self._resonator_fitter = shunt.LinearShuntFitter(
                frequency=freq,
                data=data,
                background_model=bg_class()
            )
            
            f_r = self._resonator_fitter.resonance_frequency
            Q_i = self._resonator_fitter.Q_i
            Q_c = self._resonator_fitter.Q_c
            Q_t = self._resonator_fitter.Q_t
            
            self.update_plot()
            
            return (f_r, Q_i, Q_c, Q_t)
            
        except Exception as e:
            self._resonator_fitter = None
            raise ValueError(f"Resonator fit failed: {str(e)}")
    
    def clear_resonator_fit(self):
        """Clear resonator fit result."""
        self._resonator_fitter = None
        self.update_plot()

    def set_transform(self, index: int):
        self._current_transform = index
        self.clear_fit()  # Clear fit on transform change
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
                for xs, ys, data in self.data_source.get_visible_datasets():
                    # Apply S21 rotation if enabled
                    if self._rotate_s21:
                        data = rotate_s21(data)
                    zs = transform(data)
                    zs = np.where(np.isinf(zs), np.nan, zs)
                    all_mins.append(float(np.nanmin(zs)))
                    all_maxs.append(float(np.nanmax(zs)))
                return min(all_mins), max(all_maxs)
            else:
                data = self.data_source.get_data()
                # Apply S21 rotation if enabled
                if self._rotate_s21:
                    data = rotate_s21(data)
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
            
            # Get slider values if linecuts are shown (Qt sliders)
            if self._show_linecuts and hasattr(self, 'slider_y'):
                y_idx = int(self.slider_y.value())
                x_idx = int(self.slider_x.value())
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
                if not self.settings.autoscale:
                    # Only use manual settings when autoscale is off
                    if self.settings.vmin is not None:
                        vmin = self.settings.vmin
                    if self.settings.vmax is not None:
                        vmax = self.settings.vmax
                
                # Create norm for stitched data
                if self.settings.norm_type == 'twoslope':
                    vcenter = self.settings.norm_vcenter
                    if vcenter is None:
                        # Compute median across all datasets
                        all_data = []
                        for xs, ys, data in self.data_source.get_visible_datasets():
                            if self._rotate_s21:
                                data = rotate_s21(data)
                            try:
                                all_data.append(transform(data).flatten())
                            except:
                                all_data.append(np.abs(data).flatten())
                        vcenter = np.nanmedian(np.concatenate(all_data))
                    vcenter = np.clip(vcenter, vmin + 1e-10, vmax - 1e-10)
                    norm = TwoSlopeNorm(vmin=vmin, vcenter=vcenter, vmax=vmax)
                elif self.settings.norm_type == 'power':
                    norm = PowerNorm(gamma=self.settings.norm_gamma, vmin=vmin, vmax=vmax)
                else:  # linear (default)
                    norm = Normalize(vmin=vmin, vmax=vmax)
                
                pcm = None
                for xs, ys, data in self.data_source.get_visible_datasets():
                    # Apply S21 rotation if enabled
                    if self._rotate_s21:
                        data = rotate_s21(data)
                    try:
                        zs = transform(data)
                    except Exception as e:
                        print(f"Transform error: {e}")
                        zs = np.abs(data)
                    
                    # Convert Inf to NaN
                    zs = np.where(np.isinf(zs), np.nan, zs)
                    
                    pcm = self.ax_2d.pcolormesh(xs, ys, zs,
                                                 cmap=self.settings.colormap, norm=norm)
            else:
                # Single dataset: original behavior
                data = self.data_source.get_data()
                # Apply S21 rotation if enabled
                if self._rotate_s21:
                    data = rotate_s21(data)
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
                
                # Apply derivative along x-axis if enabled (not in Argand mode)
                if self._show_derivative and not self._argand_mode:
                    # Get x-coordinates for derivative
                    x_coords = self.xs
                    
                    # Apply derivative along axis=1 (x-axis direction)
                    if self._derivative_smoothing > 0:
                        from scipy.signal import savgol_filter
                        window = self._derivative_smoothing
                        if window % 2 == 0:
                            window += 1
                        if window > zs.shape[1]:
                            window = zs.shape[1] if zs.shape[1] % 2 == 1 else zs.shape[1] - 1
                        if window >= 3:
                            dx = np.mean(np.abs(np.diff(x_coords)))
                            if dx > 0:
                                # Apply savgol_filter along axis=1 for each row
                                zs = savgol_filter(zs, window_length=window, polyorder=min(3, window-1), deriv=1, delta=dx, axis=1)
                    else:
                        # Use numpy gradient
                        zs = np.gradient(zs, x_coords, axis=1)
                    
                    # Update ylabel to indicate derivative
                    ylabel = f"d({ylabel})/d({self.data_source.spec.x_label})"

                y_idx = min(y_idx, zs.shape[0] - 1) if zs.ndim > 1 else 0
                x_idx = min(x_idx, zs.shape[1] - 1) if zs.ndim > 1 else min(x_idx, len(zs) - 1)

                # Get color limits
                vmin, vmax = self.settings.get_clim(zs)
                
                # Determine actual vmin/vmax for norm (use data range if autoscale)
                actual_vmin = vmin if vmin is not None else np.nanmin(zs)
                actual_vmax = vmax if vmax is not None else np.nanmax(zs)
                
                # Create norm based on settings
                if self.settings.norm_type == 'twoslope':
                    vcenter = self.settings.norm_vcenter
                    if vcenter is None:
                        vcenter = np.nanmedian(zs)
                    # Ensure vcenter is within vmin/vmax range
                    vcenter = np.clip(vcenter, actual_vmin + 1e-10, actual_vmax - 1e-10)
                    norm = TwoSlopeNorm(vmin=actual_vmin, vcenter=vcenter, vmax=actual_vmax)
                elif self.settings.norm_type == 'power':
                    norm = PowerNorm(gamma=self.settings.norm_gamma, vmin=actual_vmin, vmax=actual_vmax)
                else:  # linear (default)
                    norm = Normalize(vmin=actual_vmin, vmax=actual_vmax)

                pcm = self.ax_2d.pcolormesh(self.xs, self.ys, zs,
                                             cmap=self.settings.colormap, norm=norm)
            
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
            
            # Adjust colorbar axes size based on shrink setting (scales both dimensions to maintain aspect ratio)
            if self._cbar_ax is not None:
                if self._show_linecuts:
                    # Horizontal colorbar - align with ax_xcut (top-right plot, directly above colorbar)
                    xcut_pos = self.ax_xcut.get_position()
                    orig_left = xcut_pos.x0
                    orig_width = xcut_pos.x1 - xcut_pos.x0
                    orig_bottom = 0.45  # Keep y-position as is
                    orig_height = 0.03
                    
                    new_width = orig_width * self.settings.cbar_shrink
                    new_height = orig_height * self.settings.cbar_shrink
                    new_left = orig_left + (orig_width - new_width) / 2  # Center horizontally within ax_xcut width
                    new_bottom = orig_bottom + (orig_height - new_height) / 2  # Center vertically
                    self._cbar_ax.set_position([new_left, new_bottom, new_width, new_height])
                else:
                    # Vertical colorbar on right side
                    orig_left, orig_bottom = 0.83, 0.15
                    orig_width, orig_height = 0.03, 0.73
                    
                    new_width = orig_width * self.settings.cbar_shrink
                    new_height = orig_height * self.settings.cbar_shrink
                    new_left = orig_left + (orig_width - new_width) / 2  # Center horizontally
                    new_bottom = orig_bottom + (orig_height - new_height) / 2  # Center vertically
                    self._cbar_ax.set_position([new_left, new_bottom, new_width, new_height])
            
            # Add colorbar to dedicated axes
            if pcm is not None:
                if self._show_linecuts:
                    # Horizontal colorbar
                    self._colorbar = self.figure.colorbar(pcm, cax=self._cbar_ax, orientation='horizontal')
                    z_label = self.settings.z_label_text if self.settings.z_label_text else ylabel
                    self._cbar_ax.set_xlabel(z_label, fontsize=self.settings.label_size)
                else:
                    # Vertical colorbar
                    self._colorbar = self.figure.colorbar(pcm, cax=self._cbar_ax, orientation='vertical')
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
                    if self._argand_mode:
                        # Argand mode: plot Re vs Im for this slice
                        # Get the raw complex data for this slice
                        raw_data = self.data_source.get_data()
                        if self._rotate_s21:
                            raw_data = rotate_s21(raw_data)
                        if self._interchanged:
                            raw_data = raw_data.T
                        slice_data = raw_data[y_idx, :]
                        
                        plot_re = np.real(slice_data)
                        plot_im = np.imag(slice_data)
                        
                        self.ax_xcut.plot(plot_re, plot_im, color=self.settings.line_color,
                                          linewidth=self.settings.line_width, **marker_kwargs)
                        
                        # Set labels for Argand plot
                        exp_type = self.data_source.spec.exp_type
                        if exp_type in (ExperimentType.RFSOC_1D, ExperimentType.RFSOC_2D):
                            self.ax_xcut.set_xlabel('I (a.u.)', fontsize=self.settings.label_size)
                            self.ax_xcut.set_ylabel('Q (a.u.)', fontsize=self.settings.label_size)
                        else:
                            self.ax_xcut.set_xlabel('Re[S21]', fontsize=self.settings.label_size)
                            self.ax_xcut.set_ylabel('Im[S21]', fontsize=self.settings.label_size)
                        
                        # Format title with slice position
                        y_val = self.ys[y_idx]
                        if abs(y_val) >= 1e4 or (abs(y_val) < 1e-2 and y_val != 0):
                            y_val_str = f'{y_val:.3e}'
                        else:
                            y_val_str = f'{y_val:.4g}'
                        self.ax_xcut.set_title(f'{y_label} = {y_val_str}', fontsize=10)
                        
                        # Set equal aspect ratio for Argand plot
                        # Use 'box' adjustable so it doesn't override manual limits
                        self.ax_xcut.set_aspect('equal', adjustable='box')
                    else:
                        # Normal mode: plot transform vs frequency
                        self.ax_xcut.plot(self.xs, zs[y_idx], color=self.settings.line_color,
                                          linewidth=self.settings.line_width, **marker_kwargs)
                        # Format title with 3 decimal places in scientific notation
                        y_val = self.ys[y_idx]
                        if abs(y_val) >= 1e4 or (abs(y_val) < 1e-2 and y_val != 0):
                            y_val_str = f'{y_val:.3e}'
                        else:
                            y_val_str = f'{y_val:.4g}'
                        self.ax_xcut.set_title(f'{y_label} = {y_val_str}', fontsize=10)
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
                        self.ax_xcut.set_aspect('auto')
                        
                        # Draw overlays on horizontal linecut (not in Argand mode)
                        for overlay in self._overlays:
                            if not overlay.visible or not overlay.is_2d:
                                continue
                            try:
                                # Get same y-index slice from overlay
                                label_o, ylabel_o, transform_o = self.transforms[self._current_transform]
                                overlay_zs = transform_o(overlay.data)
                                
                                # Handle transpose for interchange
                                if self._interchanged:
                                    overlay_zs = overlay_zs.T
                                
                                # Apply derivative if enabled
                                if self._show_derivative:
                                    if self._derivative_smoothing > 0:
                                        from scipy.signal import savgol_filter
                                        window = self._derivative_smoothing
                                        if window % 2 == 0:
                                            window += 1
                                        if window > overlay_zs.shape[1]:
                                            window = overlay_zs.shape[1] if overlay_zs.shape[1] % 2 == 1 else overlay_zs.shape[1] - 1
                                        if window >= 3:
                                            dx = np.mean(np.abs(np.diff(overlay.xs)))
                                            if dx > 0:
                                                overlay_zs = savgol_filter(overlay_zs, window_length=window, polyorder=min(3, window-1), deriv=1, delta=dx, axis=1)
                                    else:
                                        overlay_zs = np.gradient(overlay_zs, overlay.xs, axis=1)
                                
                                # Get slice at same index (if within bounds)
                                if overlay_zs.shape[0] > y_idx:
                                    self.ax_xcut.plot(overlay.xs, overlay_zs[y_idx], 
                                                      color=overlay.color,
                                                      linewidth=self.settings.line_width, alpha=0.8)
                            except Exception as e:
                                print(f"Overlay linecut error: {e}")
                        
                if self.settings.grid_enabled:
                    self.ax_xcut.grid(True, alpha=self.settings.grid_alpha, linewidth=self.settings.grid_width)
                # Apply tick settings to linecut
                self.ax_xcut.tick_params(axis='both', which='major',
                                         length=self.settings.tick_size,
                                         width=self.settings.tick_width,
                                         labelsize=self.settings.tick_font_size)
                
                # Draw fit curve on horizontal linecut
                self._draw_fit_curve()

                # Y cut - shows vertical slice at fixed X value
                if zs.ndim > 1 and zs.shape[1] > x_idx:
                    self.ax_ycut.plot(self.ys, zs[:, x_idx], color=self.settings.line_color,
                                      linewidth=self.settings.line_width, **marker_kwargs)
                    # Format title with 3 decimal places in scientific notation
                    x_val = self.xs[x_idx]
                    if abs(x_val) >= 1e4 or (abs(x_val) < 1e-2 and x_val != 0):
                        x_val_str = f'{x_val:.3e}'
                    else:
                        x_val_str = f'{x_val:.4g}'
                    self.ax_ycut.set_title(f'{x_label} = {x_val_str}', fontsize=10)
                    
                    # Draw overlays on vertical linecut
                    for overlay in self._overlays:
                        if not overlay.visible or not overlay.is_2d:
                            continue
                        try:
                            label_o, ylabel_o, transform_o = self.transforms[self._current_transform]
                            overlay_zs = transform_o(overlay.data)
                            
                            if self._interchanged:
                                overlay_zs = overlay_zs.T
                            
                            # Apply derivative if enabled
                            if self._show_derivative:
                                if self._derivative_smoothing > 0:
                                    from scipy.signal import savgol_filter
                                    window = self._derivative_smoothing
                                    if window % 2 == 0:
                                        window += 1
                                    if window > overlay_zs.shape[1]:
                                        window = overlay_zs.shape[1] if overlay_zs.shape[1] % 2 == 1 else overlay_zs.shape[1] - 1
                                    if window >= 3:
                                        dx = np.mean(np.abs(np.diff(overlay.xs)))
                                        if dx > 0:
                                            overlay_zs = savgol_filter(overlay_zs, window_length=window, polyorder=min(3, window-1), deriv=1, delta=dx, axis=1)
                                else:
                                    overlay_zs = np.gradient(overlay_zs, overlay.xs, axis=1)
                            
                            # Get slice at same index (if within bounds)
                            if overlay_zs.shape[1] > x_idx and overlay.ys is not None:
                                self.ax_ycut.plot(overlay.ys, overlay_zs[:, x_idx], 
                                                  color=overlay.color,
                                                  linewidth=self.settings.line_width, alpha=0.8)
                        except Exception as e:
                            print(f"Overlay vertical linecut error: {e}")
                            
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
                # Apply tick settings to linecut
                self.ax_ycut.tick_params(axis='both', which='major',
                                         length=self.settings.tick_size,
                                         width=self.settings.tick_width,
                                         labelsize=self.settings.tick_font_size)

            # Draw annotation lines on 2D plot
            for x_val, color, linestyle, linewidth in self._vlines:
                self.ax_2d.axvline(x=x_val, color=color, linestyle=linestyle, linewidth=linewidth, alpha=0.8)
            for y_val, color, linestyle, linewidth in self._hlines:
                self.ax_2d.axhline(y=y_val, color=color, linestyle=linestyle, linewidth=linewidth, alpha=0.8)

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

            # Draw delta callout first point marker (while waiting for second click)
            if self._delta_callout_first_point is not None:
                x1, y1, z1 = self._delta_callout_first_point
                self.ax_2d.plot(x1, y1, 'ro', markersize=7, markeredgecolor='darkred', markeredgewidth=2)

            # Draw delta callouts (connecting lines with difference annotation)
            for (x1, y1, z1), (x2, y2, z2) in self._delta_callouts:
                # Draw markers at both points
                self.ax_2d.plot(x1, y1, 'ro', markersize=5)
                self.ax_2d.plot(x2, y2, 'ro', markersize=5)
                
                # Draw connecting line
                self.ax_2d.plot([x1, x2], [y1, y2], 'r-', linewidth=1.5, alpha=0.7)
                
                # Calculate deltas
                dx = x2 - x1
                dy = y2 - y1
                dz = z2 - z1
                
                # Create annotation at midpoint
                mid_x = (x1 + x2) / 2
                mid_y = (y1 + y2) / 2
                dz_str = 'NaN' if (np.isnan(z1) or np.isnan(z2)) else f'{dz:.4g}'
                ann = self.ax_2d.annotate(
                    f'Δx={dx:.4g}\nΔy={dy:.4g}\nΔz={dz_str}',
                    xy=(mid_x, mid_y),
                    xytext=(10, 10), textcoords='offset points',
                    fontsize=9,
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='red', alpha=0.9),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0', color='red')
                )
                ann.draggable()

            # Apply tight_layout with rect to preserve space for colorbar
            if self._show_linecuts:
                self.figure.tight_layout(rect=[0, 0, 1.0, 1.0])
            else:
                self.figure.tight_layout(rect=[0, 0, 0.82, 1.0])
            
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
        self._current_fit_result = None  # Stores current fit result for copy
        self._current_resonator_result = None  # Stores current resonator fit result
        self._stitch_spec = None  # Stores spec for stitch validation

        self._setup_ui()
        self.setAcceptDrops(True)
        
        # Setup keyboard shortcuts
        self._setup_shortcuts()

        if file_path:
            self.load_file(file_path)

    def _setup_shortcuts(self):
        """Setup all keyboard shortcuts."""
        # Escape - cancel zoom/callout modes
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.escape_shortcut.activated.connect(self._on_escape_pressed)
        
        # Ctrl+C - Copy to clipboard
        self.copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self)
        self.copy_shortcut.activated.connect(self._copy_to_clipboard)
        
        # Ctrl+Shift+C - Copy metadata
        self.copy_meta_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        self.copy_meta_shortcut.activated.connect(self._copy_metadata_to_clipboard)
        
        # Ctrl+E - Export/Save figure
        self.export_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        self.export_shortcut.activated.connect(self._save_figure)
        
        # Ctrl+L - Toggle linecuts
        self.linecuts_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        self.linecuts_shortcut.activated.connect(self._toggle_linecuts_shortcut)
        
        # Ctrl+Shift+L - Toggle live update
        self.live_shortcut = QShortcut(QKeySequence("Ctrl+Shift+L"), self)
        self.live_shortcut.activated.connect(self._toggle_live_update_shortcut)
        
        # Ctrl+R - Toggle rotate S21
        self.rotate_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        self.rotate_shortcut.activated.connect(self._toggle_rotate_s21_shortcut)
        
        # Ctrl+O - Add callout
        self.callout_shortcut = QShortcut(QKeySequence("Ctrl+O"), self)
        self.callout_shortcut.activated.connect(self._on_add_callout)
        
        # Ctrl+Shift+O - Add delta callout
        self.delta_callout_shortcut = QShortcut(QKeySequence("Ctrl+Shift+O"), self)
        self.delta_callout_shortcut.activated.connect(self._on_add_delta_callout)
        
        # Ctrl+T - Import style
        self.import_style_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        self.import_style_shortcut.activated.connect(self._on_import_style)
        
        # Ctrl+Shift+E - Export style
        self.export_style_shortcut = QShortcut(QKeySequence("Ctrl+Shift+E"), self)
        self.export_style_shortcut.activated.connect(self._on_export_style)

    def _toggle_linecuts_shortcut(self):
        """Toggle linecuts via keyboard shortcut."""
        # Only works for 2D plots - check if plot widget has linecuts capability
        if self.plot_widget and hasattr(self.plot_widget, '_show_linecuts'):
            self.sidebar.linecuts_checkbox.setChecked(not self.sidebar.linecuts_checkbox.isChecked())

    def _toggle_live_update_shortcut(self):
        """Toggle live update via keyboard shortcut."""
        if hasattr(self.sidebar, 'live_checkbox') and self.sidebar.live_checkbox.isEnabled():
            self.sidebar.live_checkbox.setChecked(not self.sidebar.live_checkbox.isChecked())

    def _toggle_rotate_s21_shortcut(self):
        """Toggle rotate S21 via keyboard shortcut."""
        if hasattr(self.sidebar, 'rotate_s21_checkbox'):
            self.sidebar.rotate_s21_checkbox.setChecked(not self.sidebar.rotate_s21_checkbox.isChecked())

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
        
        # Keyboard shortcuts cheatsheet button
        self.shortcuts_btn = QPushButton("⌨")
        self.shortcuts_btn.setFixedSize(32, 32)
        self.shortcuts_btn.setToolTip("Keyboard Shortcuts")
        self.shortcuts_btn.clicked.connect(self._show_shortcuts_cheatsheet)
        top_bar.addWidget(self.shortcuts_btn)
        
        # Toggle sidebar button (on the right)
        self.toggle_btn = QPushButton("☰")
        self.toggle_btn.setFixedSize(32, 32)
        self.toggle_btn.setToolTip("Toggle Sidebar")
        self.toggle_btn.clicked.connect(self._toggle_sidebar)
        top_bar.addWidget(self.toggle_btn)
        
        content_layout.addLayout(top_bar)

        # Drop zone
        self.drop_label = QLabel("Drag and drop your HDF5 file here\n\n(Shift+Drop to add as overlay)")
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
        self.sidebar.set_callback('start_zoom', self._on_start_zoom)
        self.sidebar.set_callback('reset_zoom', self._on_reset_zoom)
        self.sidebar.set_callback('flip_x', self._on_flip_x)
        self.sidebar.set_callback('flip_y', self._on_flip_y)
        self.sidebar.set_callback('interchange_xy', self._on_interchange_xy)
        self.sidebar.set_callback('add_callout', self._on_add_callout)
        self.sidebar.set_callback('add_delta_callout', self._on_add_delta_callout)
        self.sidebar.set_callback('clear_callouts', self._on_clear_callouts)
        self.sidebar.set_callback('add_vline', self._on_add_vline)
        self.sidebar.set_callback('add_hline', self._on_add_hline)
        self.sidebar.set_callback('clear_lines', self._on_clear_lines)
        self.sidebar.set_callback('rotate_s21_toggled', self._on_rotate_s21_toggled)
        self.sidebar.set_callback('change_figsize', self._on_change_figsize)
        self.sidebar.set_callback('set_limits', self._on_set_limits)
        self.sidebar.set_callback('stitch_files', self._on_stitch_files)
        # Stitch list callbacks
        self.sidebar.set_callback('stitch_visibility_changed', self._on_stitch_visibility_changed)
        self.sidebar.set_callback('remove_stitch_file', self._on_remove_stitch_file)
        self.sidebar.set_callback('clear_stitch', self._on_clear_stitch)
        # Set up drop callback for stitch container
        self.sidebar.stitch_container.set_drop_callback(self._on_stitch_drop)
        # Overlay callbacks
        self.sidebar.set_callback('add_overlay', self._on_add_overlay)
        self.sidebar.set_callback('remove_overlay', self._on_remove_overlay)
        self.sidebar.set_callback('clear_overlays', self._on_clear_overlays)
        self.sidebar.set_callback('overlay_visibility_changed', self._on_overlay_visibility_changed)
        self.sidebar.set_callback('overlay_color_changed', self._on_overlay_color_changed)
        # Set up drop callback for overlay container
        self.sidebar.overlay_container.set_drop_callback(self._on_overlay_drop)
        self.sidebar.set_callback('import_style', self._on_import_style)
        self.sidebar.set_callback('export_style', self._on_export_style)
        # Argand mode callback
        self.sidebar.set_callback('argand_toggled', self._on_argand_toggled)
        # Derivative mode callbacks
        self.sidebar.set_callback('derivative_toggled', self._on_derivative_toggled)
        self.sidebar.set_callback('derivative_smoothing_changed', self._on_derivative_smoothing_changed)
        # Fitting callbacks
        self.sidebar.set_callback('fit_visible', self._on_fit_visible)
        self.sidebar.set_callback('fit_all', self._on_fit_all)
        self.sidebar.set_callback('fit_clear', self._on_fit_clear)
        self.sidebar.set_callback('show_fit_toggled', self._on_show_fit_toggled)
        self.sidebar.set_callback('show_residuals_toggled', self._on_show_residuals_toggled)
        self.sidebar.set_callback('copy_fit_results', self._on_copy_fit_results)
        self.sidebar.set_callback('fit_func_changed', self._on_fit_func_changed)
        main_layout.addWidget(self.sidebar)

    def _on_escape_pressed(self):
        """Handle Escape key - cancel zoom/callout modes."""
        if self.plot_widget:
            if hasattr(self.plot_widget, '_zoom_mode') and self.plot_widget._zoom_mode:
                self.plot_widget.set_zoom_mode(False)
            if hasattr(self.plot_widget, '_callout_mode') and self.plot_widget._callout_mode:
                self.plot_widget.set_callout_mode(False)
            if hasattr(self.plot_widget, '_delta_callout_mode') and self.plot_widget._delta_callout_mode:
                self.plot_widget.set_delta_callout_mode(False)

    def _toggle_sidebar(self):
        self.sidebar_visible = not self.sidebar_visible
        self.sidebar.setVisible(self.sidebar_visible)

    def _show_shortcuts_cheatsheet(self):
        """Show a modal overlay with keyboard shortcuts cheatsheet."""
        # Create overlay that covers the entire window
        self._shortcuts_overlay = QWidget(self)
        self._shortcuts_overlay.setGeometry(self.rect())
        self._shortcuts_overlay.setStyleSheet("background-color: rgba(0, 0, 0, 0.5);")
        
        # Content card - translucent
        self._shortcuts_card = QWidget(self._shortcuts_overlay)
        self._shortcuts_card.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 0.85);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.3);
            }
        """)
        card_layout = QVBoxLayout(self._shortcuts_card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(16)
        
        # Title
        title = QLabel("⌨ Keyboard Shortcuts")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1f2937; background: transparent;")
        title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title)
        
        # Shortcuts list
        shortcuts = [
            ("Ctrl + C", "Copy figure to clipboard"),
            ("Ctrl + Shift + C", "Copy metadata"),
            ("Ctrl + E", "Export/Save figure"),
            ("Ctrl + Shift + E", "Export style"),
            ("Ctrl + T", "Import style"),
            ("Ctrl + L", "Toggle linecuts (2D only)"),
            ("Ctrl + Shift + L", "Toggle live update"),
            ("Ctrl + R", "Toggle rotate S21"),
            ("Ctrl + O", "Add callout"),
            ("Ctrl + Shift + O", "Add delta callout"),
            ("Escape", "Cancel zoom/callout mode"),
        ]
        
        # Create grid layout for shortcuts
        grid = QFormLayout()
        grid.setSpacing(10)
        grid.setHorizontalSpacing(20)
        for key, description in shortcuts:
            key_label = QLabel(f"<code style='background: #e5e7eb; padding: 2px 8px; border-radius: 4px;'>{key}</code>")
            key_label.setStyleSheet("color: #2563eb; font-family: monospace; font-size: 13px; background: transparent;")
            desc_label = QLabel(description)
            desc_label.setStyleSheet("color: #4b5563; font-size: 13px; background: transparent;")
            grid.addRow(key_label, desc_label)
        
        card_layout.addLayout(grid)
        
        # Size and center the card
        self._shortcuts_card.adjustSize()
        self._center_shortcuts_card()
        
        # Close on click outside card
        def on_overlay_click(event):
            card_rect = self._shortcuts_card.geometry()
            if not card_rect.contains(event.pos()):
                self._close_shortcuts_overlay()
        
        self._shortcuts_overlay.mousePressEvent = on_overlay_click
        
        self._shortcuts_overlay.show()
        self._shortcuts_overlay.raise_()
    
    def _center_shortcuts_card(self):
        """Center the shortcuts card in the overlay."""
        if hasattr(self, '_shortcuts_overlay') and self._shortcuts_overlay and hasattr(self, '_shortcuts_card') and self._shortcuts_card:
            self._shortcuts_overlay.setGeometry(self.rect())
            self._shortcuts_card.move(
                (self._shortcuts_overlay.width() - self._shortcuts_card.width()) // 2,
                (self._shortcuts_overlay.height() - self._shortcuts_card.height()) // 2
            )
    
    def _close_shortcuts_overlay(self):
        """Close the shortcuts overlay."""
        if hasattr(self, '_shortcuts_overlay') and self._shortcuts_overlay:
            self._shortcuts_overlay.close()
            self._shortcuts_overlay.deleteLater()
            self._shortcuts_overlay = None
            self._shortcuts_card = None
    
    def resizeEvent(self, event):
        """Handle window resize."""
        super().resizeEvent(event)
        if hasattr(self, '_shortcuts_overlay') and self._shortcuts_overlay:
            self._center_shortcuts_card()

    def _on_start_zoom(self):
        """Enable zoom mode for one zoom action."""
        if self.plot_widget and hasattr(self.plot_widget, 'set_zoom_mode'):
            self.plot_widget.set_zoom_mode(True)

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

    def _on_add_callout(self):
        """Enable callout mode for single callout addition."""
        if self.plot_widget and hasattr(self.plot_widget, 'set_callout_mode'):
            self.plot_widget.set_callout_mode(True)
            # Set callback to exit callout mode after adding one callout
            if hasattr(self.plot_widget, 'set_callout_added_callback'):
                self.plot_widget.set_callout_added_callback(self._on_callout_added)

    def _on_callout_added(self):
        """Called when a callout is added - exits callout mode."""
        if self.plot_widget and hasattr(self.plot_widget, 'set_callout_mode'):
            self.plot_widget.set_callout_mode(False)

    def _on_add_delta_callout(self):
        """Enable delta callout mode for two-point difference annotation."""
        if self.plot_widget and hasattr(self.plot_widget, 'set_delta_callout_mode'):
            self.plot_widget.set_delta_callout_mode(True)
            # Set callback to exit delta callout mode after adding one delta callout
            if hasattr(self.plot_widget, 'set_delta_callout_added_callback'):
                self.plot_widget.set_delta_callout_added_callback(self._on_delta_callout_added)

    def _on_delta_callout_added(self):
        """Called when a delta callout is added - exits delta callout mode."""
        if self.plot_widget and hasattr(self.plot_widget, 'set_delta_callout_mode'):
            self.plot_widget.set_delta_callout_mode(False)

    def _on_clear_callouts(self):
        """Clear all callout annotations."""
        if self.plot_widget and hasattr(self.plot_widget, 'clear_callouts'):
            self.plot_widget.clear_callouts()

    def _on_rotate_s21_toggled(self, enabled: bool):
        """Toggle S21 rotation for data."""
        if self.plot_widget and hasattr(self.plot_widget, 'set_rotate_s21'):
            self.plot_widget.set_rotate_s21(enabled)

    def _on_add_vline(self):
        """Open dialog to add a vertical line."""
        if not self.plot_widget:
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Vertical Line")
        layout = QVBoxLayout(dialog)
        
        form_layout = QFormLayout()
        
        # X value - use QLineEdit for scientific notation support
        value_edit = QLineEdit()
        value_edit.setPlaceholderText("e.g., 5e9 or 0.001")
        form_layout.addRow("X value:", value_edit)
        
        # Color picker
        color_btn = QPushButton()
        color_btn.setFixedSize(60, 24)
        current_color = '#00aa00'  # Default green
        color_btn.setStyleSheet(f"background-color: {current_color};")
        color_btn.color = current_color
        def pick_color():
            color = QColorDialog.getColor()
            if color.isValid():
                color_btn.color = color.name()
                color_btn.setStyleSheet(f"background-color: {color.name()};")
        color_btn.clicked.connect(pick_color)
        form_layout.addRow("Color:", color_btn)
        
        # Line style
        style_combo = QComboBox()
        line_styles = [
            ('Solid', '-'),
            ('Dashed', '--'),
            ('Dotted', ':'),
            ('Dash-dot', '-.'),
        ]
        for name, _ in line_styles:
            style_combo.addItem(name)
        style_combo.setCurrentIndex(1)  # Default to dashed
        form_layout.addRow("Line style:", style_combo)
        
        # Line width
        width_spin = QDoubleSpinBox()
        width_spin.setRange(0.5, 10.0)
        width_spin.setValue(1.5)
        width_spin.setSingleStep(0.5)
        form_layout.addRow("Line width:", width_spin)
        
        layout.addLayout(form_layout)
        
        button_layout = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(apply_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        def on_apply():
            try:
                value = float(value_edit.text())
            except ValueError:
                QMessageBox.warning(dialog, "Invalid Input", "Please enter a valid number (e.g., 5e9 or 0.001)")
                return
            
            if hasattr(self.plot_widget, 'add_vline'):
                _, linestyle = line_styles[style_combo.currentIndex()]
                self.plot_widget.add_vline(
                    value,
                    color=color_btn.color,
                    linestyle=linestyle,
                    linewidth=width_spin.value()
                )
            dialog.accept()
        
        apply_btn.clicked.connect(on_apply)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec_()

    def _on_add_hline(self):
        """Open dialog to add a horizontal line."""
        if not self.plot_widget:
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Horizontal Line")
        layout = QVBoxLayout(dialog)
        
        form_layout = QFormLayout()
        
        # Y value - use QLineEdit for scientific notation support
        value_edit = QLineEdit()
        value_edit.setPlaceholderText("e.g., 5e9 or 0.001")
        form_layout.addRow("Y value:", value_edit)
        
        # Color picker
        color_btn = QPushButton()
        color_btn.setFixedSize(60, 24)
        current_color = '#0000ff'  # Default blue
        color_btn.setStyleSheet(f"background-color: {current_color};")
        color_btn.color = current_color
        def pick_color():
            color = QColorDialog.getColor()
            if color.isValid():
                color_btn.color = color.name()
                color_btn.setStyleSheet(f"background-color: {color.name()};")
        color_btn.clicked.connect(pick_color)
        form_layout.addRow("Color:", color_btn)
        
        # Line style
        style_combo = QComboBox()
        line_styles = [
            ('Solid', '-'),
            ('Dashed', '--'),
            ('Dotted', ':'),
            ('Dash-dot', '-.'),
        ]
        for name, _ in line_styles:
            style_combo.addItem(name)
        style_combo.setCurrentIndex(1)  # Default to dashed
        form_layout.addRow("Line style:", style_combo)
        
        # Line width
        width_spin = QDoubleSpinBox()
        width_spin.setRange(0.5, 10.0)
        width_spin.setValue(1.5)
        width_spin.setSingleStep(0.5)
        form_layout.addRow("Line width:", width_spin)
        
        layout.addLayout(form_layout)
        
        button_layout = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(apply_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        def on_apply():
            try:
                value = float(value_edit.text())
            except ValueError:
                QMessageBox.warning(dialog, "Invalid Input", "Please enter a valid number (e.g., 5e9 or 0.001)")
                return
            
            if hasattr(self.plot_widget, 'add_hline'):
                _, linestyle = line_styles[style_combo.currentIndex()]
                self.plot_widget.add_hline(
                    value,
                    color=color_btn.color,
                    linestyle=linestyle,
                    linewidth=width_spin.value()
                )
            dialog.accept()
        
        apply_btn.clicked.connect(on_apply)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec_()

    def _on_clear_lines(self):
        """Clear all annotation lines."""
        if self.plot_widget and hasattr(self.plot_widget, 'clear_lines'):
            self.plot_widget.clear_lines()

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
            self.settings.fig_width = new_width
            self.settings.fig_height = new_height
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
        
        xmin_edit = QLineEdit()
        xmin_edit.setText(f"{min(current_xlim):.6g}")
        xmin_edit.setPlaceholderText("e.g., 5e9 or 0.001")
        layout.addRow("X Min:", xmin_edit)
        
        xmax_edit = QLineEdit()
        xmax_edit.setText(f"{max(current_xlim):.6g}")
        xmax_edit.setPlaceholderText("e.g., 5e9 or 0.001")
        layout.addRow("X Max:", xmax_edit)
        
        # Y limits section
        layout.addRow(QLabel("<b>Y-Axis Limits</b>"))
        
        ymin_edit = QLineEdit()
        ymin_edit.setText(f"{min(current_ylim):.6g}")
        ymin_edit.setPlaceholderText("e.g., 5e9 or 0.001")
        layout.addRow("Y Min:", ymin_edit)
        
        ymax_edit = QLineEdit()
        ymax_edit.setText(f"{max(current_ylim):.6g}")
        ymax_edit.setPlaceholderText("e.g., 5e9 or 0.001")
        layout.addRow("Y Max:", ymax_edit)
        
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
            try:
                new_xmin = float(xmin_edit.text())
                new_xmax = float(xmax_edit.text())
                new_ymin = float(ymin_edit.text())
                new_ymax = float(ymax_edit.text())
            except ValueError:
                QMessageBox.warning(dialog, "Invalid Input", "Please enter valid numbers (e.g., 5e9 or 0.001)")
                return
            
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

    def _on_add_overlay(self):
        """Open file picker to add an overlay."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Add Overlay", "", "HDF5 Files (*.h5 *.hdf5)")
        
        if file_path:
            self._add_overlay_from_file(file_path)
    
    def _add_overlay_from_file(self, file_path: str):
        """Load a file and add it as an overlay."""
        if not self.plot_widget:
            QMessageBox.warning(self, "No Plot", "Please load a main file first.")
            return
        
        try:
            # Phase 1: Detect experiment type
            spec = None
            with h5py.File(file_path, 'r', libver='latest', swmr=True) as f:
                # Read metadata to detect experiment type (same as stitch/load_file)
                try:
                    metadata = json.loads(f['Metadata'][()].decode('utf-8'))
                except:
                    metadata = {'Expt ID': os.path.basename(file_path)}
                
                expt_id = metadata.get('Expt ID', '')
                
                # Find matching experiment type
                expt_type = None
                for exp_name in EXPERIMENT_REGISTRY:
                    if exp_name in expt_id:
                        expt_type = exp_name
                        break
                
                if expt_type is not None:
                    spec = EXPERIMENT_REGISTRY[expt_type]
            
            # If unknown, open axis selection dialog (file is closed now)
            if spec is None:
                dialog = AxisSelectionDialog(file_path, self)
                if dialog.exec_() != QDialog.Accepted:
                    return  # User cancelled
                spec = dialog.get_spec()
            
            # Determine if 1D or 2D
            is_overlay_2d = spec.y_key is not None
            
            # Check dimensionality match
            main_is_2d = isinstance(self.plot_widget, PlotWidget2D)
            
            if is_overlay_2d != main_is_2d:
                dim_main = "2D" if main_is_2d else "1D"
                dim_overlay = "2D" if is_overlay_2d else "1D"
                QMessageBox.warning(self, "Dimension Mismatch",
                                    f"Cannot overlay {dim_overlay} data on {dim_main} plot.")
                return
            
            # Phase 2: Load data
            with h5py.File(file_path, 'r', libver='latest', swmr=True) as f:
                xs = np.array(f[spec.x_key]) * spec.x_scale
                ys = None
                if is_overlay_2d:
                    ys = np.array(f[spec.y_key]) * spec.y_scale
                
                data = np.array(f[spec.data_key])
            
            # Assign color from palette
            num_overlays = len(self.plot_widget.get_overlays())
            color = OVERLAY_COLORS[num_overlays % len(OVERLAY_COLORS)]
            
            # Create overlay object
            label = os.path.basename(file_path)
            overlay = OverlayData(
                xs=xs,
                data=data,
                ys=ys,
                label=label,
                color=color,
                visible=True,
                source_path=file_path,
                x_label=spec.x_label,
                is_2d=is_overlay_2d
            )
            
            # Add to plot widget
            self.plot_widget.add_overlay(overlay)
            
            # Expand plot limits to include overlay data
            limits_changed = False
            if hasattr(self.plot_widget, '_full_xlim'):
                old_xlim = self.plot_widget._full_xlim
                new_xmin = min(old_xlim[0], float(np.min(xs)))
                new_xmax = max(old_xlim[1], float(np.max(xs)))
                if new_xmin != old_xlim[0] or new_xmax != old_xlim[1]:
                    self.plot_widget._full_xlim = (new_xmin, new_xmax)
                    self.plot_widget._xlim = None  # Reset zoom to show all
                    limits_changed = True
            
            if is_overlay_2d and ys is not None and hasattr(self.plot_widget, '_full_ylim'):
                old_ylim = self.plot_widget._full_ylim
                new_ymin = min(old_ylim[0], float(np.min(ys)))
                new_ymax = max(old_ylim[1], float(np.max(ys)))
                if new_ymin != old_ylim[0] or new_ymax != old_ylim[1]:
                    self.plot_widget._full_ylim = (new_ymin, new_ymax)
                    self.plot_widget._ylim = None  # Reset zoom to show all
                    limits_changed = True
            elif not is_overlay_2d:
                # For 1D plots, reset y-limits so they're recomputed with overlay data
                self.plot_widget._ylim = None
                self.plot_widget._full_ylim = None
                limits_changed = True
            
            # Update plot again if limits changed
            if limits_changed:
                self.plot_widget.update_plot()
            
            # Rebuild sidebar list (sorted alphabetically)
            self.sidebar.update_overlay_indices(self.plot_widget.get_overlays())
                
        except Exception as e:
            QMessageBox.warning(self, "Error Loading Overlay", str(e))
    
    def _on_remove_overlay(self, index: int):
        """Remove an overlay by index."""
        if self.plot_widget:
            self.plot_widget.remove_overlay(index)
            # Rebuild sidebar list with updated indices
            self.sidebar.update_overlay_indices(self.plot_widget.get_overlays())
    
    def _on_clear_overlays(self):
        """Clear all overlays."""
        if self.plot_widget:
            self.plot_widget.clear_overlays()
            self.sidebar.clear_overlay_list()
    
    def _on_overlay_visibility_changed(self, index: int, visible: bool):
        """Handle overlay visibility toggle."""
        if self.plot_widget:
            self.plot_widget.set_overlay_visibility(index, visible)
    
    def _on_overlay_color_changed(self, index: int, color: str):
        """Handle overlay color change."""
        if self.plot_widget:
            self.plot_widget.set_overlay_color(index, color)

    def _on_overlay_drop(self, file_paths: List[str]):
        """Handle files dropped onto overlay container."""
        for file_path in file_paths:
            self._add_overlay_from_file(file_path)

    def _on_stitch_visibility_changed(self, index: int, visible: bool):
        """Handle stitch file visibility toggle."""
        if self.data_source and hasattr(self.data_source, 'set_visibility'):
            self.data_source.set_visibility(index, visible)
            if self.plot_widget:
                self.plot_widget.update_plot()
    
    def _on_remove_stitch_file(self, index: int):
        """Remove a file from the stitch."""
        if self.data_source and hasattr(self.data_source, 'remove_file'):
            # Don't allow removing if only one file left
            if len(self.data_source.file_paths) <= 1:
                QMessageBox.warning(self, "Cannot Remove", 
                                    "Cannot remove the last file. Use 'Clear All' to exit stitch mode.")
                return
            
            self.data_source.remove_file(index)
            # Update sidebar list
            self.sidebar.update_stitch_list(self.data_source.file_paths)
            # Update file info
            self.file_info_label.setText(self.data_source.file_info)
            self.sidebar.set_metadata(self.data_source.metadata_str)
            if self.plot_widget:
                self.plot_widget.update_plot()
    
    def _on_clear_stitch(self):
        """Clear stitch and return to empty state."""
        # Close data source
        if self.data_source:
            self.data_source.close()
            self.data_source = None
        
        # Remove plot widget
        if self.plot_widget:
            self.plot_container.removeWidget(self.plot_widget)
            self.plot_widget.deleteLater()
            self.plot_widget = None
        
        # Clear stitch state
        self._stitch_spec = None
        
        # Clear sidebar
        self.sidebar.clear_stitch_list()
        self.sidebar.set_stitch_mode(False)
        
        # Re-enable live updates and linecuts checkboxes
        self.sidebar.live_checkbox.setEnabled(True)
        self.sidebar.live_checkbox.setToolTip("")
        self.sidebar.linecuts_checkbox.setEnabled(True)
        self.sidebar.linecuts_checkbox.setToolTip("")
        
        # Show drop zone
        self.drop_label.show()
        self.file_info_label.setText("")
    
    def _on_stitch_drop(self, file_paths: List[str]):
        """Handle files dropped onto stitch container."""
        if not self.data_source or not hasattr(self.data_source, 'add_file'):
            return
        
        spec = getattr(self, '_stitch_spec', None)
        if not spec:
            return
        
        for file_path in file_paths:
            try:
                # Validate file
                with h5py.File(file_path, 'r', libver='latest', swmr=True) as f:
                    # Check experiment type matches
                    try:
                        metadata = json.loads(f['Metadata'][()].decode('utf-8'))
                    except:
                        metadata = {'Expt ID': os.path.basename(file_path)}
                    
                    expt_id = metadata.get('Expt ID', '')
                    
                    # Find matching experiment type
                    file_expt_type = None
                    for exp_name in EXPERIMENT_REGISTRY:
                        if exp_name in expt_id:
                            file_expt_type = exp_name
                            break
                    
                    if file_expt_type is None:
                        QMessageBox.warning(self, "Unknown Experiment",
                                            f"Cannot add {os.path.basename(file_path)}:\n"
                                            f"Unknown experiment type (Expt ID: {expt_id})")
                        continue
                    
                    # Check if file already in stitch
                    if file_path in self.data_source.file_paths:
                        continue  # Skip duplicates silently
                    
                    # Load data
                    source = HDF5DataSource(file_path, spec)
                    xs, ys = source.get_axes()
                    data = source.get_data()
                    source.close()
                    
                    # Add to stitch
                    self.data_source.add_file(xs.copy(), ys.copy(), data.copy(), file_path)
                    
            except Exception as e:
                QMessageBox.warning(self, "Error Adding File",
                                    f"Failed to add {os.path.basename(file_path)}:\n{str(e)}")
        
        # Update UI
        self.sidebar.update_stitch_list(self.data_source.file_paths)
        self.file_info_label.setText(self.data_source.file_info)
        self.sidebar.set_metadata(self.data_source.metadata_str)
        if self.plot_widget:
            # Reset plot limits to include all stitched data
            xlim = self.data_source.get_combined_xlim()
            ylim = self.data_source.get_combined_ylim()
            self.plot_widget._full_xlim = xlim
            self.plot_widget._full_ylim = ylim
            self.plot_widget._xlim = None  # Reset zoom to show all
            self.plot_widget._ylim = None
            self.plot_widget.update_plot()

    def _on_export_style(self):
        """Export appearance settings to JSON file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Style", "", "JSON Files (*.json)")
        
        if not file_path:
            return
        
        if not file_path.endswith('.json'):
            file_path += '.json'
        
        style_data = {
            "colormap": self.settings.colormap,
            "normalization": {
                "type": self.settings.norm_type,
                "gamma": self.settings.norm_gamma,
                "vcenter": self.settings.norm_vcenter
            },
            "line": {
                "color": self.settings.line_color,
                "width": self.settings.line_width
            },
            "marker": {
                "style": self.settings.marker_style,
                "size": self.settings.marker_size,
                "color": self.settings.marker_color
            },
            "grid": {
                "enabled": self.settings.grid_enabled,
                "alpha": self.settings.grid_alpha,
                "width": self.settings.grid_width
            },
            "ticks": {
                "size": self.settings.tick_size,
                "width": self.settings.tick_width,
                "font_size": self.settings.tick_font_size,
                "x_count": self.settings.x_tick_count,
                "y_count": self.settings.y_tick_count
            },
            "labels": {
                "size": self.settings.label_size
            },
            "title": {
                "size": self.settings.title_size
            },
            "colorbar_shrink": self.settings.cbar_shrink,
            "y_padding": self.settings.y_padding,
            "figure_size": {
                "width": self.settings.fig_width,
                "height": self.settings.fig_height
            }
        }
        
        try:
            with open(file_path, 'w') as f:
                json.dump(style_data, f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export style:\n{e}")

    def _on_import_style(self):
        """Import appearance settings from JSON file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Style", "", "JSON Files (*.json)")
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'r') as f:
                style_data = json.load(f)
            
            # Apply settings
            if 'colormap' in style_data:
                self.settings.colormap = style_data['colormap']
                idx = self.sidebar.cmap_combo.findText(style_data['colormap'])
                if idx >= 0:
                    self.sidebar.cmap_combo.setCurrentIndex(idx)
            
            if 'normalization' in style_data:
                norm = style_data['normalization']
                self.settings.norm_type = norm.get('type', 'linear')
                self.settings.norm_gamma = norm.get('gamma', 0.5)
                self.settings.norm_vcenter = norm.get('vcenter', None)
                # Update UI
                norm_map = {'linear': 'Linear', 'twoslope': 'Two Slope', 'power': 'Power'}
                norm_text = norm_map.get(self.settings.norm_type, 'Linear')
                idx = self.sidebar.norm_combo.findText(norm_text)
                if idx >= 0:
                    self.sidebar.norm_combo.setCurrentIndex(idx)
                self.sidebar.gamma_spin.setValue(self.settings.norm_gamma)
                if self.settings.norm_vcenter is not None:
                    self.sidebar.vcenter_edit.setText(str(self.settings.norm_vcenter))
                else:
                    self.sidebar.vcenter_edit.setText('')
            
            if 'line' in style_data:
                line = style_data['line']
                self.settings.line_color = line.get('color', '#1f77b4')
                self.settings.line_width = line.get('width', 1.5)
                self.sidebar.linewidth_spin.setValue(self.settings.line_width)
            
            if 'marker' in style_data:
                marker = style_data['marker']
                self.settings.marker_style = marker.get('style', 'None')
                self.settings.marker_size = marker.get('size', 4.0)
                self.settings.marker_color = marker.get('color', '#1f77b4')
                idx = self.sidebar.marker_combo.findText(self.settings.marker_style)
                if idx >= 0:
                    self.sidebar.marker_combo.setCurrentIndex(idx)
                self.sidebar.markersize_spin.setValue(self.settings.marker_size)
            
            if 'grid' in style_data:
                grid = style_data['grid']
                self.settings.grid_enabled = grid.get('enabled', True)
                self.settings.grid_alpha = grid.get('alpha', 0.3)
                self.settings.grid_width = grid.get('width', 0.5)
                self.sidebar.grid_checkbox.setChecked(self.settings.grid_enabled)
                self.sidebar.grid_width_spin.setValue(self.settings.grid_width)
            
            if 'ticks' in style_data:
                ticks = style_data['ticks']
                self.settings.tick_size = ticks.get('size', 6.0)
                self.settings.tick_width = ticks.get('width', 1.0)
                self.settings.tick_font_size = ticks.get('font_size', 10.0)
                self.settings.x_tick_count = ticks.get('x_count', 0)
                self.settings.y_tick_count = ticks.get('y_count', 0)
                self.sidebar.tick_size_spin.setValue(self.settings.tick_size)
                self.sidebar.tick_width_spin.setValue(self.settings.tick_width)
                self.sidebar.tick_font_spin.setValue(self.settings.tick_font_size)
                self.sidebar.x_tick_spin.setValue(self.settings.x_tick_count)
                self.sidebar.y_tick_spin.setValue(self.settings.y_tick_count)
            
            if 'labels' in style_data:
                labels = style_data['labels']
                self.settings.label_size = labels.get('size', 12.0)
                self.sidebar.label_size_spin.setValue(self.settings.label_size)
            
            if 'title' in style_data:
                title = style_data['title']
                self.settings.title_size = title.get('size', 14.0)
                self.sidebar.title_size_spin.setValue(self.settings.title_size)
            
            if 'colorbar_shrink' in style_data:
                self.settings.cbar_shrink = style_data['colorbar_shrink']
                self.sidebar.cbar_shrink_spin.setValue(self.settings.cbar_shrink)
            
            if 'y_padding' in style_data:
                self.settings.y_padding = style_data['y_padding']
            
            if 'figure_size' in style_data:
                fig_size = style_data['figure_size']
                self.settings.fig_width = fig_size.get('width', 10.0)
                self.settings.fig_height = fig_size.get('height', 8.0)
                if self.plot_widget:
                    self.plot_widget.figure.set_size_inches(
                        self.settings.fig_width, self.settings.fig_height)
                    self.plot_widget.figure.tight_layout()
            
            # Apply settings to plot
            if self.plot_widget:
                self.plot_widget.update_settings(self.settings)
                
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to import style:\n{e}")

    # --- Fitting Methods ---
    
    def _on_fit_visible(self):
        """Fit data within visible range."""
        self._perform_fit(visible_only=True)
    
    def _on_fit_all(self):
        """Fit all data."""
        self._perform_fit(visible_only=False)
    
    def _perform_fit(self, visible_only: bool):
        """Perform the fit operation."""
        if not self.plot_widget:
            return
        
        # Don't fit in derivative mode
        if hasattr(self.plot_widget, '_show_derivative') and self.plot_widget._show_derivative:
            self.sidebar.show_fit_error("Fitting disabled in derivative mode")
            return
        
        # Check if in Argand mode
        if self.sidebar._argand_mode:
            # Resonator fitting
            if not HAS_RESONATOR:
                self.sidebar.show_fit_error("resonator package not installed")
                return
            
            bg_model = self.sidebar.get_background_model()
            
            try:
                f_r, Q_i, Q_c, Q_t = self.plot_widget.fit_resonator(bg_model, visible_only)
                
                # Get frequency unit from axis label
                freq_unit = 'Hz'
                if hasattr(self.plot_widget.data_source, 'spec'):
                    x_label = self.plot_widget.data_source.spec.x_label
                    unit = parse_unit(x_label)
                    if unit:
                        freq_unit = unit
                
                self.sidebar.show_resonator_results(f_r, Q_i, Q_c, Q_t, freq_unit)
                # Store for copy
                self._current_resonator_result = {
                    'f_r': f_r, 'Q_i': Q_i, 'Q_c': Q_c, 'Q_t': Q_t,
                    'freq_unit': freq_unit
                }
                self._current_fit_result = None
            except (ImportError, ValueError) as e:
                self.sidebar.show_fit_error(str(e))
                self._current_resonator_result = None
        else:
            # Standard fitting
            model_name = self.sidebar.fit_func_combo.currentText()
            guesses = self.sidebar.get_fit_guesses()
            
            try:
                result = self.plot_widget.fit_data(model_name, guesses, visible_only)
                self.sidebar.show_fit_results(result)
                # Store result for copy
                self._current_fit_result = result
                self._current_resonator_result = None
            except ValueError as e:
                self.sidebar.show_fit_error(str(e))
                self._current_fit_result = None
    
    def _on_fit_clear(self):
        """Clear fit results."""
        if self.plot_widget:
            self.plot_widget.clear_fit()
            if hasattr(self.plot_widget, 'clear_resonator_fit'):
                self.plot_widget.clear_resonator_fit()
        self.sidebar.clear_fit_display()
        self._current_fit_result = None
        self._current_resonator_result = None
    
    def _on_show_fit_toggled(self, show: bool):
        """Toggle fit curve visibility."""
        if self.plot_widget:
            self.plot_widget.set_show_fit(show)
    
    def _on_show_residuals_toggled(self, show: bool):
        """Toggle residuals plot visibility."""
        if self.plot_widget:
            self.plot_widget.set_show_residuals(show)
    
    def _on_fit_func_changed(self, func_name: str):
        """Handle fit function selection change."""
        # Clear current fit when function changes
        self._on_fit_clear()
    
    def _on_argand_toggled(self, enabled: bool):
        """Handle Argand mode toggle."""
        # Update sidebar UI
        self.sidebar.set_argand_mode(enabled)
        
        # Update plot widget
        if self.plot_widget:
            self.plot_widget.set_argand_mode(enabled)
    
    def _on_derivative_toggled(self, enabled: bool):
        """Handle derivative mode toggle."""
        # Update sidebar UI (disable fitting when derivative is on)
        self.sidebar.set_derivative_mode(enabled)
        
        # Update plot widget
        if self.plot_widget:
            self.plot_widget.set_derivative_mode(enabled)
    
    def _on_derivative_smoothing_changed(self, window: int):
        """Handle derivative smoothing window change."""
        if self.plot_widget:
            self.plot_widget.set_derivative_smoothing(window)
    
    def _on_copy_fit_results(self):
        """Copy fit results to clipboard."""
        # Check for resonator results first
        if hasattr(self, '_current_resonator_result') and self._current_resonator_result is not None:
            result = self._current_resonator_result
            lines = [
                "Resonator Fit Results:",
                "",
                f"  f_r = {result['f_r']:.6e} {result['freq_unit']}",
                f"  Q_i = {result['Q_i']:.0f}",
                f"  Q_c = {result['Q_c']:.0f}",
                f"  Q_t = {result['Q_t']:.0f}",
            ]
            text = "\n".join(lines)
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            return
        
        # Standard fit results
        if not hasattr(self, '_current_fit_result') or self._current_fit_result is None:
            return
        
        result = self._current_fit_result
        
        # Build human-readable text
        lines = [f"{result.model_name} Fit Results:", ""]
        
        for name, value, error, unit in zip(
                result.param_names, result.params, result.errors, result.param_units):
            unit_str = f" {unit}" if unit else ""
            lines.append(f"  {name} = {value:.6g} ± {error:.2g}{unit_str}")
        
        # Add extra results
        if result.extra_results:
            lines.append("")
            for name, (value, error, unit) in result.extra_results.items():
                unit_str = f" {unit}" if unit else ""
                lines.append(f"  {name} = {value:.6g} ± {error:.2g}{unit_str}")
        
        lines.append("")
        lines.append(f"  R² = {result.r_squared:.6f}")
        lines.append("")
        lines.append(f"Fit range: {result.x_range[0]:.6g} to {result.x_range[1]:.6g}")
        
        text = "\n".join(lines)
        
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
    
    def _perform_stitch(self, stitch_files: List[str], spec: ExperimentSpec):
        """Combine data from multiple files using multiple pcolormesh calls."""
        try:
            # Close existing data source if any
            if self.data_source and hasattr(self.data_source, 'close'):
                self.data_source.close()
            
            # Clear any existing overlays
            self.sidebar.clear_overlay_list()
            
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
            
            # Store stitch spec for validating drops
            self._stitch_spec = spec
            
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
            
            # Enable stitch mode (disables overlay button)
            self.sidebar.set_stitch_mode(True)
            
            # Show stitch list manager
            self.sidebar.update_stitch_list(file_paths)
            
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
            # Enable/disable fitting based on linecuts state
            # Only if live update is not active
            if not self.sidebar.live_checkbox.isChecked():
                self.sidebar.set_fit_enabled(show)
                if not show:
                    self.sidebar.fit_visible_btn.setToolTip("Enable linecuts to use fitting")
                    self.sidebar.fit_all_btn.setToolTip("Enable linecuts to use fitting")
                    # Clear any existing fit
                    self._on_fit_clear()

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
            # Clear fit display (widget already clears fit internally)
            self.sidebar.clear_fit_display()
            self._current_fit_result = None

    def _on_live_toggle(self, enabled: bool):
        if enabled and self.update_timer:
            self.update_timer.start(self.sidebar.interval_spin.value())
            # Disable fitting during live update
            self.sidebar.set_fit_enabled(False)
            # Clear any existing fit
            self._on_fit_clear()
        elif self.update_timer:
            self.update_timer.stop()
            # Re-enable fitting
            self.sidebar.set_fit_enabled(True)

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
            # Only resize on first load (when no plot exists yet)
            first_load = self.plot_widget is None
            self._setup_plot(file_path, spec, first_load=first_load)

        except Exception as e:
            tb = traceback.format_exc()
            self.drop_label.setText(f"Error loading file:\n{e}\n\n{tb}")
            self.drop_label.show()

    def _setup_plot(self, file_path: str, spec: ExperimentSpec, first_load: bool = False):
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
            if first_load:
                self.resize(1600, 900)
            # Initialize scale range from data
            vmin, vmax = self.plot_widget.get_current_data_range()
            self.sidebar.update_scale_range(vmin, vmax)
        else:
            self.plot_widget = PlotWidget1D(self.data_source, transforms, self.settings)
            if first_load:
                self.resize(1200, 600)

        # Sync settings with actual figure size
        fig_size = self.plot_widget.figure.get_size_inches()
        self.settings.fig_width = fig_size[0]
        self.settings.fig_height = fig_size[1]

        # Set up zoom completed callback to uncheck the zoom button
        self.plot_widget.set_zoom_completed_callback(self._on_zoom_completed)

        self.drop_label.hide()
        self.file_info_label.setText(self.data_source.file_info)
        self.sidebar.set_transforms(transforms)
        self.sidebar.set_metadata(self.data_source.metadata_str)
        self.sidebar.set_2d_mode(is_2d)
        
        # Clear fit display (new file loaded)
        self.sidebar.clear_fit_display()
        self._current_fit_result = None
        self._current_resonator_result = None
        
        # Clear overlays (new file loaded)
        self.sidebar.clear_overlay_list()
        
        # Clear stitch state (new file loaded)
        self.sidebar.clear_stitch_list()
        self.sidebar.set_stitch_mode(False)
        self._stitch_spec = None
        
        # Sync Argand mode with sidebar state
        if self.sidebar._argand_mode:
            self.plot_widget.set_argand_mode(True)
        
        # Sync derivative mode with sidebar state
        if self.sidebar.derivative_checkbox.isChecked():
            self.plot_widget.set_derivative_mode(True)
            self.plot_widget.set_derivative_smoothing(self.sidebar.derivative_smoothing_spin.value())
        
        # Re-enable live updates (may have been disabled by stitched data)
        self.sidebar.live_checkbox.setEnabled(True)
        self.sidebar.live_checkbox.setToolTip("")
        
        # Re-enable linecuts (may have been disabled by stitched data)
        self.sidebar.linecuts_checkbox.setEnabled(True)
        self.sidebar.linecuts_checkbox.setToolTip("")
        
        # Set z-label (colorbar/y-axis data label) from spec if provided
        if spec.data_label:
            self.sidebar.z_label_edit.setText(spec.data_label)
            self.settings.z_label_text = spec.data_label
            # For 1D plots, also set y_label_text (the data axis)
            if not is_2d:
                self.settings.y_label_text = spec.data_label
        else:
            self.sidebar.z_label_edit.setText("")
            self.settings.z_label_text = ""

        self.plot_container.addWidget(self.plot_widget)
        self.plot_widget.update_plot()
        self._start_live_updates()

    def _on_zoom_completed(self):
        """Called when zoom is completed - zoom mode already exited in PlotWidget."""
        pass  # Zoom mode is already disabled by PlotWidget

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        event.setDropAction(Qt.CopyAction)
        event.accept()
        file_path = event.mimeData().urls()[0].toLocalFile()
        
        # Shift+Drop adds as overlay, normal drop replaces
        if event.keyboardModifiers() & Qt.ShiftModifier:
            self._add_overlay_from_file(file_path)
        else:
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