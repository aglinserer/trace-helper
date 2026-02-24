#!/usr/bin/env python3
"""
Bluetooth Kernel Trace Helper
Combines functionality of bt-kernel-trace.sh and log collection commands.
"""

import argparse
import datetime
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


class BTTraceHelper:
    """Helper class to manage Bluetooth kernel tracing and log collection."""
    
    TRACING_PATH = Path("/sys/kernel/tracing")
    DYNAMIC_DEBUG_PATH = Path("/proc/dynamic_debug/control")
    
    # All Bluetooth functions to trace
    TRACE_FUNCTIONS = [
        "start_discovery", "stop_discovery", "start_discovery_sync", "stop_discovery_sync",
    ]
    
    def __init__(self):
        self.processes: List[subprocess.Popen] = []
        self.running = False
        self.creation_string = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d_%H-%M_")
        
    def check_root(self) -> bool:
        """Check if running with root privileges."""
        return os.geteuid() == 0
    
    def write_to_file(self, path: Path, content: str, mode: str = 'w') -> bool:
        """Write content to a file with error handling."""
        try:
            with open(path, mode) as f:
                f.write(content)
            return True
        except PermissionError:
            print(f"Error: Permission denied writing to {path}. Run with sudo.", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Error writing to {path}: {e}", file=sys.stderr)
            return False
    
    def setup_tracing(self) -> bool:
        """Set up kernel tracing for Bluetooth functions."""
        if not self.check_root():
            print("Error: Root privileges required for tracing setup. Run with sudo.", file=sys.stderr)
            return False
        
        print("Setting up Bluetooth kernel tracing...")
        
        # Disable tracing
        if not self.write_to_file(self.TRACING_PATH / "tracing_on", "0"):
            return False
        
        # Clear trace buffer
        if not self.write_to_file(self.TRACING_PATH / "trace", ""):
            return False
        
        # Clear PID filter
        if not self.write_to_file(self.TRACING_PATH / "set_ftrace_pid", ""):
            return False
        
        # Clear function filter
        if not self.write_to_file(self.TRACING_PATH / "set_ftrace_filter", ""):
            return False
        
        # Add all function filters
        print(f"Adding {len(self.TRACE_FUNCTIONS)} function filters...")
        for func in self.TRACE_FUNCTIONS:
            if not self.write_to_file(self.TRACING_PATH / "set_ftrace_filter", f"{func}\n", mode='a'):
                print(f"Warning: Failed to add filter for {func}", file=sys.stderr)
        
        # Enable function-fork option
        if not self.write_to_file(self.TRACING_PATH / "options/function-fork", "1"):
            return False
        
        # Set tracer to function
        if not self.write_to_file(self.TRACING_PATH / "current_tracer", "function"):
            return False
        
        # Enable tracing
        if not self.write_to_file(self.TRACING_PATH / "tracing_on", "1"):
            return False
        
        print("✓ Tracing setup complete")
        return True
    
    def setup_dynamic_debug(self) -> bool:
        """Enable dynamic debug for Bluetooth modules."""
        if not self.check_root():
            print("Error: Root privileges required for dynamic debug setup. Run with sudo.", file=sys.stderr)
            return False
        
        print("Setting up dynamic debug for Bluetooth modules...")
        
        # Enable dynamic debug for bluetooth and btusb modules
        debug_filters = [
            "module bluetooth +p",
            "module btusb +p"
        ]
        
        for filter in debug_filters:
            if not self.write_to_file(self.DYNAMIC_DEBUG_PATH, f"{filter}\n", mode='w'):
                print(f"Warning: Failed to set dynamic debug filter: {filter}", file=sys.stderr)
        
        print("✓ Dynamic debug setup complete")
        return True
    
    def stop_dynamic_debug(self) -> bool:
        """Disable dynamic debug for Bluetooth modules."""
        if not self.check_root():
            print("Error: Root privileges required for dynamic debug cleanup. Run with sudo.", file=sys.stderr)
            return False
        
        print("Cleaning up dynamic debug settings...")
        
        # Disable dynamic debug for bluetooth and btusb modules
        debug_filters = [
            "module bluetooth -p",
            "module btusb -p"
        ]
        
        for filter in debug_filters:
            if not self.write_to_file(self.DYNAMIC_DEBUG_PATH, f"{filter}\n", mode='w'):
                print(f"Warning: Failed to clear dynamic debug filter: {filter}", file=sys.stderr)
        
        print("✓ Dynamic debug cleanup complete")
        return True
    
    def stop_tracing(self) -> bool:
        """Stop kernel tracing."""
        print("Stopping tracing...")
        return self.write_to_file(self.TRACING_PATH / "tracing_on", "0")
    
    def start_log_collection(self, output_dir: Optional[str] = None) -> bool:
        """Start all log collection processes."""
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            _output_dir = Path(output_dir)
        else:
            _output_dir = Path.cwd()
        
        log_configs = [
            {
                'name': 'kernel journal',
                'cmd': ['journalctl', '-o', 'short-monotonic', '-f', '-t', 'kernel'],
                'output': _output_dir / ( self.creation_string + 'journal-kernel.log' ),
                'needs_sudo': False
            },
            {
                'name': 'bluetoothd journal',
                'cmd': ['journalctl', '-o', 'short-monotonic', '-f', '-u', 'bluetooth'],
                'output': _output_dir / ( self.creation_string + 'journal-bluetoothd.log' ),
                'needs_sudo': False
            },
            {
                'name': 'kernel trace pipe',
                'cmd': ['cat', '/sys/kernel/tracing/trace_pipe'],
                'output': _output_dir / ( self.creation_string + 'endless-trace.log' ),
                'needs_sudo': True
            }
        ]
        
        self.running = True
        
        for config in log_configs:
            if config['needs_sudo'] and not self.check_root():
                print(f"Warning: Skipping {config['name']} (requires root)", file=sys.stderr)
                continue
            
            try:
                log_file = open(config['output'], 'a')
                process = subprocess.Popen(
                    config['cmd'],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    bufsize=1
                )
                self.processes.append(process)
                print(f"✓ Started {config['name']} → {config['output']}")
            except Exception as e:
                print(f"Error starting {config['name']}: {e}", file=sys.stderr)
        
        if not self.processes:
            print("Error: No log collection processes started", file=sys.stderr)
            return False
        
        return True
    
    def stop_all(self):
        """Stop all running processes."""
        self.running = False
        print("\nStopping log collection...")
        
        for process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
            except Exception as e:
                print(f"Error stopping process: {e}", file=sys.stderr)
        
        self.processes.clear()
        print("✓ All processes stopped")
    
    def monitor(self):
        """Monitor running processes and wait for completion."""
        if not self.processes:
            print("No processes to monitor")
            return
        
        print("\nMonitoring active (Press Ctrl+C to stop)...")
        print("=" * 60)
        
        try:
            # Wait for any process to finish (shouldn't happen with -f flag)
            while self.running and any(p.poll() is None for p in self.processes):
                for process in self.processes:
                    if process.poll() is not None:
                        print(f"Warning: Process {process.pid} exited unexpectedly")
                        self.processes.remove(process)
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\nReceived interrupt signal")
        finally:
            self.stop_all()


def main():
    parser = argparse.ArgumentParser(
        description="Bluetooth Kernel Trace Helper - Setup tracing and collect logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Setup tracing only (requires sudo)
  sudo %(prog)s --setup-trace
  
  # Collect logs only (non-root gets partial logs)
  %(prog)s --collect-logs
  
  # Setup and collect (recommended, requires sudo)
  sudo %(prog)s --setup-trace --collect-logs
  
  # Full setup with custom output directory
  sudo %(prog)s -s -c -o /tmp/bt-logs
  
  # Stop tracing
  sudo %(prog)s --stop-trace
        """
    )
    
    parser.add_argument('-s', '--setup-trace', action='store_true',
                        help='Setup kernel tracing (requires root)')
    parser.add_argument('-c', '--collect-logs', action='store_true',
                        help='Start log collection')
    parser.add_argument('-o', '--output-dir', type=str,
                        help='Output directory for logs (default: current directory)')
    parser.add_argument('--stop-trace', action='store_true',
                        help='Stop kernel tracing (requires root)')
    
    args = parser.parse_args()

    helper = BTTraceHelper()
    
    # If no arguments, show help
    if not (args.setup_trace or args.collect_logs or args.stop_trace):
        parser.print_help()
        sys.exit(1)
    
    # Stop tracing if requested
    if args.stop_trace:
        rets = [helper.stop_tracing(), helper.stop_dynamic_debug()]
        if all(rets):
            print("✓ Tracing and dynamic debug stopped successfully")
            sys.exit(0)
        else:
            sys.exit(1)
    
    # Setup tracing and dynamic_debug if requested
    if args.setup_trace:
        if not helper.setup_tracing():
            sys.exit(1)
        if not helper.setup_dynamic_debug():
            sys.exit(1)
    
    # Start log collection if requested
    if args.collect_logs:
        if not helper.start_log_collection(args.output_dir):
            sys.exit(1)
        
        # Monitor until interrupted
        helper.monitor()


if __name__ == "__main__":
    main()
