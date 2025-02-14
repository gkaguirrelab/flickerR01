import cv2
import matplotlib.pyplot as plt
import numpy as np
import os
import seaborn as sns
import argparse 
import sys 
import matlab.engine
from natsort import natsorted
from collections.abc import Iterable
import pickle
import scipy.io
from mpl_toolkits.mplot3d import Axes3D
import pandas as pd

"""Import the FPS of the camera"""
agc_lib_path = os.path.join(os.path.dirname(__file__))
from recorder import CAM_FPS, parse_settings_file 

"""Parse command line arguments when script is called via command line"""
def parse_args() -> tuple:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description="Analyze Temporal Sensitivity of the camera")
    
    parser.add_argument('recordings_dir', type=str, help="Path to where the camera recordings are stored")
    parser.add_argument('experiment_filename', type=str, help="Name of the experiment to analyze Temporal Sensitivity for")
    parser.add_argument('ndf_range', nargs='+', type=str, help='The ndf2str values to use when generating the TTF')
    parser.add_argument('--save_path', type=str, default=None, help="The path to where the pickle results of the TTF function will be saved. Optional.")

    args = parser.parse_args()

    return args.recordings_dir, args.experiment_filename, args.ndf_range, args.save_path

"""Close all currently open matplotlib figures"""
def close_all_figures():
    plt.close('all')

"""Given row/col, return the index this coord would be in a flattend img array"""
def pixel_to_index(r: int, c: int, cols: int) -> int:
    return r * cols + c

"""Convert a .raw video to frames"""
def raw_video_to_frames(path_to_video: str, video_shape: tuple) -> np.ndarray:
    # Unpack the shape of the video 
    frames, height, width = video_shape 

    # Initialize container to hold frames 
    frames: list = []

    # Open the raw video file
    with open(path_to_video, 'rb') as f:
        for i in range(frame_count):
            # Read one frame's worth of data
            raw_data: bytes = f.read(frame_size)
            
            # Break when we hit the end of the file
            if(not raw_data):
                break  
            
            # Convert raw bytes to a 2D numpy array of the input image shape
            frame: np.ndarray = np.frombuffer(raw_data, dtype=np.uint8).reshape((height, width))

            # Append this frame to the frame array 
            frames.append(frame)

    # Convert frames to np.ndarray and return 
    frames: np.ndarray = np.ndarray(frames)
    
    return frames

"""Find the pixels activated by a given stimulus video"""
def find_active_pixels(path_to_vid: str):
    # Read in the frame series as a np.array
    vid_arr: np.array = parse_video(path_to_vid)

    # Find the avg pixel intensity of each pixel across the video
    avg_pixel_activity: np.array = np.mean(vid_arr, axis=0)

    # Splice out a section of the image to illustrate activity
    example_subset = avg_pixel_activity[:24, :24]

    # Display the activity of each pixel
    plt.title(f'Avg Pixel Activity: {os.path.basename(path_to_vid)}')
    plt.ylabel('Row')
    plt.xlabel('Col')
    plt.xticks(fontsize=4)  # Change x-tick font size
    plt.yticks(fontsize=4)  # Change y-tick font size
   
    sns.heatmap(example_subset, annot=True, cmap='viridis', cbar=True)

    # Show the heatmap
    plt.show()

"""Generate the temporal support for a givne signal captured at a given FPS"""
def generate_temporal_support(signal: np.ndarray, CAM_FPS: float=CAM_FPS) -> np.ndarray:
    t: np.ndarray = np.arange(0, signal.shape[0]/CAM_FPS, 1/CAM_FPS)

    return t

"""Parse the system information for every frame of a given video from the world cam"""
def parse_system_info_file(path_to_file: str) -> pd.DataFrame:
    system_info_df: pd.DataFrame = pd.read_csv(path_to_file, header=None, names=['CPU Usage', 'CPU Clockspeed'])

    return system_info_df

"""Parse the timing of captured frames (begin/end) for a given video from the world 
   camera into a pandas DataFrame"""
def parse_frame_capture_file(path_to_file: str) -> pd.DataFrame:
    frame_timing_df: pd.DataFrame = pd.read_csv(path_to_file, header=None, names=['Begin', 'End'])

    return frame_timing_df 

"""Generate the flat fielding function for the camera and a matrix of color-classified pixels
   when video input is a string, it's a path to the video file. When it's an np.array,
   its the frames preloaded"""
