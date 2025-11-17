# OrcaSlicer Tool Shutdown

Automatic hotend shutdown for multi-tool/IDEX prints after each tool's last usage.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![OrcaSlicer](https://img.shields.io/badge/OrcaSlicer-compatible-green.svg)](https://github.com/SoftFever/OrcaSlicer)

## 🎯 What It Does

- **Analyzes** G-code to track tool usage
- **Identifies** the last usage of each tool
- **Inserts** shutdown commands (`M104 S0 T{n}`) automatically
- **Saves** energy by turning off unused hotends
- **Prevents** oozing from inactive tools
- **Generates** detailed usage reports

## 📊 Example

**Before (OrcaSlicer default):**
```
T0: Active layers 1-5   → Standby 100°C until end (15 layers wasted)
T1: Active layers 6-10  → Standby 100°C until end (10 layers wasted)
T2: Active layers 11-20 → Active until end ✓
```

**After (with script):**
```
T0: Active layers 1-5   → Shutdown at layer 5 ✓
T1: Active layers 6-10  → Shutdown at layer 10 ✓
T2: Active layers 11-20 → Active until end ✓
```

**Energy Savings:** ~25 Wh per print (for this example)

## 🚀 Quick Start

### Installation

```bash
# Download script
wget https://raw.githubusercontent.com/PrintStructor/orcaslicer-tool-shutdown/main/orcaslicer_tool_shutdown.py

# Make executable (macOS / Linux)
chmod +x orcaslicer_tool_shutdown.py

# Test
python3 orcaslicer_tool_shutdown.py --version
# Output: v1.0
```

### Usage

#### Manual Mode
```bash
# Analyze and modify G-code
python3 orcaslicer_tool_shutdown.py print.gcode

# Dry-run (preview changes without saving)
python3 orcaslicer_tool_shutdown.py --dry-run print.gcode
```

#### OrcaSlicer Integration

In **Printer Settings → Machine G-code → Post-processing scripts**, add either:

```text
/path/to/orcaslicer_tool_shutdown.py
```

(if the script is executable and uses `#!/usr/bin/env python3`)

or explicitly with Python:

```text
python3 "/path/to/orcaslicer_tool_shutdown.py"
```

Now every sliced file will automatically be post-processed and have shutdown commands and a report injected!

## 📈 Output Example

```text
==============================================================
OrcaSlicer Tool Shutdown v1.0
==============================================================
✓ Loaded: 45000 lines from print.gcode

Analyzing tool usage...
✓ Analysis complete:
  T0: 2 tool changes
  T1: 2 tool changes
  T2: 1 tool change

Inserting shutdown commands...
  ✓ Found: Last temperature command for T0 at line 5050 (S100)
✓ Shutdown for T0 inserted at line 5051
  ✓ Found: Last temperature command for T1 at line 8550 (S100)
✓ Shutdown for T1 inserted at line 8551
  ℹ T2: No temperature command found after last usage – active until end

Generating report...
✓ Backup: print.gcode.bak
✓ Saved: print.gcode

==============================================================
✓ SUCCESS
  • Original: 45000 lines
  • Modified: 45050 lines
  • Shutdowns: 2
==============================================================
```

## 🔧 Features

### ✅ Robust Analysis
- **M82/M83 Support:** Handles both absolute and relative extrusion
- **Accurate Tracking:** Only counts actual extrusions, not retracts
- **Smart Detection:** Distinguishes between tool changes and temperature commands

### ✅ Safe Implementation
- **Automatic Backup:** Creates `.bak` file before modifying (configurable)
- **Dry-Run Mode:** Test changes without saving
- **Detailed Logging:** See exactly what's being modified

### ✅ Smart Insertion
- **Finds Temperature Commands:** Searches backwards for generic `M104 S… T{n}` commands **after** a tool’s last real usage
- **Overwrites Idle Temperature:** Inserts `M104 S0 T{n}` immediately after the last non-zero temperature command for that tool
- **Respects Active Tools:** Tools used until the very end stay active (no shutdown inserted)

### ✅ Comprehensive Reporting
- **Usage Statistics:** Tool changes, tools used, shutdown status
- **Energy Estimates:** Calculates approximate power savings
- **Tool Status:** Shows which tools got auto-shutdown

## 📋 Requirements

- **Python:** 3.6 or higher  
- **OS:** Linux, macOS, Windows  
- **Slicer:** OrcaSlicer (tested with v2.0+)  
- **Temperature commands in OrcaSlicer:**  
  Each filament/tool should have a temperature / idle temperature configured, so that OrcaSlicer emits `M104 S… Tn` commands after tool changes and during cooling.  
  The script hooks into those `M104` commands **after a tool’s last real usage**.  
  If no temperature command is emitted for a given tool/filament, that tool cannot be auto-shutdown.

