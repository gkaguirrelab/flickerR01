import subprocess
import sys
import time

def main():
    print('Building controllers')
    # List of scripts to run and their associated arguments
    component_controllers = {#'MS_com.py': ['/media/eds/EXTERNAL1/'],
                             #'Sunglasses_com.py': ['/media/eds/EXTERNAL1/sunglasses.csv', 'INF'],
                             'Camera_com.py': ['/media/eds/EXTERNAL1/all_together_now_camera.avi', 'INF', '--save_frames', '1'], 
                             'Pupil_com.py': ['/media/eds/EXTERNAL1/all_together_now_pupil.mp4', 'INF', '--save_frames', '1']}

    # List to keep track of process objects
    processes = []

    print('starting processes')
    
    # Iterate over the other scripts and start them with their associated arguments
    for script, args in component_controllers.items():
        p = subprocess.Popen(['python3', script] + args,
                              stdout=sys.stdout,
                              stderr=sys.stderr)
        processes.append(p)

    # Retrieve the processes by name
    #minispect_process, = processes
    #minispect_process, pupil_process = processes 
    #minispect_process, sunglasses_process, camera_process, pupil_process = processes #camera_process = processes 
    #minispect_process, = processes

    camera_process, pupil_process = processes 

    print(f'Executing')
    try:
        while(True):    
            time.sleep(1)
        #minispect_process.terminate()
        pupil_process.terminate()
       
        
        # Wait for the pupil process to complete for a timed recording
        #pupil_process.wait()
        camera_process.terminate()
        #sunglasses_process.terminate()
       # camera_process.terminate()


        # Then close the minispect process
        #minispect_process.terminate()
        
        #sunglasses_process.wait()
        pupil_process.wait()
        camera_process.wait()
        #minispect_process.wait()
    
    except:
        #minispect_process.terminate()
        camera_process.terminate()
        #sunglasses_process.terminate()
        pupil_process.terminate()


        # Then close the minispect process
        #minispect_process.terminate()
        
        #sunglasses_process.wait()
        camera_process.wait()
        pupil_process.wait()
        #minispect_process.wait()


if(__name__ == '__main__'):
    main()