def generate_fielding_function(video: str | np.ndarray) -> tuple:
    # Initialize frame variale
    frames: np.ndarray = None
    # Parse the video into its frames if given the path
    if(type(video) is str):
        frames: np.array = parse_video(video)
    # Otherwise, the input parameter is already the frame array
    else:
        frames = video

    # Take the mean frame and extract its dimensions
    mean_frame: np.array = np.mean(frames, axis=0)

    # Construct the indices of the various colors 
    r_pixels: np.array = np.array([(r,c)
                                    for r in range(mean_frame.shape[0]) 
                                    for c in range(mean_frame.shape[1]) 
                                    if (r % 2 != 0 and c % 2 != 0)])

    g_pixels: np.array = np.array([(r,c)
                                    for r in range(mean_frame.shape[0])
                                    for c in range(mean_frame.shape[1])
                                    if ((r % 2 == 0 and c % 2 != 0) or (r % 2 != 0 and c % 2 == 0))])
    b_pixels: np.array = np.array([(r,c)
                                    for r in range(mean_frame.shape[0]) 
                                    for c in range(mean_frame.shape[1])
                                    if (r % 2 == 0 and c % 2 == 0)])

    # Initialize a pixel matrix to show where in the image each pixel is
    pixel_matrix: np.array = mean_frame.copy()

    # Assign pixel identities
    pixel_matrix[r_pixels[:,0], r_pixels[:,1]] = 0 # Assign R to 0
    pixel_matrix[g_pixels[:,0], g_pixels[:,1]] = 1 # Assign G to 1
    pixel_matrix[b_pixels[:,0], b_pixels[:,1]] = 2 # Assign B to 2

    # Initialize the fielding function image
    fielding_function: np.array = mean_frame.copy()

    # Normalize the red pixels 
    fielding_function[r_pixels[:,0], r_pixels[:,1]] /= np.max(fielding_function[r_pixels[:,0], r_pixels[:,1]])

    # Normalize the green pixels
    fielding_function[g_pixels[:,0], g_pixels[:,1]] /= np.max(fielding_function[g_pixels[:,0], g_pixels[:,1]])

    # Normalize the blue pixels
    fielding_function[b_pixels[:,0], b_pixels[:,1]] /= np.max(fielding_function[b_pixels[:,0], b_pixels[:,1]])

    # Build the x, y meshgrid for the surface plot of the camera frame
    x: np.array = np.arange(0,mean_frame.shape[1])
    y: np.array = np.arange(0, mean_frame.shape[0])
    x, y = np.meshgrid(x,y)

    # z is the signal of the pixels
    z: np.arary = mean_frame

   # Construct a figure to display the plot
    fig: plt.figure = plt.figure()
    ax: plt.Axes = fig.add_subplot(111, projection='3d')
    ax.set_xlabel('Column')
    ax.set_ylabel('Row')
    ax.set_zlabel('Pixel Intensity')
    ax.set_zlim([np.min(z), np.max(z)])

    # Generate the surface plot
    surface = ax.plot_surface(x, y, z, cmap='plasma')
    fig.colorbar(surface, shrink=0.7)
    
    # Show the plot
    plt.show()

    return fielding_function, pixel_matrix

"""Parse the mean of a given set of pixels from a series of frame buffers. This is 
   used as opposed to parse_mean_video when the frame array is too long to
   create a video for, and when the frames are stored in buffer format. 
   This approach only ever stores the mean of each frame rather than 
   loading them all in and then taking the mean, so saves more memory
   in that regard too"""
def parse_mean_frame_array_buffer(path_to_frame_buffers: str | list, start_buffer: int=0, pixel_indices: np.ndarray=None) -> np.array:
    # Initialize container for the frame buffer file paths 
    frame_buffer_files: list = []
    
    # Check if we need to generate paths or not
    if(type(path_to_frame_buffers) != list):
        # If not already passed in a list, create a list of the frame buffer files and splice from where to start
        frame_buffer_files = [os.path.join(path_to_frame_buffers, frame) 
                             for frame in natsorted(os.listdir(path_to_frame_buffers))][start_buffer:]
    else:
        frame_buffer_files = path_to_frame_buffers

    # Allocate a container to hold the frame means
    mean_array: list = []

    # Iterate over the files
    for buffer_file in frame_buffer_files:
        # Load in the frame 
        frame_buffer: np.ndarray = np.load(buffer_file)

        # Iterate over the frames in the frame buffer 
        for frame_idx in range(frame_buffer.shape[0]):
            # Retrieve the frame
            frame: np.ndarray = frame_buffer[frame_idx]

            # Find the mean of the desird pixels, or entire image if no pixels 
            # specified
            if(pixel_indices is None or len(pixel_indices) == 0): 
                pixel_indices = np.arange(0, frame.shape[0]*frame.shape[1])
            
            mean_frame: np.ndarray = np.mean(frame.flatten()[pixel_indices])

            # Append the mean of the frame to the mean_array 
            mean_array.append(mean_frame)
    
    # Convert the mean array to a numpy array
    mean_array: np.ndarray = np.array(mean_array, dtype=np.uint8)

    # Retunr the mean array
    return mean_array

"""Parse the mean of a given set of pixels from a series of frames. This is 
   used as opposed to parse_mean_video when the frame array is too long to
   create a video for. This approach only ever stores the mean of each frame 
   rather than loading them all in and then taking the mean, so saves more memory
   in that regard too"""
def parse_mean_frame_array(path_to_frames: str, start_frame: int=0, pixel_indices: np.ndarray=None) -> np.array:
    # Create a list of the frame files and splice from where to start
    frame_files: str = [os.path.join(path_to_frames, frame) 
                        for frame in natsorted(os.listdir(path_to_frames))][start_frame:]

    # Allocate a container to hold the frame means
    mean_array: list = []

    # Iterate over the files
    for frame_file in frame_files:
        # Load in the frame 
        frame: np.ndarray = np.load(frame_file)

        # Find the mean of the desird pixels, or entire image if no pixels 
        # specified
        if(pixel_indices is None or len(pixel_indices) == 0): 
            pixel_indices = np.arange(0, frame.shape[0]*frame.shape[1])
        
        mean_frame: np.ndarray = np.mean(frame.flatten()[pixel_indices])

        # Append the mean of the frame to the mean_array 
        mean_array.append(mean_frame)
    
    # Convert the mean array to a numpy array
    mean_array: np.ndarray = np.array(mean_array, dtype=np.uint8)

    # Retunr the mean array
    return mean_array
    
