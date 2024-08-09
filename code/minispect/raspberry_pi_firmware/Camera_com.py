from utility.Camera_util import record_video, write_frame, running_frame_mean
import argparse
import multiprocessing as mp
import time

def parseArgs():
    parser = argparse.ArgumentParser(description='Record videos from the camera via the RP')
    parser.add_argument('output_path', type=str, help='Path to output the recorded video to')
    parser.add_argument('duration', type=float, help='Duration of the video')

    args = parser.parse_args()
    
    return args.output_path, args.duration

def main():
    output_path, duration = parseArgs()
    
    capture_queue = mp.Queue()
    write_queue = mp.Queue() 
    gain_control_queue = mp.Queue()
    
    capture_process = mp.Process(target=record_video, args=(output_path, duration, capture_queue, write_queue))															   
    write_process = mp.Process(target=write_frame, args=(write_queue,))
    
  
    #running_mean = mp.Process(target=running_frame_mean, args=(frame_queue, mean_queue, 1))
    
    capture_process.start()
    write_process.start()
    #running_mean.start()
    
    while(capture_process.is_alive() and write_process.is_alive()):
    	time.sleep(1)    
    
    capture_process.terminate()
    capture_process.join()
    	
    
    write_process.terminate()
    write_process.join()
    
    print('Processes finished')



if(__name__ == '__main__'):
    main()