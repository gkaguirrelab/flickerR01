import argparse
import os
import sys
import signal
import threading

"""Import utility functions from the device recorder"""
recorder_lib_path = os.path.join(os.path.dirname(__file__), '..', 'sunglasses')
sys.path.append(os.path.abspath(recorder_lib_path))
from recorder import record_live, record

"""If we receive a SIGTERM, terminate gracefully via keyboard interrupt"""
def handle_sigterm(signum, frame):
    print("Received SIGTERM. Raising KeyboardInterrupt...")
    raise KeyboardInterrupt
signal.signal(signal.SIGTERM, handle_sigterm)

# Create a threading flag to declare when to start recording 
# when run as a subprocess
go_flag: threading.Event = threading.Event()

"""Add a handle to receive a USRSIG from the main process 
   to begin capturing when all sensors have reported ready"""
def handle_gosignal(signum, frame=None):
    print(f'Sunglasses Cam: Received Go signal')
    go_flag.set()

signal.signal(signal.SIGUSR1, handle_gosignal)

"""Parse arguments via the command line"""
def parse_args() -> tuple:
    parser = argparse.ArgumentParser(description='Record videos from the camera via the RP')
    
    parser.add_argument('output_path', type=str, help='Path to the readings file') 
    parser.add_argument('duration', type=float, help='Duration of the recording')
    parser.add_argument('--is_subprocess', default=0, type=int, help='A flag to tell this process if it has been run as a subprocess or not')
    parser.add_argument('--parent_pid', default=0, type=int, help='A flag to tell this process what the pid is of the parent process which called it')
   
    args = parser.parse_args()
    
    return args.output_path, args.duration, bool(args.is_subprocess), args.parent_pid

def main():
    # Parse the command line arguments
    output_path, duration, is_subprocess, parent_pid = parse_args()
        
    # Select whether to use the set-duration video recorder or the live recorder
    recorder: object = record_live if duration == float('INF') else record 

    # Try capturing
    try:
        recorder(duration, output_path, 
                is_subprocess, parent_pid,
                go_flag)
    
    # If the capture was canceled via Ctrl + C
    except KeyboardInterrupt:
        pass 

    # Close capture regardless of interrupt or not
    finally:
        pass






if(__name__ == '__main__'):
    main()