"""Parse video file starting as start_frame as mean of certain pixels of np.array"""
def parse_mean_video(path_to_video: str, start_frame: int=0, pixel_indices: np.array=None) -> np.array:
    # Initialize a video capture object
    video_capture: cv2.videoCapture = cv2.VideoCapture(path_to_video)

    # Create a container to store the frames as they are read in
    frames: list = []

    while(True):
        # Attempt to read a frame from the video file
        ret, frame = video_capture.read()

        # If read in valid, we are 
        # at the end of the video, break
        if(not ret): break 

        # Images read in as color by default => All channels 
        # equal since images were captured raw, so 
        # just take the first value to for every pixel
        frame: np.array = frame[:,:,0]

        # Find the mean of the given pixels per frame 
        if(pixel_indices is None or len(pixel_indices) == 0): 
            pixel_indices = np.arange(0, frame.shape[0]*frame.shape[1])
        mean_frame: np.ndarray = np.mean(frame.flatten()[pixel_indices])

        # Append the mean frame to the frames list
        frames.append(mean_frame)

    # Close the video capture object 
    video_capture.release()
    
    # Convert frames to standardized np.array
    frames = np.array(frames, dtype=np.uint8)

    return frames[start_frame:]

"""Parse video file starting as start_frame of certain pixels of np.array"""
def parse_video(path_to_video: str, start_frame: int=0, pixel_indices: np.array=None) -> np.array:
    # Initialize a video capture object
    video_capture: cv2.VideoCapture = cv2.VideoCapture(path_to_video)

    # Create a container to store the frames as they are read in
    frames = []

    while(True):
        # Attempt to read a frame from the video file
        ret, frame = video_capture.read()

        # If read in valid, we are 
        # at the end of the video, break
        if(not ret): break 

        # Otherwise, append the frame 
        # to the frames containers
        frames.append(frame)

    # Close the video capture object 
    video_capture.release()
    
    # Convert frames to standardized np.array
    frames = np.array(frames, dtype=np.uint8)

    # Select only one channel as pixel intensity value, since 
    # the grayscale images are read in as RGB, all channels are equal, 
    # just choose the first one
    frames = frames[start_frame:,:,:,0]

    # If we simply want the entire images, return them now 
    if(pixel_indices is None): return frames
    
    # Otherwise, splice specific pixel indices
    pixel_rows = pixel_indices // frames.shape[1]
    pixel_cols = pixel_indices % frames.shape[1]

    frames = frames[:, pixel_rows, pixel_cols]

    return frames

"""Convert a given str NDF representation to its float value"""
def str2ndf(ndf_string: str) -> float:
    return float(ndf_string.replace("x", "."))

"""Parse an experiment filename to find its relevant info"""
def parse_recording_filename(filename: str) -> dict:
    fields: list = ["experiment_name", "frequency", "NDF"]
    tokens: list = filename.split("_")

    # Ignore the 'hz' in the frequency token
    tokens[1] = float(tokens[1][:-2])
    # Ignore file extension and the letters NDF in the NDF token 
    tokens[2] = str2ndf(tokens[-1][:-7])

    return {field: token for field, token in zip(fields, tokens)}

"""Read all videos in of a certain light level"""
def read_light_level_videos(recordings_dir: str, experiment_filename: str, 
                            light_level: str, parser: object) -> tuple:
    
    # Construct the path to the metadata directory
    metadata_dir: str = recordings_dir + '_metadata'
    
    # Create container to map frequencies and their videos
    frequencies_and_videos: dict = {}

    print(f"Reading in {experiment_filename} {light_level}NDF videos...")

    # Read in all the files in the recording dir
    for file in os.listdir(recordings_dir):
        if(file == '.DS_Store'): continue
        
        # Build the complete path to the file
        filepath = os.path.join(recordings_dir, file)

        # Parse the experiment information out of the filename
        experiment_info: dict = parse_recording_filename(file)

        # If the video isn't from the target experiment, skip 
        if(experiment_info["experiment_name"] != experiment_filename):
            continue 
        
        # If the video is not from this light_level, skip 
        if(experiment_info["NDF"] != str2ndf(light_level)):
            continue 
        
        # Find the path to the warmup (0hz) file itself 
        tokens: list = os.path.splitext(file)[0].split('_') # Split based on meaningful _ character

        # Default extension for settings files is .pkl. This is to be compatible with legacy videos
        settings_extension: str = '.pkl'

        tokens[1] = '0hz' # set frequency part equal to 0hz to find the warmup video 
        warmup_settings_filename: str = '_'.join(tokens) + '_warmup_settingsHistory' + settings_extension # construct the warmup_settings filename
        warmup_settings_filepath: str = os.path.join(metadata_dir, warmup_settings_filename) # append it to the metadata dir path 
        
        # If the .pkl path didn't exist, change the path to a csv file
        if(not os.path.exists(warmup_settings_filepath)):
            settings_extension = '.csv'
            warmup_settings_filepath = warmup_settings_filepath.replace('.pkl', settings_extension)

        # Find the path to the settings file for the video
        video_settings_filepath: str = os.path.join(metadata_dir, os.path.splitext(file)[0] + '_settingsHistory' + settings_extension)
        
        # Parse the video and pair it with its frequency 
        print(f"Reading {light_level}NDF {experiment_info['frequency']}hz from {file}")
        print(f'Warmup settings from: {os.path.basename(warmup_settings_filepath)}')
        print(f'Video settings from: {os.path.basename(video_settings_filepath)}')

        # Read in the gain + exposure settings of the camera 
        warmup_settings: dict = None 
        video_settings : dict = None 

        # If we are working with a .pkl file, need to read them 
        # in as follows
        if(settings_extension == '.pkl'):
            with open(warmup_settings_filepath, 'rb') as f:
                warmup_settings = pickle.load(f)
            
            with open(video_settings_filepath, 'rb') as f:
                video_settings = pickle.load(f)
        
        # Otherwise, we are working with a .csv file and can 
        # read them in as dataframes
        else:
            # Retrieve the settings histories as dictionaries of lists of gain_history and exposure history
            warmup_settings_dict_of_lists = (parse_settings_file(warmup_settings_filepath)[['gain_history', 'exposure_history']]).to_dict(orient='list')
            video_settings_dict_of_lists = (parse_settings_file(video_settings_filepath)[['gain_history', 'exposure_history']]).to_dict(orient='list')

            # Convert the lists in the dictionaries to np.arrays
            warmup_settings = {key: np.array(val)
                              for key, val 
                              in warmup_settings_dict_of_lists.items()}

            video_settings = {key: np.array(val)
                              for key, val 
                              in video_settings_dict_of_lists.items()}

        # Associate the frequency to this tuple of (video, warmup_settings, settings)
        frequencies_and_videos[experiment_info["frequency"]] = (parser(filepath), warmup_settings, video_settings)

    # Sort the videos by their frequencies
    sorted_by_frequencies: list = sorted(frequencies_and_videos.items())

    # Split the two back into seperate lists
    frequencies: list = []
    videos: list = []
    warmup_settings_list: list = []
    video_settings_list: list = []
    for (frequency, (video, warmup_settings, video_settings)) in sorted_by_frequencies:
        frequencies.append(frequency)
        videos.append(video)
        warmup_settings_list.append(warmup_settings)
        video_settings_list.append(video_settings)

    return np.array(frequencies, dtype=np.float64), videos, warmup_settings_list, video_settings_list

