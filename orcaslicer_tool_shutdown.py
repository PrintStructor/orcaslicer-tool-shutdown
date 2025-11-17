#!/usr/bin/env python3
"""
OrcaSlicer Post-Processing Script: Automatic Tool Shutdown After Last Use
Version: 1.0
Author: Chris (Multi-Tool Klipper Community)
GitHub: https://github.com/PrintStructor/orcaslicer-tool-shutdown
License: MIT

DESCRIPTION:
This script analyzes OrcaSlicer-generated G-code and automatically inserts
shutdown commands (M104 S0) for tools after their last usage. This saves
energy and prevents oozing from unused hotends.

FEATURES:
- Automatic tool usage analysis
- Energy-saving shutdown after last use
- Detailed usage report generation
- Compatible with multi-tool and IDEX printers
- Supports both absolute (M82) and relative (M83) extrusion
- Dry-run mode for testing

USAGE:
  python3 orcaslicer_tool_shutdown.py print.gcode
  python3 orcaslicer_tool_shutdown.py --dry-run print.gcode

ORCASLICER INTEGRATION:
  Printer Settings → Machine G-code → Post-processing scripts:
  /usr/bin/python3 "/path/to/orcaslicer_tool_shutdown.py"

COMPATIBILITY:
  - Firmware: Marlin, RepRapFirmware, Klipper
  - Slicer: OrcaSlicer (tested with v2.0+)
  - Python: 3.6+
  - Materials: ALL (PLA, PETG, ABS, TPU, etc.)

For more information, visit:
  https://github.com/PrintStructor/orcaslicer-tool-shutdown
"""

import sys
import re
import os
from collections import defaultdict
from datetime import datetime
import argparse

