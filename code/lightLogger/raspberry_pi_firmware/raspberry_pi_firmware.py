import subprocess
import sys
import time
import argparse
import psutil
import os 
import signal
import traceback
import queue
import setproctitle
import threading
import datetime
import multiprocessing as mp

# Define the time in seconds to wait before 
# raising a timeout error
sensor_initialization_timeout: float = 30

# The time in seconds to allow for sensors to start up
sensor_initialization_time: float = 1.5

# Initialize an int to track how many sensors are ready at a given point
controllers_ready: int = 0 

# Initialize a lock for when we access controllers ready 
ready_sig_lock: threading.Lock = threading.Lock()

"""Define a function to receive signals when the processes are ready"""
def handle_readysig(signum, frame, siginfo=None):
    global controllers_ready
    #print(f'Master process: Received a sensor ready signal!')
    os.write(sys.stdout.fileno(), b"Master process: Received a READY signal\n")

    # Note that we have received a sigready, preventing race conditions from handlers
    with ready_sig_lock:
        controllers_ready += 1

signal.signal(signal.SIGUSR1, handle_readysig)

"""Parse the command line arguments"""
def parse_args() -> tuple:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description='Main control software for managing each component of the device')

    parser.add_argument('config_path', type=str, help='Where to read the processes and arguments from')
    parser.add_argument('n_bursts', type=float, help='The number of bursts to take')
    parser.add_argument('burst_seconds', type=int, help='The amount of seconds for each capture burst')
    parser.add_argument('--shell_output', type=int, choices=[0,1], default=1, help='Enable/Disable output to the terminal from all of the subprocesses')
    parser.add_argument('--starting_chunk_number', type=int, default=0, help='The chunk number to start counting at')
    parser.add_argument('--startup_delay_seconds', type=int, default=0, help='The delay with which to start executing commands in the process.')

    args = parser.parse_args()

    return args.config_path, args.n_bursts, args.burst_seconds, bool(args.shell_output), args.starting_chunk_number, args.startup_delay_seconds

"""Find the PIDS of a process with a given name"""
def find_pid(target_name: tuple) -> list:
    # Initialize a list to store the pids we find 
    # of processes with the target name
    pids: list = []

    # Iterate over the existing processes
    for proc in psutil.process_iter(attrs=['pid', 'name']):
        # Try to access the process information
        try:
            # Get the process's info, including name and pid
            process_name: str = proc.info['name']
            pid: int = proc.info['pid']
            
            # Check if process name matches the target name
            if(process_name == target_name):
                pids.append(pid)
        
        # Skip errored processes
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    return pids

"""Parse the arguments for each subprocess from the main commandline run file"""
def parse_process_args(config_path: str) -> tuple:
    # Define a container for the experiment name + path 
    experiment_name: str = None

    # Generate a dictionary to store program names and thier arguments
    controllers_and_args: dict = {}
    
    # Open the config file 
    with open(config_path, 'r') as f:
        # Iterate over the lines of the file
        for line_num, line in enumerate(f):
             # Skip commented lines 
            if(len(line.strip()) == 0 or line.strip()[0] == '#'): continue

            # First line is going to be the overarching experiment name + path
            if(experiment_name is None):
                experiment_name = line.strip()
                continue

            # First, split the line into space-based tokens
            tokens: list = line.split(' ')

            # Find the program name
            program_name, *_ = [token for token in tokens 
                                if '.py' in token]

            # Find the file extension for this controller 
            file_extension, *_ = [token for token in tokens 
                                 if 'burstX' in token]
            
            # Define the formula for the filename as the savepath plus the 
            # burst placeholder and extension
            filename_formula: str = os.path.join(experiment_name, os.path.basename(experiment_name.strip('/')) + file_extension)

            # Recombine the args into one commandline string
            args: str = " ".join(tokens[0:1] + [program_name, filename_formula] + tokens[3:]).strip()

            # Because we are going to run this process as a subprocess, 
            # we must ensure it has both the flag and a placeholder 
            # for the pid of this parent process
            assert('--is_subprocess 1' in args and '--parent_pid X' in args)

            # Save the arguments for the given program name
            controllers_and_args[program_name] = args

    return controllers_and_args, experiment_name
     

"""Capture a burst of length burst_seconds
   from all of the sensors by recalling 
   the controllers repeatedly (and thus 
   reinitializing all of the sensors over and over)"""