"""This function is used to plot the fit_info tuple returned by fit_source_modulation 
   zoomed into a particular section of the fit"""
def plot_fit(fit_info: tuple, FPS: float, start_second: int=0, end_second: int=None) -> None:
    # Define the constant of the sampling rate of the fit 
    fit_sampling_rate: int = 10000

    # Caluculate the start/end index values of the observed and fit 
    start_ob: int = int(FPS*start_second) 
    start_f: int = int(fit_sampling_rate*start_second) 
    
    end_ob: None | int = None if end_second is None else int(FPS * end_second)
    end_f: None | int = None if end_second is None else int(fit_sampling_rate * end_second)


    # Label the plot
    plt.title('Observed vs Fit Signal')
    plt.ylabel('Contrast')
    plt.xlabel('Time [seconds]')

    # Plot the observed and fit singals
    plt.plot(fit_info[0][start_ob:end_ob], fit_info[1][start_ob:end_ob], label='Observed', color='blue')
    plt.plot(fit_info[2][start_f:end_f], fit_info[3][start_f:end_f], label='Fit', color='orange')

    # Add a legend to the plot
    plt.legend()

    # Show the plot
    plt.show()

"""Interpolate the camera signal via MATLAB in order to 
   help dropped frames issue"""
def interpolate_signal(signal: np.ndarray, signal_t: np.ndarray, 
                       fit: np.ndarray, fit_t: np.ndarray,
                       threshold: float, fps: float,
                       convert_to_contrast: bool=False) -> tuple:
    # Start the MATLAB engine
    eng = matlab.engine.start_matlab()
    eng.addpath('~/Documents/MATLAB/projects/combiExperiments/code/lightLogger/camera')
    eng.addpath('~/Documents/MATLAB/projects/combiExperiments/code/lightLogger/libraries_matlab')

    # Convert signal to contrast (if needed)
    if(convert_to_contrast is True):
        signal_mean = np.mean(signal)
        signal = (signal - signal_mean) / signal_mean

    # Call the MATLAB function to generate the interpolated signal and signal T
    interpolated_signal, interpolated_signal_T = eng.interpolateSignal(matlab.double(signal),
                                                                       matlab.double(signal_t),
                                                                       matlab.double(fit),
                                                                       matlab.double(fit_t),
                                                                       matlab.double(threshold),
                                                                       matlab.double(fps),
                                                                       nargout=2)

    # Convert returned data back to Python datatype 
    interpolated_signal: np.array = np.array(interpolated_signal).flatten()
    interpolated_signal_T: np.array = np.array(interpolated_signal_T).flatten()

    return interpolated_signal, interpolated_signal_T 

"""Similar to fit source modulation, but this time taking into account changes to the MATLAB fourier regression
   function to allow us to compare phases from any point in time. Needs a signal_t generated with an FPS guess."""
def fit_source_modulation_with_t(signal: np.ndarray, signal_t: np.ndarray, frequency: float, fit_sampling_rate: float= CAM_FPS, convert_to_contrast: bool=False) -> tuple:
    # Start the MATLAB engine
    eng = matlab.engine.start_matlab()
    eng.addpath('~/Documents/MATLAB/projects/combiExperiments/code/lightLogger/camera')

    # Ensure MATLAB started properly
    assert eng is not None

    # Convert to contrast units, if desired 
    if(convert_to_contrast is True):
        signal_mean = np.mean(signal)
        signal = (signal - signal_mean) / signal_mean
    
    # Call the MATLAB fourier regression function
    observed_r2, observed_amplitude, observed_phase, observed_fit, observed_model_T, observed_signal_T = eng.fourierRegressionWithT(matlab.double(signal.astype(float)), 
                                                                                                                                    matlab.double(signal_t.astype(float)),
                                                                                                                                    matlab.double(frequency), 
                                                                                                                                    matlab.double(fit_sampling_rate), 
                                                                                                                                    nargout=6)

    # Convert returned data back to Python datatype 
    observed_signal_T: np.array = np.array(observed_signal_T).flatten()
    observed_model_T: np.array = np.array(observed_model_T).flatten()
    observed_fit: np.array = np.array(observed_fit).flatten()


    print(f"R2: {observed_r2}")
    print(f"Amplitude: {observed_amplitude}")


    return observed_amplitude, observed_phase, (observed_signal_T, signal, observed_model_T, observed_fit, observed_r2)

