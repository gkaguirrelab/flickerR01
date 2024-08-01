#from picamera2 import Picamera2, Preview
import time
import cv2
import matplotlib.pyplot as plt
from scipy.signal import correlate, hilbert
from skimage.io import imsave
import numpy as np
import os
import re

CAM_FPS = 206.65

def reconstruct_video(video_frames: np.array, output_path: str):
    # Define the information about the video to use for writing
    #fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # You can use other codecs like 'mp4v', 'MJPG', etc.
    fps = CAM_FPS  # Frames per second of the camera to reconstruct
    height, width = video_frames[0].shape[:2]

    # Initialize VideoWriter object to write frames to
    out = cv2.VideoWriter(output_path, 0, fps, (width, height), isColor=len(video_frames.shape) > 3)

    for i in range(video_frames.shape[0]):
        out.write(video_frames[i])  # Write the frame to the video

    # Release the VideoWriter object
    out.release()
    cv2.destroyAllWindows()

# Read in a video as a series of frames in np.array format
def read_in_video(path_to_video: str) -> np.array:
    return np.load(path_to_video)

# Parse a video in .avi format to a series of frames 
# in np.array format 
def parse_video(path_to_video: str) -> np.array:
    video_capture = cv2.VideoCapture(path_to_video)

    frames = []
    while(True):
        ret, frame = video_capture.read()

        if(not ret): break 

        frames.append(frame)

    video_capture.release()

    frames = np.array(frames, dtype=np.uint8)

    return frames[:,:,:,0] # Grayscale images are read in as color, all channels are equal, so just take the first channel


# Analyze the temporal sensitivity of the camera 
def analyze_temporal_sensitivity(recordings_dir: str, experiment_filename: str, light_levels: tuple) -> tuple:
    # Create matrix where each row i is the ith light level's videos of different freqeuncies                                                                 # Compare the text between _ and NDF in the string to the light level
    light_levels_files = [ [ os.path.join(recordings_dir, file) for file in os.listdir(recordings_dir) 
                            if experiment_filename in file and light_level == file.split('_')[-1][:-7] ] 
                            for light_level in light_levels ] 
    
    # Create a mapping between the light levels and the videos taken at different frequencies at that light level  
    light_level_videos: dict = {light_level : [ parse_video(file) for file in light_level_files ] 
                                for light_level, light_level_files in zip(light_levels, light_levels_files)}

    # Iterate over the light levels
    for ind, (light_level, videos) in enumerate(light_level_videos.items()): 
        # Parse the frequency of each video at this light level
        frequencies: list = [ float(re.search(r'\d+[\.x]\d+hz', file).group()[:-2]) 
                             for file in light_levels_files[ind]]

        # Convert the videos to grayscale if they are not already
        grayscale_videos: np.array = np.array([ videos[i] if(len(videos[i].shape) == 3) 
                                               else np.array(cv2.cvtColor(videos[i], cv2.COLOR_BGR2GRAY)) 
                                               for i in range(len(videos)) ], dtype=np.uint8)

        # Find average intensity of every frame in every video, then concat
        average_frame_intensities: np.array = np.mean(grayscale_videos, axis=(2,3))

        # For each frequency and associated video, plot the source modulation and 
        # fit the observed values to the source modulation
        for frequency, avg_video in zip(frequencies, average_frame_intensities):
            duration: float = avg_video.shape[0] / CAM_FPS # duration of the signal in seconds 
            source_amplitude: float = np.max(avg_video) - np.mean(avg_video) 
            source_phase: int = 0

            # Generate mock source time values and sinusoidal wave 
            t_source: np.array = np.linspace(0, duration, avg_video.shape[0], endpoint=False)
            y_source: np.array = source_amplitude * np.sin(2 * np.pi * frequency * t_source + source_phase)  + np.mean(avg_video)

            # Generate x values in time for the measured points   
            t_measured: np.array = np.linspace(0, duration, avg_video.shape[0], endpoint=False)
            y_measured: np.array = avg_video

            plt.title(f"{light_level} {frequency}hz")
            plt.xlabel('Time (seconds)')
            plt.ylabel('Amplitude')
            plt.plot(t_source, y_source, label='Source Modulation')
            plt.plot(t_measured, y_measured, label='Measured')
            plt.legend()
            plt.show()

        # Reshape this from videos to one vector
    

    return 

    """Express both source and observed values as power spectrum"""
    frequency: int = 2  # frequency of the sinusoid in Hz
    amplitude: int = np.max(average_frame_intensities) - np.mean(average_frame_intensities)   # amplitude of the sinusoid
    phase: int = 0       # phase shift in radians
    sampling_rate:int = 1  # samples per second
    duration: float = video_frames.shape[0] / CAM_FPS  # duration of the signal in seconds

    # Generate mock source time values and sinusoidal wave 
    t_source: np.array = np.linspace(0, duration, video_frames.shape[0], endpoint=False)
    y_source: np.array = amplitude * np.sin(2 * np.pi * frequency * t_source + phase)  + np.mean(average_frame_intensities)

    # Generate x values in time for the measured points    
    t_measured: np.array = np.linspace(0,duration,video_frames.shape[0],endpoint=False)+0.1
    y_measured = average_frame_intensities 

    # Fit measured to source by finding the difference in phase shift 
    # between the two waves
    source_analytic_signal = hilbert(y_source)  # use hilbert transform since it works for imperfect sine waves
    measured_analytic_signal = hilbert(y_measured)

    instantaneous_phase1 = np.unwrap(np.angle(source_analytic_signal))
    instantaneous_phase2 = np.unwrap(np.angle(measured_analytic_signal))
    
    phase_difference = instantaneous_phase2 - instantaneous_phase1
    average_phase_difference = np.mean(phase_difference)

    return (t_source, y_source), (t_measured, y_measured)
    
    """"""

    # Plot the mock source data 
    plt.plot(t_source, y_source, label='Source Modulation')

    # Plot the observed data 
    plt.plot(t_measured, y_measured, label='Avg Intensity')

    plt.title('Camera Temporal Sensitivity (2Hz)')
    plt.xlabel('Time (seconds)')
    plt.ylabel('Amplitude')
    plt.legend()
    plt.show()