def capture_burst_multi_init(info_file: object, component_controllers: list, CPU_priorities: list, 
                             burst_seconds: float, burst_num: int, shell_output: bool= True) -> None:

    # Determine the current pid of this master process
    master_pid: int = os.getpid()

    # List to keep track of process objects
    processes: list = []

    # Initialize a dict of controller names and if they are initialized 
    # or not
    controllers_ready: list = []

    """Define a function to receive signals when the processes are ready"""
    def handle_readysig(signum, frame, siginfo=None):
        #print(f'Received a sensor ready signal!')
        
        # Determine the pid of the sender
        sender_pid: int = siginfo.si_pid 

        # Record the time the signal was received 
        time_received: float = time.time()
        
        # Append the ready signal and the time received to controllers ready
        controllers_ready.append((True, time_received))
    
    signal.signal(signal.SIGUSR1, handle_readysig)

    # Iterate over the other scripts and start them with their associated arguments
    for (script, args), (core, priority) in zip(component_controllers.items(), CPU_priorities):
        # In the args, we must replace the burstX with the burst number
        # and the parent process ID with the parent processID of this file 
        args: str = args.replace('burstX', f'burst{burst_num}').replace('--parent_pid X', f'--parent_pid {master_pid}')

        # Launch the subprocess
        p = subprocess.Popen(args,
                             stdout=sys.stdout,
                             stderr=sys.stderr,
                             shell=shell_output)

        # Turn p into a psutil process so we can set core 
        # affinity and niceity
        psutil_process: psutil.Process = psutil.Process(p.pid)

        # Set the cpu affinity (which core this will run on)
        # as well as its niceity (priority)
        psutil_process.cpu_affinity([core])

        # Have to include this to define niceity because 
        # using the psutil_process.nice() command requires sudo 
        # privelges, which if I run this script with, says my 
        # libraries don't exist
        # Also do before change and after to ensure both are top priority
        os.system(f"sudo renice -n -20 -p {p.pid}")

        # Append this process to the list of processes 
        # and its pid to the list of pids
        processes.append(p)

    # Wait for all of the sensors to initialize by waiting for their signals
    try:
        start_wait: float = time.time()
        last_read: float = time.time()
        while(len(controllers_ready) != len(component_controllers)):
            # Capture the current time
            current_wait: float = time.time()

            # If we waited N seconds without all sensors being ready, throw an error
            if((current_wait - start_wait) >= sensor_initialization_timeout):
                raise Exception('ERROR: Main controller did not receive enough READY signals by timeout')
            
            # Every 2 seconds, output a messag
            if((current_wait - last_read) >= 2):
                print(f'Waiting for all controllers to initialize: {len(controllers_ready)}/{len(component_controllers)}')
                last_read = current_wait
    
    # Catch and safely handle when the sensors error in their initialization
    except Exception as e:
        # Print the traceback of the function calls that caused the error
        traceback.print_exc()
        print(e)
        print('Main process did not receive sensors ready signal in time. Exiting...')
        sys.exit(1)
    
    # Have all sensors sleep for N seconds 
    time.sleep(sensor_initialization_time)
    
    # Find the current PID of all of the controllers (basically, everything with Python in it)
    pids: list = find_all_pids('python3')

    # Once all sensors are initialized, send a go signal to them
    print(f'Master process {master_pid} sending go signals...')

    # Record the time the go signal was sent by the master process
    time_sent: float = time.time()
    for pid in pids:        
        # Send the signal to begin recording
        print(f'\tSending GO to: {pid}')
        os.kill(pid, signal.SIGUSR1)

    # Denote the start time of this burst as when all sensors 
    # have begun and their priorities have been set
    start_time: float = time.time()
    current_time: float = start_time

    # Record burst seconds long with extra time for initialization 
    while((current_time - start_time) < burst_seconds):
        time.sleep(1)
        current_time = time.time()
    
    # Close the processes after recording 
    for process in processes:
        process.wait()

    # Record the time the processes ready signals 
    # were received as well as the go time sent
    chunk_signal_info: str = ",".join([str(time) for (state, time) in controllers_ready] + [str(time_sent)])
    info_file.write(chunk_signal_info + "\n")

    return

"""Helper function to send STOP signals to the subprocesses"""
def stop_subprocesses(pids: dict, master_pid: int):
    # If we have recorded the desired bursts, 
    # send a stop signal 
    for controller, pid in pids.items():        
        # Send the signal to STOP recording
        print(f'\tMaster process: {master_pid} | Sending STOP to {controller}: {pid}')
        os.kill(pid, signal.SIGUSR2)
    
    # Close the processes after recording 
    for process in processes:
        process.wait()