"""Fit the source modulation to the observed and plot the fit"""
def fit_source_modulation(signal: np.array, light_level: str, frequency: float, ax: plt.Axes=None, 
                          fps_guess: float=CAM_FPS, fps_guess_increment: tuple=(0,0.25),
                          convert_to_contrast: bool =False) -> tuple:     
    # Start the MATLAB engine
    eng = matlab.engine.start_matlab()
    eng.addpath('~/Documents/MATLAB/projects/combiExperiments/code/lightLogger/camera')

    # Ensure MATLAB started properly
    assert eng is not None
    
    # Convert signal to contrast (if needed)
    if(convert_to_contrast is True):
        signal_mean = np.mean(signal)
        signal = (signal - signal_mean) / signal_mean

    # Find the actual FPS of the observed data (might be slightly different than our guess)
    observed_fps: matlab.double = eng.findObservedFPS(matlab.double(signal), 
                                                      matlab.double(frequency), 
                                                      matlab.double([fps_guess+fps_guess_increment[0], fps_guess+fps_guess_increment[1]]), 
                                                      nargout=1)
    
    # Fit the data
    observed_r2, observed_amplitude, observed_phase, observed_fit, observed_model_T, observed_signal_T = eng.fourierRegression(matlab.double(signal), 
                                                                                                                               matlab.double(frequency), 
                                                                                                                               observed_fps, 
                                                                                                                               nargout=6)
    print(f"Observed FPS: {observed_fps}")
    print(f"R2: {observed_r2}")
    print(f"Amplitude: {observed_amplitude}")

    # Close the MATLAB engine 
    eng.quit()
    
    # Convert returned data back to Python datatype 
    observed_signal_T: np.array = np.array(observed_signal_T).flatten()
    observed_model_T: np.array = np.array(observed_model_T).flatten()
    observed_fit: np.array = np.array(observed_fit).flatten()

    # If we do not want to plot, simply return
    if(ax is None):
        return observed_amplitude, observed_phase, observed_fps

    # Plot the fit on a given axis 
    ax.plot(observed_signal_T, signal-np.mean(signal), linestyle='-', label="Measured")
    ax.plot(observed_model_T, observed_fit, linestyle='-', label="Fit")
    ax.legend(fontsize=4)
    ax.set_title(f"Measured vs Fit Modulation {light_level}NDF {frequency}hz")
    ax.set_xlabel('Time [seconds]')
    ax.set_ylabel('Contrast')
    ax.set_ylim((-0.5, 0.5))

    return observed_amplitude, observed_phase, observed_fps, (observed_signal_T, signal, observed_model_T, observed_fit, observed_r2)

"""Analyze the temporal sensitivity of a given light level, fit source vs observed for all frequencies"""
def analyze_temporal_sensitivity(recordings_dir: str, experiment_filename: str, light_level: str) -> tuple:
    print(f"Generating TTF : {light_level}NDF")

    # Read in the videos at different frequencies 
    (frequencies, mean_videos, warmup_settings, video_settings) = read_light_level_videos(recordings_dir, experiment_filename, light_level, parse_mean_video)

    # Assert we read in some videos
    assert len(mean_videos) != 0 

    # Assert all of the videos are grayscale 
    assert all(len(vid.shape) < 3 for vid in mean_videos)
    
    # Create axis for all of the frequencies to fit
    total_axes = len(frequencies)+1 # frequencies + 1 for the TTF 
    moldulation_fig, modulation_axes = plt.subplots(total_axes, figsize=(18,16))
    settings_fig, settings_axes = plt.subplots(total_axes-1, figsize=(18,16))
    
    # Ensure the settings are an iterable format
    settings_axes = settings_axes if isinstance(settings_axes, Iterable) else [settings_axes]

    # Find the amplitude and FPS of the videos
    amplitudes, videos_fps, fits = [], [], []
    for ind, (frequency, mean_video, warmup_settings_history, video_settings_history) in enumerate(zip(frequencies, mean_videos, warmup_settings, video_settings)):
        print(f"Fitting Source vs Observed Modulation: {light_level}NDF {frequency}hz")
        moduation_axis, gain_axis = modulation_axes[ind], settings_axes[ind]

        # Fit the source modulation to the observed for this frequency, 
        # and find the amplitude
        observed_amplitude, observed_phase, observed_fps, fit = fit_source_modulation(mean_video, light_level, frequency, moduation_axis)

        # Build the temporal support of the settings values by converting frame num to second
        settings_t: np.array = np.arange(0, mean_video.shape[0]/observed_fps, 1/observed_fps)
        
        # Because we are counting by float, sometimes the shapes are off by a frame, so just 
        # take how many points we actually have 
        num_video_points = len(video_settings_history['gain_history'])
        settings_t = settings_t[:num_video_points]

        # Plot the gain of the camera over the course of the modulation video
        gain_axis.plot(settings_t, video_settings_history['gain_history'], color='red', label='Gain') 
        gain_axis.set_title(f'Camera Settings {light_level}NDF {frequency}hz')
        gain_axis.set_xlabel('Time [seconds]')
        gain_axis.set_ylabel('Gain', color='red')
        
        # Plot the exposure of the camera over the course of the modulation video on the same plot
        # but with a different axis
        exposure_axis = gain_axis.twinx()
        exposure_axis.plot(settings_t, video_settings_history['exposure_history'], color='orange', label='Exposure Time')
        exposure_axis.set_ylabel('Exposure', color='orange')

        # Append this information to the running lists
        amplitudes.append(observed_amplitude)
        videos_fps.append(observed_fps)
        fits.append(fit)


    # Convert amplitudes to standardized np.array
    amplitudes = np.array(amplitudes, dtype=np.float64)
    videos_fps = np.array(videos_fps, dtype=np.float32)

    # Plot the TTF for one light level
    ax = modulation_axes[-1]
    ax.plot(np.log10(frequencies), amplitudes, linestyle='-', marker='o', label='Observed Device')
    ax.set_ylim(bottom=0)
    ax.set_xlabel('Frequency [log]')
    ax.set_ylabel('Amplitude')
    ax.set_title(f'Amplitude by Frequency [log] {light_level}NDF')
    ax.legend()
    
    # Adjust the spacing between the plots
    moldulation_fig.subplots_adjust(hspace=2)
    settings_fig.subplots_adjust(hspace=2)

    # Save the figure
    moldulation_fig.savefig(f'/Users/zacharykelly/Aguirre-Brainard Lab Dropbox/Zachary Kelly/FLIC_admin/Equipment/SpectacleCamera/calibration/graphs/TemporalSensitivity{light_level}NDF.pdf')
    settings_fig.savefig(f'/Users/zacharykelly/Aguirre-Brainard Lab Dropbox/Zachary Kelly/FLIC_admin/Equipment/SpectacleCamera/calibration/graphs/cameraSettings{light_level}NDF.pdf')

    # Close the plot and clear the canvas
    plt.close(moldulation_fig)
    plt.close(settings_fig)

    return frequencies, amplitudes, videos_fps, warmup_settings, fits