No external dependencies required!

> ⚠️ Note  
> The script has been tested with OrcaSlicer configurations that use per-filament idle/standby temperatures (e.g. 80–120 °C).  
> In theory, it may also work with setups that do not explicitly configure idle temperatures, as long as OrcaSlicer still emits `M104 S… Tn` temperature commands for the tools – but this scenario is currently **untested**.  
> If you run such a setup and try the script, feedback via GitHub issues is very welcome.

## 🛠️ Configuration

Edit the script's `config` dictionary for customization:

```python
self.config = {
    'shutdown_heater': True,    # Add M104 S0 commands
    'shutdown_fan': False,      # Add M106 P{n} S0 commands (optional)
    'add_comments': True,       # Add explanatory comments
    'create_backup': True,      # Create .bak files
    'generate_report': True,    # Add detailed report to G-code
}
```

> ⚠️ Important  
> The script does **not** read the `idle_temperature` comment directly.  
> It operates purely on actual G-code temperature commands and hooks into the last non-zero `M104 S… Tn` **after** a tool’s final real extrusion.  
> If a filament/tool has no such temperature command emitted by OrcaSlicer, the script will **not modify anything for that tool**.

## 📖 How It Works

### 1. Analysis Phase

```python
# Track tool usage - ONLY standalone T commands!
for each line in gcode:
    if line matches "^\s*T(\d+)\s*(?:;.*)?$":  # Standalone T command
        current_tool = n
        # NOT matched: M104 S100 T0, M109 S270 T1 (temperature commands)
        # MATCHED: T0, T1, T2 (actual tool changes)
    if line is extrusion move:
        tool_usage[current_tool].append(line_number)
```

### 2. Detection Phase

```python
# Find last usage of each tool
for each tool:
    last_usage[tool] = max(tool_usage[tool])
```

### 3. Insertion Phase

```python
# Find last non-zero M104 temperature command for the tool AFTER its last usage
for each tool with last_usage:
    search backwards from end:
        if line matches "M104 S<temp> T{tool}" with temp != 0:
            insert after:
                "; AUTO-SHUTDOWN: Tool T{tool}"
                "M104 S0 T{tool}"  # Shutdown
```

### 4. Report Generation

```python
# Add detailed statistics to G-code header
report = generate_usage_statistics()
insert_at_beginning(gcode, report)
```

## 🔍 Troubleshooting

### "No temperature commands found"
This is normal if:

- a tool is used until the very end of the print, or  
- OrcaSlicer did not emit any `M104 S… Tn` for that tool.

In that case the script will log:  
`"ℹ T{n}: No temperature command found after last usage – active until end"`

### "Script changes nothing"
Possible reasons:

- Single-tool print (nothing to shutdown)  
- All tools are used until the end  
- OrcaSlicer did not emit any `M104 S… Tn` temperature commands for the tools

Use `--dry-run` to see what would change:

```bash
python3 orcaslicer_tool_shutdown.py --dry-run print.gcode
```

### "Backup file already exists"
The script creates `.bak` files. If one exists, it will be overwritten.  
To keep multiple backups, rename them manually.

## 📊 Performance

- **Speed:** ~0.5 seconds for 50,000 line files
- **Memory:** ~10 MB for typical prints
- **File Size:** Adds ~50 lines (report + shutdown commands)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Reporting Issues

When reporting bugs, please include:

1. OrcaSlicer version
2. Sample G-code (or relevant snippet)
3. Expected vs actual behavior
4. Script output/error messages

## 📜 Changelog

### v1.0 (2025-11-17)

- Initial public release
- Automatic tool shutdown after last use
- Energy savings and ooze prevention
- Detailed usage reporting
- M82/M83 extrusion mode support
- Dry-run mode for testing
- Automatic backup creation
- OrcaSlicer post-processing integration

### v1.0.1 (2025-11-17)
- Improved temperature command handling (no longer hard-coded to `M104 S100 Tn`)
- More robust shutdown insertion based on the last non-zero `M104 S… Tn`
- Updated documentation (idle temperature notes, tested setups)

## 📄 License

MIT License – Use freely, modify as needed, share improvements!

## 🙏 Credits

- **Author:** Chris @ PrintStructor (Multi-Tool Klipper Community)
- **Inspired by:** Real-world multi-tool printing challenges
- **Tested on:** multi-tool Klipper setup  
  **Intended for:** IDEX, E3D ToolChanger, Jubilee, Prusa XL and similar multi-tool printers (feedback welcome)

## 🔗 Links

- **Feature Request:** [OrcaSlicer GitHub](https://github.com/SoftFever/OrcaSlicer)
- **Documentation:** This README (wiki may follow later)
- **Support:** Open an issue on GitHub

---

**Happy Printing! 🎉**

*Save energy, reduce oozing, print better!*