"""
def record_video(output_path: str, duration: float):
    # # Begin Recording 
    cam = initialize_camera()
    cam.start("video")
    
    # Initialize array to hold video frames
    frames = []
    
    # Begin timing capture
    start_capture_time = time.time()
    
    # Record frames and append them to frames array  
    while(True):
        frame = cam.capture_array("raw")
        frames.append(frame)
        
        current_time = time.time()
        
        if((current_time - start_capture_time) > duration):
            break
    
    # Record timing of end of capture 
    end_capture_time = time.time()
    
    frames = np.array(frames, dtype=np.uint8)    
    
    #imsave('./test_color.tiff', cv2.cvtColor(frames[0], cv2.COLOR_BAYER_RG2BGR))
    #imsave('./test.tiff', frames[0])
    
    # Calculate the approximate FPS the frames were taken at 
    # (approximate due to time taken for other computation)
    observed_fps = frames.shape[0]/(end_capture_time-start_capture_time)
    print(f'I captured {len(frames)} at {observed_fps} fps')
    
    # Assert that we captured the frames at the target FPS,
    # with margin of error
    assert abs(CAM_FPS - observed_fps) < 10     
    
    assert len(frames.shape) == 3 
    
    # Stop recording and close the picam object 
    cam.close() 
    
    # Build the video from the frames and save it 
    reconstruct_video(frames, output_path)
    
    

def initialize_camera() -> Picamera2:
    # Initialize camera 
    cam: Picamera2 = Picamera2()
    
    # Select the mode to put the sensor in
    # (ie, mode for high fps/low res, more pixel HDR etc)
    sensor_mode: dict = cam.sensor_modes[4]		
    
    # Set the mode
    cam.configure(cam.create_video_configuration(sensor={'output_size':sensor_mode['size'], 'bit_depth':sensor_mode['bit_depth']}, main={'size':sensor_mode['size']}, raw=sensor_mode))
    
    # Ensure the frame rate; This is calculated by
    # FPS = 1,000,000 / FrameDurationLimits 
    # e.g. 206.65 = 1000000/FDL => FDL = 1000000/206.65
    frame_duration_limit = int(np.ceil(1000000/sensor_mode['fps']))
    
    cam.video_configuration.controls['FrameDurationLimits'] = (frame_duration_limit,frame_duration_limit) # *2 for lower,upper bound equal
    
    # Set runtime camera information, such as auto-gain
    # auto exposure, white point balance, etc
    cam.set_controls({'AeEnable':True, 'AwbEnable':False}) # Note, AeEnable changes both AEC and AGC
    
    return cam
"""

def main():    
    # Prepare encoder and output filename
    #output_file: str = './test.avi'    
    
    #record_video(output_file, 10)

    #frames = parse_video(output_file)
    #frames = read_in_video(output_file)
    #reconstruct_video(frames, './my_video.avi')
    analyze_temporal_sensitivity('../recordings/', 'test', ['0x2'])

if(__name__ == '__main__'):
    main()