"Plot the TTF of the Klein at a single light level"
def generate_klein_ttf(recordings_dir: str, experiment_filename: str):
    # Read in the videos 
    videos: list = [ (file, scipy.io.loadmat(os.path.join(recordings_dir, file))) 
              for file in os.listdir(recordings_dir)
              if experiment_filename == file.split('_')[0]]
    
    # Construct plot to hold video fits as well as 
    # association of frequencies to amplitudes and observed FPS
    fig, axes = plt.subplots(len(videos),1)
    results: dict = {}

    # Iterate over the videos
    for ind, (filename, mat) in enumerate(videos):
        # Find the filename and its extension
        name, extension = os.path.splitext(filename)

        # Reformat the filename to fit the expected input 
        # of parse_recording_filename
        filename: str = name + f'_0NDF{extension}'

        print(f"Analyzing {filename}")

        # Parse the filename 
        file_info: dict = parse_recording_filename(filename)

        # Retrieve relevant information from the filename 
        # and the observed modulation video from the file
        light_level: float = file_info['NDF']
        f: float = file_info['frequency']
        video: np.array = mat['luminance256HzData'][0].flatten().astype(np.float64)

        # Calculate the observed amplitude and FPS
        observed_amplitude, observed_phase, observed_fps = fit_source_modulation(video, light_level, f, ax=axes[ind], fps_guess=256)

        # Save these results
        results[f] = [observed_amplitude, observed_fps]

    # Show the figure of source vs observed modulation fits
    fig.show()

    # Initialize the MATLAB engine
    eng = matlab.engine.start_matlab() 
    eng.addpath('/Users/zacharykelly/Documents/MATLAB/toolboxes/combiLEDToolbox/code/calibration/measureFlickerRolloff/')

    # Sort the results by frequency
    sorted_by_frequency = sorted(results.items())
    frequencies = []
    amplitudes = []

    for (frequency, (amplitude, fps)) in sorted_by_frequency:
        frequencies.append(frequency)
        amplitudes.append(amplitude)

    # Convert frequencies and amplitudes to standardized np.arrays
    # float64 necessary when passing to MATLAB
    frequencies = np.array(frequencies, dtype=np.float64)
    amplitudes = np.array(amplitudes)

    # Find the expected amplitudes from Geoff's previous work 
    expected_amplitudes = np.array(eng.contrastAttenuationByFreq(matlab.double([6,12,25,50]))).flatten()*0.5

    plt.close(fig)

    # Plot the amplitude that we measured from the videos
    plt.plot(np.log10(frequencies), amplitudes, marker='.', label='Measured')
    
    # Plot the amplitude that we observed from the klein software 
    plt.plot(np.log10([6,12,25,50,100]),[0.5,0.4965,0.4715,0.4175,0.31], marker='x', color='red', label='Observed')
    
    # Plot the amplitudes expected from Geoff's previous work
    plt.plot(np.log10([6,12,25,50]), expected_amplitudes, marker='o', color='green', label='Expected')
    
    plt.xlabel('Frequency [log]')
    plt.ylabel('Amplitude')
    plt.title('Klein TTF Plot (0 NDF)')
    plt.legend()
    plt.show()