class ToolShutdownProcessor:
    def __init__(self, gcode_file, dry_run=False):
        self.gcode_file = gcode_file
        self.lines = []
        self.tool_usage = defaultdict(list)
        self.tool_changes = defaultdict(int)
        self.current_tool = 0
        self.total_tools = set()
        self.shutdown_inserted = set()
        self.dry_run = dry_run
        
        # Extrusion tracking
        self.e_mode = 'ABS'  # ABSolute extrusion mode (M82), not ABS material!
        self.e_pos = 0.0
        
        # Regex patterns
        self.re_e = re.compile(r'(?<!;)\bE([-+]?\d*\.?\d+)')
        # Match standalone T commands only (not in M104/M109 temperature commands)
        self.re_t = re.compile(r'^\s*T(\d+)\s*(?:;.*)?$')
        self.re_g92_e = re.compile(r'^\s*G92\s+.*E([-+]?\d*\.?\d+)', re.IGNORECASE)
        
        # Configuration
        self.config = {
            'shutdown_heater': True,     # Add M104 S0 commands
            'shutdown_fan': False,       # Add M106 P{n} S0 commands
            'add_comments': True,        # Add explanatory comments
            'create_backup': True,       # Create .bak files
            'generate_report': True,     # Add detailed report to G-code
        }
        
    def load_gcode(self):
        """Load G-code file"""
        try:
            with open(self.gcode_file, 'r', encoding='utf-8') as f:
                self.lines = f.readlines()
            print(f"✓ Loaded: {len(self.lines)} lines from {self.gcode_file}")
            if self.dry_run:
                print("⚠ DRY-RUN mode: No changes will be saved")
            return True
        except Exception as e:
            print(f"✗ Error loading file: {e}")
            return False
    
    def analyze_tool_usage(self):
        """Analyze tool usage with M82/M83 support"""
        previous_tool = None
        in_start_gcode = True
        first_tool_after_start = True
        
        for line_num, raw_line in enumerate(self.lines):
            line = raw_line.strip()
            
            # Detect end of start G-code
            if ';LAYER:' in line or ';layer' in line.lower():
                in_start_gcode = False
            
            # Track extrusion mode (M82 = absolute, M83 = relative)
            if line.startswith('M82'):
                self.e_mode = 'ABS'
                continue
            elif line.startswith('M83'):
                self.e_mode = 'REL'
                continue
            
            # Track E position resets
            g92_match = self.re_g92_e.match(line)
            if g92_match:
                self.e_pos = float(g92_match.group(1))
                continue
            
            # Track tool changes (only standalone T commands)
            t_match = self.re_t.match(line)
            if t_match:
                new_tool = int(t_match.group(1))
                
                if not in_start_gcode:
                    if first_tool_after_start:
                        # First tool selection after start = initialization, not a change
                        first_tool_after_start = False
                    elif previous_tool is not None and previous_tool != new_tool:
                        # Only count actual changes between different tools
                        self.tool_changes[new_tool] += 1
                
                self.current_tool = new_tool
                previous_tool = new_tool
                self.total_tools.add(new_tool)
                continue
            
            # Track extrusions
            if line and line[0] == 'G' and line[:2] in ('G0', 'G1'):
                e_match = self.re_e.search(line)
                if not e_match:
                    continue
                
                e_value = float(e_match.group(1))
                is_extrusion = False
                
                if self.e_mode == 'ABS':
                    # Absolute mode: check if E increased
                    if e_value > self.e_pos + 1e-6:
                        is_extrusion = True
                    self.e_pos = e_value
                else:
                    # Relative mode: positive E is extrusion
                    if e_value > 1e-6:
                        is_extrusion = True
                
                if is_extrusion:
                    self.tool_usage[self.current_tool].append(line_num)
                    self.total_tools.add(self.current_tool)
        
        print(f"✓ Analysis complete:")
        for tool in sorted(self.total_tools):
            change_count = self.tool_changes[tool]
            if self.tool_usage[tool]:
                print(f"  T{tool}: {change_count} tool changes")
            else:
                print(f"  T{tool}: Not used")
    
    def find_last_standby_command(self, tool_num):
        """
        Find last standby command for a tool by searching backwards.
        
        Searches for: "M104 S100 T{tool_num}"
        S100 = OrcaSlicer's standby temperature (distinct from print temps)
        
        Returns: Index AFTER the standby command, or None
        """
        for idx in range(len(self.lines) - 1, -1, -1):
            line = self.lines[idx].strip()
            
            if f'M104 S100 T{tool_num}' in line:
                print(f"  ✓ Found: Last standby for T{tool_num} at line {idx}")
                return idx + 1  # Insert directly after
        
        # No standby found - tool probably used until end
        return None
    
    def find_safe_insertion_point(self, last_usage_line, tool):
        """Find safe location to insert shutdown command"""
        insert_after_standby = self.find_last_standby_command(tool)
        
        if insert_after_standby:
            return insert_after_standby
        
        # No standby found - tool stays active until end
        print(f"  ℹ T{tool}: No standby found - active until end")
        return None
    
    def generate_shutdown_commands(self, tool_num):
        """Generate shutdown G-code commands"""
        commands = []
        
        if self.config['add_comments']:
            commands.append(f"; ========================================\n")
            commands.append(f"; AUTO-SHUTDOWN: Tool T{tool_num}\n")
            commands.append(f"; Overrides OrcaSlicer standby (100°C → 0°C)\n")
            commands.append(f"; ========================================\n")
        
        if self.config['shutdown_heater']:
            commands.append(f"M104 S0 T{tool_num}          ; Hotend T{tool_num} shutdown\n")
        
        if self.config['shutdown_fan']:
            commands.append(f"M106 P{tool_num} S0          ; Part cooling fan T{tool_num} off\n")
        
        if self.config['add_comments']:
            commands.append(f"; Energy savings: Tool T{tool_num} fully deactivated\n")
            commands.append("\n")
        
        return commands
    
    def insert_shutdown_commands(self):
        """Insert shutdown commands (from end to start to preserve line numbers)"""
        last_usage = {}
        for tool in self.total_tools:
            if self.tool_usage[tool]:
                last_usage[tool] = max(self.tool_usage[tool])
        
        tools_by_last_use = sorted(last_usage.items(), key=lambda x: x[1], reverse=True)
        output_lines = self.lines.copy()
        
        for tool, last_line in tools_by_last_use:
            insert_at = self.find_safe_insertion_point(last_line, tool)
            
            if insert_at is None:
                continue
            
            shutdown_cmds = self.generate_shutdown_commands(tool)
            
            for cmd in reversed(shutdown_cmds):
                output_lines.insert(insert_at, cmd)
            
            self.shutdown_inserted.add(tool)
            print(f"✓ Shutdown for T{tool} inserted at line {insert_at}")
        
        return output_lines
    
    def generate_report(self):
        """Generate detailed usage report for G-code header"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_changes = sum(self.tool_changes.values())
        
        report = []
        report.append("; ╔══════════════════════════════════════════════════════════╗\n")
        report.append("; ║         AUTOMATIC TOOL SHUTDOWN REPORT                     ║\n")
        report.append("; ╚══════════════════════════════════════════════════════════╝\n")
        report.append(f"; Processed on: {timestamp}\n")
        report.append(f"; Script: orcaslicer_tool_shutdown.py v1.0\n")
        report.append(f"; Mode: {'DRY-RUN' if self.dry_run else 'PRODUCTION'}\n")
        report.append(";\n")
        report.append("; Overall Statistics:\n")
        report.append("; ──────────────────────────────────────────────────────────\n")
        report.append(f";   • Tools: {len(self.total_tools)}\n")
        report.append(f";   • Tool Changes: {total_changes}\n")
        report.append(f";   • Auto-Shutdowns: {len(self.shutdown_inserted)}\n")
        
        if total_changes > 0:
            est_time = total_changes * 20
            report.append(f";   • Tool Change Time: ~{est_time//60}m {est_time%60}s\n")
        
        report.append(";\n")
        report.append("; Tool Usage:\n")
        report.append("; ──────────────────────────────────────────────────────────\n")
        
        for tool in sorted(self.total_tools):
            if self.tool_usage[tool]:
                changes = self.tool_changes[tool]
                
                report.append(f";   Tool T{tool}:\n")
                report.append(f";     • Changes: {changes}x\n")
                
                status = "✓ Auto-Shutdown" if tool in self.shutdown_inserted else "○ Active until end"
                report.append(f";     • Status: {status}\n")
                report.append(";\n")
        
        report.append("; ══════════════════════════════════════════════════════════\n")
        report.append("; Script: https://github.com/PrintStructor/orcaslicer-tool-shutdown\n")
        report.append("; For updates and documentation, visit the repository above\n")
        report.append("; ══════════════════════════════════════════════════════════\n")
        report.append("\n")
        
        return report
    
    def insert_report(self, output_lines):
        """Insert report at beginning of G-code"""
        report = self.generate_report()
        
        insert_at = 0
        for idx, line in enumerate(output_lines):
            if ';LAYER:0' in line or 'thumbnail end' in line.lower():
                insert_at = idx if ';LAYER:0' in line else idx + 1
                break
        
        for line in reversed(report):
            output_lines.insert(insert_at, line)
        
        return output_lines
    
    def save_output(self, output_lines):
        """Save modified G-code"""
        if self.dry_run:
            print("\n" + "="*60)
            print("DRY-RUN: Changes that would be made:")
            print("="*60)
            for tool in sorted(self.shutdown_inserted):
                print(f"  • T{tool}: Shutdown would be inserted")
            print(f"\n  {len(output_lines) - len(self.lines)} lines would be added")
            print("="*60)
            return True
        
        if self.config['create_backup']:
            backup = self.gcode_file + '.bak'
            try:
                with open(backup, 'w', encoding='utf-8') as f:
                    f.writelines(self.lines)
                print(f"✓ Backup: {backup}")
            except Exception as e:
                print(f"⚠ Backup error: {e}")
        
        try:
            with open(self.gcode_file, 'w', encoding='utf-8') as f:
                f.writelines(output_lines)
            print(f"✓ Saved: {self.gcode_file}")
            return True
        except Exception as e:
            print(f"✗ Save error: {e}")
            return False
    
    def process(self):
        """Main processing function"""
        print("=" * 60)
        print("OrcaSlicer Tool Shutdown v1.0")
        print("=" * 60)
        
        if not self.load_gcode():
            return False
        
        print("\nAnalyzing tool usage...")
        self.analyze_tool_usage()
        
        if not self.total_tools:
            print("\n⚠ No tools found")
            return False
        
        print("\nInserting shutdown commands...")
        output_lines = self.insert_shutdown_commands()
        
        if self.config['generate_report']:
            print("\nGenerating report...")
            output_lines = self.insert_report(output_lines)
        
        print("\nSaving..." if not self.dry_run else "\nDry-run...")
        success = self.save_output(output_lines)
        
        print("\n" + "=" * 60)
        if success:
            print("✓ SUCCESS" if not self.dry_run else "✓ DRY-RUN OK")
            print(f"  • Original: {len(self.lines)} lines")
            print(f"  • Modified: {len(output_lines)} lines")
            print(f"  • Shutdowns: {len(self.shutdown_inserted)}")
        else:
            print("✗ ERROR")
        print("=" * 60)
        
        return success


def main():
    parser = argparse.ArgumentParser(
        description='OrcaSlicer Tool Shutdown v1.0 - Automatic energy-saving tool shutdown',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 orcaslicer_tool_shutdown.py print.gcode
  python3 orcaslicer_tool_shutdown.py --dry-run print.gcode

OrcaSlicer Integration:
  Printer Settings → Machine G-code → Post-processing scripts:
  /usr/bin/python3 "/path/to/orcaslicer_tool_shutdown.py"

For more information:
  https://github.com/PrintStructor/orcaslicer-tool-shutdown
        """
    )
    
    parser.add_argument('gcode_file', nargs='?', help='G-code file to process')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without saving')
    parser.add_argument('--version', action='version', version='v1.0')
    
    args = parser.parse_args()
    
    if not args.gcode_file:
        parser.print_help()
        sys.exit(1)
    
    if not os.path.exists(args.gcode_file):
        print(f"✗ File not found: {args.gcode_file}")
        sys.exit(1)
    
    processor = ToolShutdownProcessor(args.gcode_file, dry_run=args.dry_run)
    success = processor.process()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