"""Capture a burst of length burst_seconds
   from all of the sensors by calling the controllers 
   once and communicating with signals when to start/stop
   the next chunk"""
def capture_burst_single_init(info_file: object, component_controllers: list, CPU_priorities: list, 
                              burst_seconds: float, n_bursts: int, shell_output: bool= True,
                              burst_num: int=0) -> None:

    global controllers_ready

    # Determine the current pid of this master process
    master_pid: int = os.getpid()

    # List to keep track of process objects
    processes: list = []

    # Iterate over the other scripts and start them with their associated arguments
    for script, args in component_controllers.items():
        # In the args, we must replace the burstX with the burst number
        # and the parent process ID with the parent processID of this file 
        args: str = args.replace('--parent_pid X', f'--parent_pid {master_pid}')

        # Launch the subprocess
        p = subprocess.Popen(args,
                             stdout=sys.stdout,
                             stderr=sys.stderr,
                             shell=shell_output)

        # Append this process to the list of processes 
        # and its pid to the list of pids
        processes.append(p)

    # Wait for all of the sensors to initialize by waiting for their signals
    try:
        start_wait: float = time.time()
        last_read: float = time.time()
        while(True):
            # Check to see if all ready signals have been received 
            with ready_sig_lock:
                # If we have received all ready signals reset to 0 and break
                if(controllers_ready == len(component_controllers)):
                    controllers_ready = 0
                    break 

            # Capture the current time
            current_wait: float = time.time()

            # If we waited N seconds without all sensors being ready, throw an error
            if((current_wait - start_wait) >= sensor_initialization_timeout):
                raise Exception('ERROR: Master process did not receive enough READY signals by timeout')
            
            # Every 2 seconds, output a messag
            if((current_wait - last_read) >= 2):
                print(f'Waiting for all controllers to initialize: {controllers_ready}/{len(component_controllers)}')
                last_read = current_wait
    
    # Catch and safely handle when the sensors error in their initialization
    except Exception as e:
        # Print the traceback of the function calls that caused the error
        traceback.print_exc()
        print(e)
        print('Master Process: Did not receive sensors ready signal in time. Exiting...')
        sys.exit(1)

    # Retrieve the pids of the actual process (most recent PID, per my working theory, thus last in sorted list)
    # for each of the component controllers 
    pids: dict = {controller: pid 
                 for controller, pid 
                 in zip(component_controllers.keys(), [find_pid(key)[-1] 
                                                      for key in component_controllers.keys()])}

    # Now, we are going to set the priorities and CPU cores 
    for (controller, pid), (core, priority) in zip(pids.items(), CPU_priorities):
        print(f'Affixing {controller} | pid: {pid} to CPU core: {core} with priority: {priority}')

        # Turn p into a psutil process so we can set core 
        # affinity and niceity
        psutil_process: psutil.Process = psutil.Process(p.pid)

        # Set the cpu affinity (which core this will run on)
        # as well as its niceity (priority)
        psutil_process.cpu_affinity([core])

        # Have to include this to define niceity because 
        # using the psutil_process.nice() command requires sudo 
        # privelges, which if I run this script with, says my 
        # libraries don't exist
        # Also do before change and after to ensure both are top priority
        os.system(f"sudo renice -n -20 -p {p.pid}")

    # Have all sensors sleep for N seconds 
    time.sleep(sensor_initialization_time)

    # Capture the start of this chunk
    chunk_start_time: datetime.datetime = datetime.datetime.now()
    
    # Capture the desired amount of bursts
    while(burst_num < n_bursts):
        # Note which burst we are on 
        print(f'Master process: Burst num: {burst_num+1}/{n_bursts}')

        # Once all sensors are initialized, send a go signal to them
        print(f'Master process: {master_pid} sending GO signals...')

        # Capture when the GO signal is sent to the controllers
        #time_sent: float = time.time()
        for controller, pid in pids.items():        
            # Send the signal to begin/continue recording
            print(f'\tMaster Process | Sending GO to: {controller} pid: {pid}')
            os.kill(pid, signal.SIGUSR1)
        
        # Wait until we have received all of the sensors have finished 
        # this chunk before saying go to the next one
        last_read: float = time.time()
        current_wait: float = last_read 
    
        # Wait for the subcontrollers to be ready for the next chunk
        try:
            while(True):
                # Check to see if we have received all signals 
                with ready_sig_lock:
                    # Break if we are ready to go again
                    if(controllers_ready == len(component_controllers)):
                        # Reset to zero to wait for next iteration 
                        controllers_ready = 0
                        break

                # If we waited N seconds without all sensors being ready, throw an error
                if((current_wait - start_wait) >= sensor_initialization_timeout):
                    raise Exception('ERROR: Master process did not receive enough READY signals by timeout')

                # Capture the current time since we begun waiting
                current_wait: float = time.time()
                if((current_wait - last_read) >= 2):
                    print(f'Master Process: Waiting for sensors to be ready... {controllers_ready}/{len(component_controllers)}')
                    last_read = current_wait

        # If we didn't receive enough ready signals, something has gone wrong. Likely, the signal 
        # just disappeared, but could be other reasons. We are going to safely exit, then begin the program again
        except Exception as e:
            # Kill the subprocesses (allow for devices to be freed and so on)
            stop_subprocesses(pids, master_pid)

            # If it's a control C, simply just exit 
            if(isinstance(e, KeyboardInterrupt)):
                sys.exit(0)

            # Otherwise, return the burst number. This 
            # is not going to be equal to the n_bursts and is therefore 
            # an error signal
            return burst_num 

        print(f'Master Process: Sensors ready!')

        # Increment the burst number 
        burst_num += 1

    # Stop the subprocesses
    stop_subprocesses(pids, master_pid)

    # Return the burst num. If this is equal to n bursts, we executed successfully. 
    return burst_num