"""Generate a TTF plot for several light levels, return values used to generate the plot"""
def generate_TTF(recordings_dir: str, experiment_filename: str, light_levels: tuple, save_path: str=None, hold_figures_on: bool=False) -> dict: 
    # Start the MATLAB engine
    eng = matlab.engine.start_matlab()
    eng.addpath('~/Documents/MATLAB/toolboxes/combiLEDToolbox/code/calibration/measureFlickerRolloff/')
    eng.addpath('~/Documents/MATLAB/projects/combiExperiments/code/lightLogger/camera')

    # Create a mapping between light levels and their (frequencies, amplitudes)
    light_level_ts_map: dict = {str2ndf(light_level) : analyze_temporal_sensitivity(recordings_dir, experiment_filename, light_level)
                                                       for light_level in light_levels}

    # Create a mapping of the frequencies and their verified amplitudes 
    # via the Klein chromasurf software.
    klein_frequencies_and_amplitudes: dict = {freq : amp 
                                            for freq, amp
                                            in zip([6,12,25,50,100], np.array([0.5,0.4965,0.4715,0.4175,0.31]) / 0.5)}


    # Create a TTF plot to measure data
    ttf_fig, (ttf_ax0, ttf_ax1, ttf_ax2) = plt.subplots(3, 1, figsize=(14,12))

    # Create a plot to measure warmup times per light-level
    warmup_fig, warmup_axes = plt.subplots(len(light_level_ts_map), 1, figsize=(10,8))

    # Ensure warmup_axes is an iterable object
    warmup_axes = warmup_axes if isinstance(warmup_axes, Iterable) else [warmup_axes]
    
    # Initialize a results container to store values used to generate the plot
    results: dict = {'fixed_FPS': CAM_FPS} 

    # Plot the light levels' amplitudes by frequencies
    for ind, (light_level, (frequencies, amplitudes, videos_fps, warmup_settings, fits)) in enumerate(light_level_ts_map.items()):  
        # Find the corrected amplitude for these frequencies
        corrected_amplitudes: np.array = np.array([amp if freq not in klein_frequencies_and_amplitudes 
                                                    else amp / klein_frequencies_and_amplitudes[freq] 
                                                    for freq, amp 
                                                    in zip(frequencies, amplitudes)])

        # Plot the amplitude and FPS
        ttf_ax0.plot(np.log10(frequencies), amplitudes, linestyle='-', marker='o', label=f"{light_level}NDF")
        ttf_ax1.plot(np.log10(frequencies), corrected_amplitudes, linestyle='-', marker='o', label=f"{light_level}NDF")
        ttf_ax2.plot(np.log10(frequencies), videos_fps, linestyle='-', marker='o', label=f"{light_level}NDF FPS")
        
        # Retrieve info to plot the camera settings over the warmup period
        gain_axis = warmup_axes[ind]
        gain_history: np.array = warmup_settings[0]['gain_history']
        exposure_history: np.array = warmup_settings[0]['exposure_history']
        warmup_t: np.array = np.arange(0, len(gain_history)/CAM_FPS, 1/CAM_FPS)

        # Plot the gain of the camera over the course of the warmup video
        gain_axis.plot(warmup_t, gain_history, color='red', label='Gain') 
        gain_axis.set_title(f'Camera Settings {light_level}NDF 0hz')
        gain_axis.set_xlabel('Time [seconds]')
        gain_axis.set_ylabel('Gain', color='red')
        gain_axis.set_ylim([0.5,11])
        
        # Plot the exposure of the camera over the course of the warmup video on the same plot
        # but with a different axis
        exposure_axis = gain_axis.twinx()
        exposure_axis.plot(warmup_t, exposure_history, color='orange', label='Exposure Time')
        exposure_axis.set_ylabel('Exposure', color='orange')
        exposure_axis.set_ylim([35,5000])


                # Record these results in the results dictionary
        results['ND'+str(light_level).replace('.', 'x')] = {'amplitudes': amplitudes,
                                                            'corrected_amplitudes': corrected_amplitudes,
                                                            'videos_fps': videos_fps,
                                                            'warmup_t': warmup_t,
                                                            'warmup_settings': warmup_settings,
                                                            'fits': {'F'+str(freq).replace('.', 'x'): fit 
                                                            for freq, fit in zip(frequencies, fits)}}

    # Retrieve the ideal device curve from MATLAB
    sourceFreqsHz = matlab.double(np.logspace(0,2))
    dTsignal = 1/CAM_FPS
    ideal_device_curve = (np.array(eng.idealDiscreteSampleFilter(sourceFreqsHz, dTsignal)).flatten() * 0.5).astype(np.float64)
    
    # Record the ideal_device_curve in the results dictionary
    results['ideal_device'] = [np.array(sourceFreqsHz, dtype=np.float64), ideal_device_curve]

    # Add the ideal device to the plot
    ttf_ax0.plot(np.log10(sourceFreqsHz).flatten(), ideal_device_curve, linestyle='-', marker='o', label=f"Ideal Device")
    ttf_ax1.plot(np.log10(sourceFreqsHz).flatten(), ideal_device_curve, linestyle='-', marker='o', label=f"Ideal Device")

    # Standardize the y axis scale
    ttf_ax0.set_ylim([0, 0.65])
    ttf_ax1.set_ylim([0, 0.65])

    # Close the MATLAB engine 
    eng.quit()

    # Label TTF and FPS plot
    ttf_ax0.set_xlabel("Frequency [log]")
    ttf_ax0.set_ylabel("Amplitude")
    ttf_ax0.set_title("Camera TTF Plot")
    ttf_ax0.legend()

    ttf_ax1.set_xlabel("Frequency [log]")
    ttf_ax1.set_ylabel("Amplitude")
    ttf_ax1.set_title("Corrected Camera TTF Plot")
    ttf_ax1.legend()

    ttf_ax2.set_xlabel("Frequency [log]")
    ttf_ax2.set_ylabel("FPS")
    ttf_ax2.set_title("FPS by Frequency/Light Level")
    ttf_ax2.legend()

    # Adjust spacing between subplots
    ttf_fig.subplots_adjust(hspace=2)
    ttf_fig.subplots_adjust(wspace=0.5)
    warmup_fig.subplots_adjust(hspace=1)

    # Save the figure
    ttf_fig.savefig('/Users/zacharykelly/Aguirre-Brainard Lab Dropbox/Zachary Kelly/FLIC_admin/Equipment/SpectacleCamera/calibration/graphs/CameraTemporalSensitivity.pdf')
    warmup_fig.savefig('/Users/zacharykelly/Aguirre-Brainard Lab Dropbox/Zachary Kelly/FLIC_admin/Equipment/SpectacleCamera/calibration/graphs/warmupSettings.pdf')

    # Display the figure
    if(hold_figures_on is True):
        plt.show()

    # If we do not want to save the results, simply return 
    if(save_path is None):
        return results

    # Otherwise, save the results of generating the TTF plot
    with open(os.path.join(save_path,'TTF_info.pkl'), 'wb') as f:
        pickle.dump(results, f)

