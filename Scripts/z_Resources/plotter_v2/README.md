# HDF5 Plotter

A PyQt5-based interactive viewer for HDF5 data files, designed for experimental physics data visualization.

## Features

- **Drag & Drop** – Open .h5 files by dragging onto the window
- **Live Updates** – Auto-refresh plots from actively running experiments
- **1D & 2D Plots** – Auto-detects experiment type and displays appropriate plot. If Auto-detect fails, requires manual axes configuration.
- **In-plotter fitting** – Basic fitting functions (Linear, Lorentzian, Double Lorentzian, Exponential decay, Exponentially decaying sinusoidal). For fitting of resonator traces in polar mode, this amazing package [Resonator](https://github.com/danielflanigan/resonator) by [Daniel Flanigan](https://github.com/danielflanigan) is used.
- **Linecuts** – Interactive sliders for horizontal/vertical cuts through 2D data
- **Transforms** – Built-in transforms (Magnitude, Phase, Real, Imag, dB, etc.) + Polar plots of complex data.
- **Color Normalization** – Linear, Power, and Two-Slope normalization
- **Stitch Files** – Combine multiple HDF5 files into a single view
- **Annotations** – Add callouts to plots
- **Export** – Save figures as PNG/PDF/SVG, copy to clipboard, copy experiment metadata
- **Style Import/Export** – Save and load appearance settings as JSON

## Usage (Works best alongside Quddy!)

### Run Directly

For seamlessness - run this in the same environment as Quddy

```bash
python plotter_v2.py [optional: path/to/file.h5]
```

Or simply run the script and drag-and-drop .h5 files onto the window.

### Windows File Association (Optional)

Associate `.h5` files with the plotter so double-clicking opens them directly:

1. **Edit** `register_plotter_h5.bat` and set your paths:
   ```batch
   set PYTHONW=C:\path\to\pythonw.exe
   set PLOTTER=C:\path\to\plotter_v2.py
   set ICON=C:\path\to\plotter_icon.ico
   ```

> **Note**: Uses `pythonw.exe` (not `python.exe`) to avoid console window popup. Again, for seamlessness, use the `pythonw.exe` in the same environment as Quddy!

2. **Run as Administrator**:
   - Right-click `register_plotter_h5.bat` → "Run as administrator"

3. **Test**: Double-click any `.h5` file

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+C` | Copy figure to clipboard |
| `Ctrl+Shift+C` | Copy metadata |
| `Ctrl+E` | Export/Save figure |
| `Ctrl+Shift+E` | Export style (JSON) |
| `Ctrl+T` | Import style (JSON) |
| `Ctrl+L` | Toggle linecuts (2D) |
| `Ctrl+Shift+L` | Toggle live update |
| `Ctrl+R` | Toggle S21 rotation |
| `Ctrl+O` | Add callout |
| `Ctrl+Shift+O` | Add delta callout |
| `Escape` | Cancel zoom/callout mode |


### Style Presets

Export your appearance settings (colormap, normalization, ticks, fonts, figure size) to JSON and reuse across sessions:

```json
{
  "colormap": "viridis",
  "normalization": {"type": "power", "gamma": 0.5},
  "grid": {"enabled": true, "width": 0.5},
  "figure_size": {"width": 10.0, "height": 8.0}
}
```

## Supported Experiment Types

The plotter auto-detects experiment types based on HDF5 structure:

- **CW Experiments** – Single-tone, Two-tone, Power sweeps
- **RFSoC Experiments** – Rabi, T1, T2, Resonator spectroscopy
- **Custom** – Generic 1D/2D datasets

> To add experiment types, update `EXPERIMENT_REGISTRY` dictionary. Use existing experiment types as a reference for syntax.

> To add fit models, add fitting functions and update `FIT_MODELS` dictionary.