def main():
    # Set the program title so we can see what it is in TOP 
    setproctitle.setproctitle(os.path.basename(__file__))

    # Define a set of valid process names to use for data collection
    valid_processes: set = set(['MS_com.py', 'Sunglasses_com.py', 
                                'Camera_com.py', 'Pupil_com.py'])

    # Parse the file containing the processes to run and their args
    config_path, n_bursts, burst_seconds, shell_output, starting_chunk_number, startup_delay_seconds = parse_args()

    # Sleep for the desired amount of delay before executing processes
    print(f'DELAYING BEGIN FOR: {startup_delay_seconds}')
    time.sleep(startup_delay_seconds)

    # Parse the controllers and their arguments
    print('Parsing processes and args...')
    component_controllers, experiment_name = parse_process_args(config_path)

    # Assert we have put some controllers into the file 
    assert(len(component_controllers) != 0)

    # Assert we have entered valid process names and args for each 
    assert(all(name in valid_processes for name in component_controllers))

    # Make a supra directory for this experiment 
    # if it does not exist 
    if(not os.path.exists(experiment_name)):
        os.makedirs(experiment_name)

    # Initialize a .csv to track when sensors report ready 
    # and when go signals are sent 
    experiment_info_file: str = open(os.path.join(experiment_name, 'info_file.csv'), 'a')
    experiment_info_file.write('CHUNK_START,CHUNK_END,CRASH\n')

    # Assign max priority to all processes
    cores_and_priorities: list = [(process_num, -20) for process_num in range(len(component_controllers))]

    # Now, add the burst seconds of capture argument for the controllers we are 
    # using
    for process in component_controllers:
        # Retrieve the commandline string to run this controller
        commandline_input: str = component_controllers[process]

        # Now, add in to capture infinitely. This is because we will 
        # manually cancel it from this process, and there is less 
        # computation in the live capture
        commandline_input = f"{commandline_input} {burst_seconds}"

        # Resave this input 
        component_controllers[process] = commandline_input

    # Print out each sub program along with its arguments
    print(f'Executing: {n_bursts} bursts of {burst_seconds} seconds using processes:')
    for name, args in component_controllers.items():
        print(f'\tProgram: {name} | Args: {args}')   

    # Iterate over the number of bursts
    burst_num_reached: int = 0
    while(burst_num_reached < n_bursts):
        # Attempt to carry out the experiment
        burst_num_reached = capture_burst_single_init(experiment_info_file, component_controllers, cores_and_priorities,
                                                      burst_seconds, n_bursts, shell_output=True)

        # Detect if there was a crash in capturing the bursts
        if(burst_num_reached != n_bursts):
            print(f'CRASHED! Restarting after small delay')
        
        # Sleep for a small delay to allow for sensors to close cleanly
        time.sleep(sensor_initialization_delay)
        
    
    # Close the info file
    experiment_info_file.close()


if(__name__ == '__main__'):
    main()