"""Generate a plot of mean microseconds per line by categorical exposure time"""
def generate_ms_by_exposure_plot(recordings_dir: str, experiment_filename: str, light_levels: list):
    # Define containers used for plotting
    x: list = []
    y: list = []
    yerr: list = []

    # Iterate across light levels
    for light_level in light_levels:
        # Define frequencies to conduct plotting for
        # and container for per-view results
        frequencies_to_test: set = {6, 12, 25}
        microseconds_per_row_list: list = []

        # Retrieve the videos by finding videos whose light level matches and whose frequencies are 
        # in the set of frequencies to test
        print(f"Retreiving {light_level} videos")
        videos = [(os.path.join(recordings_dir, file), parse_video(os.path.join(recordings_dir, file))) 
                    for file in os.listdir(recordings_dir) 
                    if f"{light_level}NDF" in file 
                    and parse_recording_filename(file)['frequency'] in frequencies_to_test
                    and parse_recording_filename(file)['experiment_name'] == experiment_filename]

        # Find the slope and associated microseconds per row of each video
        for (path, video) in videos:
            print(f'Plotting row phase for {path}')
            
            # Find the frequency for this video
            f = parse_recording_filename(os.path.split(path)[1])['frequency']

            # Calculate relevant information
            slope = generate_row_phase_plot(video, f)
            secs_per_row = slope/(2*np.pi*f)
            microseconds_per_row_list.append(abs(secs_per_row*1000000))

        # Convert list to standardized np.array
        microseconds_per_row_list: np.array = np.array(microseconds_per_row_list)
        
        # Calculate values for this light level (exposure time is categorical here since it maxes at anything below 0)
        exposure_time = 1 if light_level == '0' else 2
        mean_microseconds_per_row = np.mean(microseconds_per_row_list)
        std_microseconds_per_row = np.std(microseconds_per_row_list)

        print(f"Exposure Time: {exposure_time}")
        print(f"Mean Microseconds: {mean_microseconds_per_row}")
        print(f"Std microseconds per row: {std_microseconds_per_row}")

        # Append values to the plotting containers
        x.append(exposure_time)
        y.append(mean_microseconds_per_row)
        yerr.append(std_microseconds_per_row)

    # Plot the data
    plt.errorbar(x, y, yerr=yerr, linestyle='', marker='o', color='blue', ecolor='red')
    plt.xticks([1,2], ['600usec', '4862usec'])
    plt.title('Mean Microseconds per Row by Exposure')
    plt.xlabel('Exposure Time')
    plt.ylabel('Mean Microseconds per Row')
    plt.show()


"""Generate a plot of phase by row"""
def generate_row_phase_plot(video: np.array, frequency: float) -> float:
    # Start the MATLAB engine
    eng = matlab.engine.start_matlab()

    # Calculate the phase for each row of the video 
    phases: list = []
    for r in range(video.shape[1]):
        # Get the mean video of just this row
        row_video: np.array = np.mean(np.ascontiguousarray(video[:,r,:].astype(np.float64)), axis=1).flatten()

        # Find the phase
        observed_r2, observed_amplitude, observed_phase, observed_fit, observed_model_T, observed_signal_T = eng.fourierRegression(matlab.double(row_video),
                                                                                                                                   matlab.double(frequency), 
                                                                                                                                   matlab.double(CAM_FPS), 
                                                                                                                                   nargout=6)
        
        # Append the phase to the storage container
        phases.append(observed_phase)

    # Convert the list of phases to standardized np.array
    phases = np.unwrap(np.array(phases), period=np.pi/4)

    # Build the x and y of the figure to plot
    x, y = range(video.shape[1]), phases

    # Assert there are the same number of phases as rows
    assert len(x) == phases.shape[0]

    # Fit a linear polynomial (degree 1)
    coefficients: list = np.polyfit(x, y, 1)
    slope: float = coefficients[0]

    # Plot the phases by row
    plt.scatter(x, y, marker='.')
    plt.title('Phase by Row Number')
    plt.xlabel('Row Number')
    plt.ylabel('Phase [radians]')
    plt.show()

    return slope

def main():    
    recordings_dir, experiment_filename, ndf_range, save_path = parse_args()

    generate_TTF(recordings_dir, experiment_filename, ndf_range, save_path)

if(__name__ == '__main__'):
    main()
