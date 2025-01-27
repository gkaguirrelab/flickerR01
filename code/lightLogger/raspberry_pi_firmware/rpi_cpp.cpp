#include <iostream>
#include <filesystem>
#include "CLI11.hpp"
#include <algorithm>
#include <boost/asio.hpp>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <memory>
#include <thread>
#include "AGC.h"
#include <thread>
#include <vector>
#include <fstream>
#include <cereal/types/vector.hpp>
#include <cereal/archives/binary.hpp>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/i2c-dev.h>
#include <libcamera/libcamera.h>
#include <libuvc/libuvc.h>
#include <mutex>
#include <sys/mman.h>
#include <bitset>
#include "downsample.h"
#include <opencv2/opencv.hpp> 

namespace fs = std::filesystem; 


// Define a struct to track the performance of all of the 
// recorders of the duration of the video. This will be needed 
// to read in the data in Python and analyze performance. 
typedef struct { 
    uint32_t duration; 
    size_t M_captured_frames = 0;
    size_t W_captured_frames = 0;
    size_t P_captured_frames = 0;
    size_t S_captured_frames = 0;

} performance_data;

// NOTE: You MUST!!! run this program with sudo. Otherwise, the world camera will not connect

/*
Parse the command line arguments to the program 
@Param: argc: int - commandline argument count, 
        argv: char** - commandline argument values, 
        output_dir: filesystem:path - path to folder to output values in,
        controller_flags: std::array - array of bools to denote which controllers to use 
                          for recording, 
        duration: uint32_t - duration of the recording in seconds. 

@Ret: 0 on success, non-zero on failure
@Mod: output_dir - populates the variable with a filesystem path,
      duration - populates the variable with an int64_t representing the duration 
                 of recording in seconds 
      controller_flags - populates indices of sensors to activate
*/
int parse_args(const int argc, const char** argv, 
               fs::path& output_dir, std::array<bool, 4>& controller_flags,
               uint32_t& duration) {
    // Initialize the argparser class
    CLI::App app{"Control Firmware for GKA Lab Integrated Personal Light Logger Wearable Device"};
    
    // Add the required output path variable and populate the output_dir variable
    app.add_option("-o,--output_dir", output_dir, "The directory in which to output files. Does not need to exist.")
        ->required();

    // Add the required duration variable and populate it with the number of seconds to record for. The range is between 
    // 1 second and the number of seconds in 24 hours. 
    app.add_option("-d,--duration", duration, "Duration of the recording to make")
        ->required()
        ->check(CLI::Range(1, 86400));
    
    // Populate the controller flags for the controllers we will use
    app.add_option("-m,--minispect", controller_flags[0], "0/1 boolean flag to denote whether we will use the MS in recording.");
    app.add_option("-w,--world", controller_flags[1], "0/1 boolean flag to denote whether we will use the World Camera in recording.");
    app.add_option("-p,--pupil", controller_flags[2], "0/1 boolean flag to denote whether we will use the Pupil Camera in recording.");
    app.add_option("-s,--sunglasses", controller_flags[3], "0/1 boolean flag to denote whether we will use the Sunglasses Recorder in recording.");

    // Parse the arguments and catch if there was a parsing error, 
    // outputting helpful information upon failure. 
    try {
        CLI11_PARSE(app, argc, argv);
    }
    catch(CLI::ParseError& e) {
        app.exit(e); //Returns non 0 error code on failure
    }

    return 0; // Returns 0 on success
}


/*
Continous writing monitor for all of the process. 
Writes buffers when they are full (after a small grace period).
@Param: output_dir: fs::path* - The output directory where files will be written 
        duration: uint32_t - The duration in seconds of the entire recording
        buffer_size_s: uint8_t - The duration in seconds a given buffer is allocated for
        buffers_one: std::vector<std::vector<uint8_t>>* - Pointer to the first suprabuffer holding all of the sensors subbuffers
        buffers_two: std::vector<std::vector<uint8_t>>* - Pointer to the second suprabuffer holding all of the sensors subbuffers
@Ret: N/A 
@Mod: Writes binary serialized buffers to numbered files in output_dir 
*/
int write_process_parallel(const fs::path* output_dir, 
                           const uint32_t duration, 
                           const uint8_t buffer_size_s,
                           std::vector<std::vector<uint8_t>>* buffers_one, 
                           std::vector<std::vector<uint8_t>>* buffers_two) 
    {

    // TODO: We may be able to cut down on the write time by writing only the bytes of the pupil 
    // that have been filled (as we are using compressed MJPEG, not all 8x400x400 bytes are used. In fact, 
    // many less than that are used)

    // TODO: Need to downsample the world camera data somewhere

    // Let the user know the write process started successfully 
    std::cout << "Write | Initialized" << '\n';
    
    // Capture the start time of this process
    auto start_time = std::chrono::steady_clock::now();
    auto last_write_time = std::chrono::steady_clock::now();

    // Define a counter to keep track of which write we are on 
    uint32_t write_num = 1;

    // Define a buffer pointer to use to switch between the buffers when writing.
    // Initialize it as buffers one
    std::vector<std::vector<uint8_t>>* buffer = buffers_one; 

    // Define the variables we will use to keep track of filenames and their open files. 
    fs::path filename = "";
    std::ofstream out_file; 

    // Define timing variables we will use later

    // Write at regular intervals until the end of the recording 
    std::cout << "Write | Beginning waiting for writes..." << '\n';
    while(true) {
        // Capture the elapsed time since the start
        auto current_time = std::chrono::steady_clock::now();
        auto elapsed_time = current_time - start_time;
        auto elapsed_seconds = std::chrono::duration_cast<std::chrono::seconds>(elapsed_time).count();
        auto time_since_last_write = std::chrono::duration_cast<std::chrono::seconds>(current_time - last_write_time).count();

        // End recording if we have reached the desired duration. 
        if ((uint32_t) elapsed_seconds >= duration) {
            break;
        }

        // If we have filled at least one buffer and it is a few seconds into the next buffer, 
        // write out the previous buffer and clear it for the next swap 
        if(time_since_last_write >= (buffer_size_s + 2)) {
            // Begin timing how long writing this chunk took
            auto start_write_time = std::chrono::steady_clock::now();
            std::cout << "Write | Writing buffer: " << write_num << '\n';  

            // Retrieve the correct buffer to write
            buffer = (write_num % 2 == 0) ? buffers_two : buffers_one;

            { // Must force archive to go out of scope, ensuring all contents are flushed
                cereal::BinaryOutputArchive out_archive(out_file);
                out_archive(*buffer);
            } // Source: https://uscilab.github.io/cereal/quickstart.html under Serialize your data
            
            // Close the output file and reset the filename to ""
            out_file.close();
            filename = "";
            
            // Output how long writing this chunk took
            auto elapsed_time_writing = std::chrono::steady_clock::now() - start_write_time;
            std::cout << "Write | Writing buffer: " << write_num << " Took(ms): " << std::chrono::duration<float_t, std::milli>(elapsed_time_writing).count() << '\n';  


            // Update the last time we wrote to the current time 
            last_write_time = current_time;

            // Incremement the write num
            write_num++;
        }
        // Otherwise, let's create the file for the next buffer
        else {  
            // Generate the filename for the next chunk's output
            if(filename == "") {
                filename = "chunk_" + std::to_string(write_num) + ".bin";
            }

            // Open the file for the next chunk
            if(!out_file.is_open()) {
                // Open a file in the output directory for writing 
                out_file.open(*output_dir / filename, std::ios::binary);

                // Ensure the file was opened correctly 
                if(!out_file.is_open()) {
                    std::cerr << "ERROR: Failed to open outfile: " << *output_dir / filename << '\n';
                    exit(1);
                }
            }
        }
    }

    // When we break out of this loop, because need to write out one final buffer. This is because we wait until 
    // after the next buffer to start to write in the loop. At the end, the next buffer will never start, therefore 
    // it will never be written
    
    // Begin timing how long writing this chunk took
    auto start_write_time = std::chrono::steady_clock::now();
    std::cout << "Write | Writing buffer: " << write_num << '\n';  

   // Retrieve the correct buffer to write
    buffer = (write_num % 2 == 0) ? buffers_two : buffers_one;

    { // Must force archive to go out of scope, ensuring all contents are flushed
        cereal::BinaryOutputArchive out_archive(out_file);
        out_archive(*buffer);
    } // Source: https://uscilab.github.io/cereal/quickstart.html under Serialize your data
    
    // Close the output file and reset the filename to ""
    out_file.close();
    filename = "";
    
    // Output how long writing this chunk took
    auto elapsed_time_writing = std::chrono::steady_clock::now() - start_write_time;
    std::cout << "Write | Writing buffer: " << write_num << " Took(ms): " << std::chrono::duration<float_t, std::milli>(elapsed_time_writing).count() << '\n';  

    return 0; 
}


/*
Continous recorder for the MS. 
@Param: duration: uint32_t - Time in seconds to record for. 
        buffer one: std::vector<uint8_t>* - The first of two buffers allocated for the sensor
        buffer two: std::vector<uint8_t>* - The second of two buffers allocated for the sensor
        buffer_size_frames: uint16_t - The amount of frames until each buffer is full and needs to swap
@Ret: 0 on success, throws errors otherwise
@Mod: Fills buffer_one and buffer_two with captured values. 
*/
int minispect_recorder(const uint32_t duration, 
                       std::vector<uint8_t>* buffer_one, 
                       std::vector<uint8_t>* buffer_two,
                       const uint16_t buffer_size_frames,
                       performance_data* performance_struct) 
    {
    // Create a boost io_service object to manage the IO objects
    // and initialize serial port variable
    boost::asio::io_service io;
    boost::asio::serial_port ms(io);

    // Define the data length and the start delimeter. Therefore, 
    // each transmission is actually 2 + the data length 
    constexpr char start_delim = '<';
    constexpr char end_delim = '>';
    constexpr size_t data_length = 148; 

    // Define variables we will use to probe the serial stream and read individual 
    // bytes to look for delimeters, as well as the buffer to read data 
    std::array<char, 1> byte_read; 
    std::array<char, data_length> reading_buffer; 

    // Initialize a counter for how many frames we are going to capture and the current buffer position 
    size_t buffer_offset = 0;
    size_t frame_num = 0; 

    // Attempt to connect to the MS
    std::cout << "MS | Initializating..." << '\n'; 
    try {
        // Connect to the MS
        ms.open("/dev/ttyACM0");

    }
    catch(const std::exception& e) {
        std::cout << "ERROR: Could not open MS connection" << '\n';
        std::cerr << "ERROR: " << e.what() << '\n';

        // Close the MS and safely exit from the error
        if(ms.is_open()) { ms.close();}
        exit(1);
    }
    
    // Attempt to set options for the serial connection to the MS
    try{ 
        // Set serial port configuration options
        ms.set_option(boost::asio::serial_port_base::baud_rate(115200));
        ms.set_option(boost::asio::serial_port_base::character_size(8));
        ms.set_option(boost::asio::serial_port_base::parity(boost::asio::serial_port_base::parity::none));
        ms.set_option(boost::asio::serial_port_base::stop_bits(boost::asio::serial_port_base::stop_bits::one));
        ms.set_option(boost::asio::serial_port_base::flow_control(boost::asio::serial_port_base::flow_control::none));
    }
    catch(const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << '\n';

        // Close the MS and safely exit from the error
        if(ms.is_open()) { ms.close();}
        exit(1);
    }

    // Set the initial buffer pointer to buffer 1 and track which one 
    // we are on 
    std::vector<uint8_t>* buffer = buffer_one;
    uint8_t current_buffer = 1;

    std::cout << "MS | Initialized." << '\n';

    // Begin recording for the given duration
    std::cout << "MS | Beginning recording..." << '\n';
    auto start_time = std::chrono::steady_clock::now(); // Capture the start time 
    while(true) {
        // Capture the elapsed time and ensure it is in the units of seconds
        auto elapsed_time = std::chrono::steady_clock::now() - start_time;
        auto elapsed_seconds = std::chrono::duration_cast<std::chrono::seconds>(elapsed_time).count();

        // End recording if we have reached the desired duration.
        if ((uint32_t) elapsed_seconds >= duration) {
            break;
        }
        
        // Swap buffers if we filled up this buffer
        if(buffer_offset == buffer->size()) {
            //std::cout << "MS | Swapping buffers" << '\n';

            // If we are using buffer two, switch to buffer one, otherwise vice versa
            buffer = (current_buffer % 2 == 0) ? buffer_one : buffer_two;

            // Update the current buffer state
            current_buffer = (current_buffer % 2) + 1;

            // Reset the buffer offset to 0 since now we are working with a new buffer 
            buffer_offset = 0; 
        }

        // Read a byte from the serial stream
        boost::asio::read(ms, boost::asio::buffer(byte_read));

        // If this byte is the start buffer, note that we have received a reading
        if (byte_read[0] == start_delim) {      
            //std::cout << "MS | Captured a reading" << '\n';

            // Now we can read the correct amount of data
            boost::asio::read(ms, boost::asio::buffer(reading_buffer, data_length));

            // Read one more byte. This essentially serves to ensure we read the correct amount of data 
            // as well as reset the byte_read buffer to not the starting delimeter. It should ALWAYS be the end 
            // delimeter
            boost::asio::read(ms, boost::asio::buffer(byte_read));

            if(byte_read[0] != end_delim) {
                std::cerr << "MS | ERROR: Start delimeter not closed by end delimeter." << '\n'; 

                // Close the MS and safely exit from the error
                if(ms.is_open()) { ms.close();}
                exit(1);
            }
 
            // Ensure we are not going to overrun the buffer on this write.
            // Note since this is essentially copying an array over, we must only check if it's greater than size. 
            // Consider when buffer offset is 0. If our buffer was 1 reading (148) bytes, if we checked if buffer_offset + 148 
            // is >= it would falsely say this is out of bounds. 
            if(buffer_offset+data_length > buffer->size()) {
                std::cout << "MS | ERROR: Overran buffer" << '\n';
                
                if(ms.is_open()) { ms.close();}
                exit(1);
            }

            // Append these bytes to the buffer for the duration of the video
            std::memcpy(buffer->data()+buffer_offset, reading_buffer.data(), data_length);

            // Increment the buffer offset 
            buffer_offset += data_length; 

            // Increment the number of captured frames 
            frame_num++; 
        } 
    }
    
    // Output information about how much data we captured 
    std::cout << "MS | Capture Frames: " << frame_num << '\n';

    // Close the connection to the MS device
    std::cout << "MS | Closing..." << '\n'; 
    ms.close(); 
    std::cout << "MS | Closed." << '\n'; 

    // Save the recording performance for this recorder in the performance data struct
    performance_struct->M_captured_frames = frame_num; 

    return 0;
}

/*
Callback function for libcamera when it retrieves a frame from the world recorder
@Param:
@Ret: 
@Mod: 
*/
typedef struct {
    std::shared_ptr<libcamera::Camera> camera;
    float_t current_gain;
    int current_exposure; 
    float_t speed_setting; 
    std::chrono::steady_clock::time_point last_agc_change; 
    size_t frame_num; 
    uint64_t frame_duration;
    size_t sequence_number; 
    size_t rows;
    size_t cols; 
    uint8_t downsample_factor;
    size_t downsampled_bytes_per_image; 
    uint16_t buffer_size_frames; 
    uint8_t current_buffer;
    std::vector<uint8_t>* buffer;
    size_t buffer_offset; 
    std::vector<uint8_t>* buffer_one; 
    std::vector<uint8_t>* buffer_two; 
} world_callback_data;

static void world_frame_callback(libcamera::Request *request) {
    // Determine if we have received invalid image data (e.g. during application shutdown)
    if (request->status() == libcamera::Request::RequestCancelled) {return;}

    // Define a variable to hold the arguments passed to the callback function
    world_callback_data* data; 

    // Retrieve the current time (used to determine when we will change AGC settings)
    auto current_time = std::chrono::steady_clock::now();

    // There should be a single buffer per capture
    const libcamera::Request::BufferMap &buffers = request->buffers();
    auto buffer_pair = *buffers.begin();

    // (Unused) Stream *stream = bufferPair.first;
    libcamera::FrameBuffer *buffer = buffer_pair.second;

    // Capture the metadata of this frame. This lets us know if a frame was successfully captured and also 
    // the frame sequence number. Gaps in the sequence number indicate dropped frames 
    const libcamera::FrameMetadata &metadata = buffer->metadata();
    
    // Check if the frame was captured without any sort of error
    if(metadata.status != libcamera::FrameMetadata::Status::FrameSuccess) {
        std::cout << "World | Frame unsuccessful" << '\n';
        return ; 
    }

    // Retrieve the sequence number and ensure it is sequential with the previous one
    //if(metadata.sequence != data->sequence_number) {
    //    size_t num_dropped_frames = metadata.sequence - data->sequence_number; 
    //    std::cout << "World | Dropped " << num_dropped_frames << " frames" << '\n';  
    //}

    // Retrieve the arguments data for the callback function
    data = reinterpret_cast<world_callback_data*>(buffer->cookie());

    // Retrieve information we will lookup often from the struct onto the stack 
    size_t frame_num = data->frame_num;
    uint8_t current_buffer = data->current_buffer;

    // Swap buffers if this one is full
    if(data->buffer_offset == data->buffer->size()) {
        //std::cout << "World | Swapping buffers" << '\n';

       // If we are using buffer two, switch to buffer one, otherwise vice versa
        data->buffer = (current_buffer % 2 == 0) ? data->buffer_one : data->buffer_two;

        // Update the current buffer state and buffer pointer position
       data->current_buffer = (current_buffer % 2) + 1;
       data->buffer_offset = 0; 
    }

    // RAW images have 1 plane, so retrieve the plane the data lies on
    libcamera::FrameBuffer::Plane pixel_data_plane = buffer->planes().front();
    void *memory_map = mmap(nullptr, pixel_data_plane.length, PROT_READ, MAP_SHARED, pixel_data_plane.fd.get(), pixel_data_plane.offset);
    if (memory_map == MAP_FAILED) {
        std::cout << "World | Failed to map buffer memory!" << std::endl;
        return;
    }

    // Retireve the plane data from the object 
    //void *memory_map = mmap(nullptr, pixel_data_plane.length + pixel_data_plane.offset, PROT_READ | PROT_WRITE, MAP_SHARED, pixel_data_plane.fd.get(), 0); 

    // Cast to byte array 
    uint8_t* pixel_data = static_cast<uint8_t*>(memory_map); 

    // Ensure the image is the size we think it should be 
    if(pixel_data_plane.length != (data->rows * data->cols*2)) {
        std::cout << "World | ERROR: Bytes returned from camera "<< pixel_data_plane.length << " are not equal to intended " << data->rows * data->cols << '\n'; 
        return; 
    }

    // Downsample the image to save space, time when writing, and for privacy reasons
    downsample16(pixel_data, data->rows, data->cols, data->downsample_factor, data->buffer->data()+data->buffer_offset);

    //std::memcpy(data->buffer->data() + data->buffer_offset, pixel_data, pixel_data_plane.length);

    // Change the AGC every 250 milliseconds
    if(std::chrono::duration_cast<std::chrono::milliseconds>(current_time - data->last_agc_change).count() >= 250) {
        // Calculate the mean of the pixel data. This will be the input to the AGC
        int32_t mean_intensity = std::accumulate(pixel_data, pixel_data + pixel_data_plane.length, 0) / pixel_data_plane.length; 

        // Input the mean intensity of the current frame to the AGC. Retrieve corrected gain and exposure. 
        adjusted_settings adjusted_settings = AGC(mean_intensity, data->current_gain, data->current_exposure, data->speed_setting);

        data->current_gain = (float_t) adjusted_settings.adjusted_gain;
        data->current_exposure = (int) adjusted_settings.adjusted_exposure; 

        // Update the last AGC change time 
        data->last_agc_change = current_time;
    }  
    
    // Increment the frame number and update the sequence number 
    data->frame_num++; 
    data->sequence_number = metadata.sequence; 

    // Increment the buffer offset for the next frame 
    data->buffer_offset += data->downsampled_bytes_per_image; //pixel_data_plane.length; 

    // Put the frame buffer back into circulation with the camera 
    // with the updated controls
    request->reuse(libcamera::Request::ReuseFlag::ReuseBuffers);
    libcamera::ControlList &controls = request->controls();
    controls.set(libcamera::controls::AE_ENABLE, libcamera::ControlValue(false)); 
    controls.set(libcamera::controls::AWB_ENABLE, libcamera::ControlValue(false));
    controls.set(libcamera::controls::ANALOGUE_GAIN, libcamera::ControlValue(data->current_gain)); 
    controls.set(libcamera::controls::EXPOSURE_TIME, libcamera::ControlValue(data->current_exposure)); 
    controls.set(libcamera::controls::FrameDurationLimits, libcamera::Span<const std::int64_t, 2>({data->frame_duration, data->frame_duration}));

    data->camera->queueRequest(request);

}

/*
Continous recorder for the World Camera.
@Param: duration: uint32_t - Time in seconds to record for. 
        buffer one: std::vector<uint8_t>* - The first of two buffers allocated for the sensor
        buffer two: std::vector<uint8_t>* - The second of two buffers allocated for the sensor
        buffer_size_frames: uint16_t - The amount of frames until each buffer is full and needs to swap
@Ret: 0 on success, errors and quits otherwise. 
@Mod: Fills buffer_one and buffer_two with captured values. 
*/
int world_recorder(const uint32_t duration, 
                   std::vector<uint8_t>* buffer_one, 
                   std::vector<uint8_t>* buffer_two,
                   const uint16_t buffer_size_frames,
                   performance_data* performance_struct) 
    {
    // Define parameters for the video stream 
    constexpr size_t cols = 640; 
    constexpr size_t rows = 480;
    constexpr float_t fps = 200;
    constexpr int64_t frame_duration = 1e6/fps;
    constexpr uint8_t downsample_factor = 3; // The power of 2 with which to downsample each dimension of the frame 
    constexpr size_t downsampled_bytes_per_image = (rows >> downsample_factor) * (cols >> downsample_factor) * 2;
    constexpr float_t initial_gain = 1; 
    constexpr int initial_exposure = 100; 
    
    // Initialize libcamera
    std::cout << "World | Initializating..." << '\n'; 
    
    // Define variables to detect the camera 
    static std::shared_ptr<libcamera::Camera> camera;
    std::unique_ptr<libcamera::CameraManager> cm = std::make_unique<libcamera::CameraManager>();

    // Initialize the camera manager to begin manipulating camera devices 
    cm->start();

    // Retrieve the cameras themselves. If the world cam was not detected, throw an error
    auto cameras = cm->cameras();
    if (cameras.empty()) {
        std::cout << "World Camera | Camera not found." << '\n';
        cm->stop();
        return EXIT_FAILURE;
    }

    // Retrieve the first available camera from the manager to be the world camera 
    camera = cm->get(cameras[0]->id());

    // Acquire the camera 
    camera->acquire();

    // Define the configuration for the camera (this MUST be raw for raw images)
    std::unique_ptr<libcamera::CameraConfiguration> config = camera->generateConfiguration( { libcamera::StreamRole::Raw} );

    libcamera::StreamConfiguration &streamConfig = config->at(0);
    //std::cout << "Default viewfinder configuration is: " << streamConfig.toString() << std::endl; 

    //streamConfig.pixelFormat = libcamera::formats::;

    const libcamera::StreamFormats &formats = streamConfig.formats();

    std::cout << "Supported Pixel Formats:" << std::endl;

    for (const auto &format : formats.pixelformats()) {
        std::cout << "  " << format.toString() << std::endl;
    }

    streamConfig.pixelFormat = libcamera::formats::SRGGB8;
     // potentially look at stride for the image artifacts. 
    //streamConfig.size.shrinkBy(libcamera::Size() )

    streamConfig.size.width = cols;
    streamConfig.size.height = rows;

    if (config->validate() == libcamera::CameraConfiguration::Invalid) {
        std::cerr << "World | ERROR: Invalid configuration" << std::endl;
        return -1;
    }

    std::cout << "Validated viewfinder configuration is: " << streamConfig.toString() << std::endl;
    std::cout << "Validated size | " << "height: " << streamConfig.size.height << " width: " << streamConfig.size.width << '\n';
    std::cout << "Validated format | " << "format: " << streamConfig.pixelFormat.toString() << '\n'; 
    std::cout << "Validated Stride: " << streamConfig.stride << '\n'; 

    camera->configure(config.get());

    
    // Allocate buffers for the frames we will capture 
    libcamera::FrameBufferAllocator *allocator = new libcamera::FrameBufferAllocator(camera);

    for (libcamera::StreamConfiguration &cfg : *config) {
        int ret = allocator->allocate(cfg.stream());
        if (ret < 0) {
            std::cerr << "Can't allocate buffers" << std::endl;
            return -ENOMEM;
        }

        size_t allocated = allocator->buffers(cfg.stream()).size();
        //std::cout << "Allocated " << allocated << " buffers for stream" << std::endl;
    }

    // Define the data to be used 
    world_callback_data data;
    data.camera = camera;
    data.current_gain = initial_gain;
    data.current_exposure = initial_exposure; 
    data.speed_setting = 0.95;
    data.sequence_number = 0; 
    data.frame_num = 0;
    data.frame_duration = frame_duration;
    data.rows = rows; 
    data.cols = cols; 
    data.downsample_factor = downsample_factor;
    data.downsampled_bytes_per_image = downsampled_bytes_per_image; 
    data.current_buffer = 1;
    data.buffer = buffer_one;
    data.buffer_one = buffer_one;
    data.buffer_two = buffer_two;
    data.buffer_offset = 0;
    data.buffer_size_frames = buffer_size_frames;

    // Initialize the capture stream 
    libcamera::Stream *stream = streamConfig.stream();
    const std::vector<std::unique_ptr<libcamera::FrameBuffer>> &buffers = allocator->buffers(stream);
    std::vector<std::unique_ptr<libcamera::Request>> requests;
    for (size_t i = 0; i < buffers.size(); ++i) {
        std::unique_ptr<libcamera::Request> request = camera->createRequest();
       
        if (!request)
        {
            std::cerr << "Can't create request" << std::endl;
            return 1;
        }
        
        const std::unique_ptr<libcamera::FrameBuffer> &buffer = buffers[i];

        // Save a pointer to the callback data struct with the request
        buffer->setCookie(reinterpret_cast<uint64_t>(&data));
        int ret = request->addBuffer(stream, buffer.get());
  
        if (ret < 0)
        {
            std::cerr << "Can't set buffer for request"
                << std::endl;
            return 1;
        }

        // Set the controls of the camera (brightness, exposure, etc per request)
        // Also give the request a pointer to the data struct
        libcamera::ControlList &controls = request->controls();

        controls.set(libcamera::controls::AE_ENABLE, libcamera::ControlValue(false));
        controls.set(libcamera::controls::AWB_ENABLE, libcamera::ControlValue(false));
        controls.set(libcamera::controls::ANALOGUE_GAIN, libcamera::ControlValue(initial_gain));
        controls.set(libcamera::controls::EXPOSURE_TIME, libcamera::ControlValue(initial_exposure));
        controls.set(libcamera::controls::FrameDurationLimits, libcamera::Span<const std::int64_t, 2>({frame_duration, frame_duration}));

        requests.push_back(std::move(request)); 
    }
    
    //std::cout << "Allocated the stream " << std::endl;

    // Connect the world camera to its callback function 
    camera->requestCompleted.connect(world_frame_callback);

    // Initialize libcamera
    std::cout << "World | Initialized" << '\n'; 
    
    //std::cout << "Assigned the callback " << std::endl;

    camera->start(&requests[0]->controls());

     
    std::cout << "World | Beginning recording" << std::endl;

    for (std::unique_ptr<libcamera::Request> &request : requests) {
        camera->queueRequest(request.get());
    }
    
    /*
    auto start_time = std::chrono::steady_clock::now(); // Capture the start time
    while(true) {
        // Capture the elapsed time since start and ensure it is in the units of seconds
        auto current_time = std::chrono::steady_clock::now();
        auto elapsed_time = current_time - start_time;
        auto elapsed_seconds = std::chrono::duration_cast<std::chrono::seconds>(elapsed_time).count();
        
        // End recording if we have reached the desired duration. 
        if ((uint32_t) elapsed_seconds >= duration) {
            break;
        }


        libcamera::ControlList &controls = requests[0]->controls();
        controls.set(libcamera::controls::AE_ENABLE, libcamera::ControlValue(false));
        


    }
    */

    std::this_thread::sleep_for(std::chrono::seconds(duration));

    // Output information about how much data we captured 
    std::cout << "World | Captured Frames: " << data.frame_num << '\n';

    // Close the connection to the Camera device
    std::cout << "World | Closing..." << '\n';
    
    camera->stop();
    allocator->free(stream);
    delete allocator;
    camera->release();
    camera.reset();
    cm->stop();

    std::cout << "World | Closed." << '\n'; 

    // Save the recording performance for this recorder in the performance data struct
    performance_struct->W_captured_frames = data.frame_num; 

    return 0;
}



/*
Callback function for libUVC when it retrieves a frame from the pupil recorder
@Param:
@Ret: 
@Mod: 
*/
typedef struct {
    size_t frame_num; 
    uint16_t buffer_size_frames; 
    uint8_t current_buffer;
    std::vector<uint8_t>* buffer;
    size_t buffer_offset; 
    std::vector<uint8_t>* buffer_one; 
    std::vector<uint8_t>* buffer_two; 

} pupil_callback_data;

void pupil_frame_callback(uvc_frame_t* frame, void *ptr) {
    // Convert the usr_pointer to be a data struct    
    pupil_callback_data *data = static_cast<pupil_callback_data*>(ptr);

    // Swap buffers if this one is full
    if(data->buffer_offset == data->buffer->size()) {
        // If we are using buffer two, switch to buffer one, otherwise vice versa
        data->buffer = (data->current_buffer % 2 == 0) ? data->buffer_one : data->buffer_two;

        // Update the current buffer as well as the pointer to the position therein 
        data->current_buffer = (data->current_buffer % 2) + 1;
        data->buffer_offset = 0; 
    }
    
    // Decompress the MJPEG image to its original size, as libuvc automatically compresses the image in MJPEG format, making the number of 
    // bytes non-constant. Note: If this is too slow, we can switch to using libturbo-jpeg 
    cv::Mat uncompressed_img = cv::imdecode(cv::Mat(1, frame->data_bytes, CV_8UC1, frame->data), cv::IMREAD_GRAYSCALE);

    // Check if decoding was successful
    if (uncompressed_img.empty()) {
        std::cerr << "Pupil | ERROR: Could not decode MJPEG image." << '\n';
        return ;
    }

    // Save the desired frame into the buffer
    size_t num_bytes_uncompressed = uncompressed_img.total() * uncompressed_img.elemSize();
    std::memcpy(data->buffer->data() + data->buffer_offset, uncompressed_img.data, num_bytes_uncompressed);

    // Increment the number of captured frames and the offset into the data buffer 
    data->frame_num+=1;
    data->buffer_offset += num_bytes_uncompressed;
}

/*
Continous recorder for the Pupil Camera.
@Param: duration: uint32_t - Time in seconds to record for. 
        buffer one: std::vector<uint8_t>* - The first of two buffers allocated for the sensor
        buffer two: std::vector<uint8_t>* - The second of two buffers allocated for the sensor
        buffer_size_frames: uint16_t - The amount of frames until each buffer is full and needs to swap
@Ret: 0 on success, errors and quits otherwise. 
@Mod: Fills buffer_one and buffer_two with captured values. 
*/
int pupil_recorder(const uint32_t duration, 
                   std::vector<uint8_t>* buffer_one, 
                   std::vector<uint8_t>* buffer_two,
                   const uint16_t buffer_size_frames,
                   performance_data* performance_struct) 
    {
    
    uvc_context_t *ctx;
    uvc_device_t *dev;
    uvc_device_handle_t *devh;
    uvc_stream_ctrl_t ctrl;
    uvc_error_t res;

    // Define parameters for the video stream
    constexpr size_t img_rows = 400;
    constexpr size_t img_cols = 400; 
    constexpr size_t fps = 120;
    
    std::cout << "Pupil | Initializating..." << '\n'; 

    // Initialize libUVC 
    res = uvc_init(&ctx, NULL);
    if (res < 0) {
        uvc_perror(res, "uvc_init");
        return 1;
    }

    // Attempt to find the device (via VendorID and productID)
    res = uvc_find_device(ctx, &dev, 0x0C45, 0x64AB, NULL);
    if (res < 0) {
        uvc_perror(res, "uvc_find_device");
        uvc_exit(ctx);
        return 1;
    }

    // Attempt to open the device
    res = uvc_open(dev, &devh, 1);
    if (res < 0) {
        uvc_perror(res, "uvc_open");
        uvc_unref_device(dev);
        uvc_exit(ctx);
        return 1;
    }

    // Attempt to set the video format
    res = uvc_get_stream_ctrl_format_size(devh, &ctrl, UVC_COLOR_FORMAT_MJPEG, img_rows, img_cols, fps, 1);
    if (res < 0) {
        std::cout << "ERROR! "<< uvc_strerror(res) << '\n';
        uvc_close(devh);
        uvc_unref_device(dev);
        uvc_exit(ctx);
        return 1;
    }

    std::cout << "Pupil | Initialized." << '\n';

    // Initialize a counter for how many frames we are going to capture 
    // and how many bytes each frame is
    size_t frame_num = 0; 

    // Set the initial buffer pointer to buffer 1
    std::vector<uint8_t>* buffer = buffer_one;
    uint8_t current_buffer = 1;

    // Initialize a struct containing data for the callback function when frames are captured 
    pupil_callback_data data;
    data.frame_num = frame_num;
    data.buffer_size_frames = buffer_size_frames; 
    data.current_buffer = current_buffer; 
    data.buffer = buffer; 
    data.buffer_one = buffer_one; 
    data.buffer_two = buffer_two;  
    data.buffer_offset = data.buffer_offset;

    // Begin recording for the given duration
    std::cout << "Pupil | Beginning recording..." << '\n';
    res = uvc_start_streaming(devh, &ctrl, pupil_frame_callback, &data, 0, 1);
    if (res < 0) {
        std::cerr << "Unable to start streaming: " << uvc_strerror(res) << std::endl;
        uvc_close(devh);
        uvc_unref_device(dev);
        uvc_exit(ctx);
        return 1;
    }

    // Stop streaming after a given duration
    std::this_thread::sleep_for(std::chrono::seconds(duration));
    uvc_stop_streaming(devh);
    
    // Output information about how much data we captured 
    std::cout << "Pupil | Captured Frames: " << data.frame_num << '\n';

    // Close the connection to the Camera device
    std::cout << "Pupil | Closing..." << '\n'; 
    
    uvc_close(devh);
    uvc_unref_device(dev);
    uvc_exit(ctx);

    std::cout << "Pupil | Closed." << '\n'; 

    // Save the recording performance for this recorder in the performance data struct
    performance_struct->P_captured_frames = data.frame_num; 

    return 0;
}

/*
Continous recorder for the Sunglasses Hall magnetic sensor. 
@Param: duration: uint32_t - Time in seconds to record for. 
        buffer one: std::vector<uint8_t>* - The first of two buffers allocated for the sensor
        buffer two: std::vector<uint8_t>* - The second of two buffers allocated for the sensor
        buffer_size_frames: uint16_t - The amount of frames until each buffer is full and needs to swap
@Ret: 0 on success, errors and quits otherwise. 
@Mod: Fills buffer_one and buffer_two with captured values. 
*/
int sunglasses_recorder(const uint32_t duration,
                        std::vector<uint8_t>* buffer_one, 
                        std::vector<uint8_t>* buffer_two,
                        const uint16_t buffer_size_frames,
                        performance_data* performance_struct) 
    {
    // Initialize a connection to the bus to read from the sensor
    std::cout << "Sunglasses | Initializating..." << '\n'; 

    // Define details about where the connection to the device will live
    constexpr const char* i2c_bus_number = "/dev/i2c-1";     // I2C bus number, corresponds to /dev/i2c-1
    constexpr int device_addr = 0x6B; // Define the memory address of the device
    constexpr uint8_t config = 0x10; // Configuration command: Continuous conversion mode, 12-bit Resolution (0x10)
    constexpr uint8_t read_reg = 0x00;

    // Initialize a counter for how many frames we are going to capture 
    // and the current offset into the buffer
    size_t frame_num = 0; 
    size_t buffer_offset = 0;

    // Set the initial buffer pointer to buffer 1
    std::vector<uint8_t>* buffer = buffer_one;
    uint8_t current_buffer = 1;

    // Attempt to open the I2C bus
    int i2c_bus = open(i2c_bus_number, O_RDWR);
    if (i2c_bus < 0) {
        std::cerr << "Sunglasses | Failed to open the I2C bus" << '\n';
        exit(1);
    }

    // Set the I2C slave address
    if (ioctl(i2c_bus, I2C_SLAVE, device_addr) < 0) {
        std::cerr << "Sunglasses | Failed to set I2C address" << '\n';
        close(i2c_bus);
        exit(1);
    }

    // Write the configuration command
    if (write(i2c_bus, &config, 1) != 1) {
        std::cerr << "Sunglasses | Failed to write to the I2C device" << '\n';
        close(i2c_bus);
        exit(1);
    }

    // Write the register address
    if (write(i2c_bus, &read_reg, 1) != 1) {
        std::cerr << "Sunglasses | Failed to write to the I2C device" << '\n';
        close(i2c_bus);
        exit(1);
    }

    std::cout << "Sunglasses | Initialized..." << '\n'; 

    // Begin recording for the given duration
    std::cout << "Sunglasses | Beginning recording..." << '\n';
    auto start_time = std::chrono::steady_clock::now(); // Capture the start time
    while(true) {
        // Capture the elapsed time since start and ensure it is in the units of seconds
        auto current_time = std::chrono::steady_clock::now();
        auto elapsed_time = current_time - start_time;
        auto elapsed_seconds = std::chrono::duration_cast<std::chrono::seconds>(elapsed_time).count();
        
        // End recording if we have reached the desired duration. 
        if ((uint32_t) elapsed_seconds >= duration) {
            break;
        }

        // Swap buffers if this one is full
        if(buffer_offset == buffer->size()) {
            //std::cout << "Sunglasses | Swapping buffers" << '\n';

            // If we are using buffer two, switch to buffer one, otherwise vice versa
            buffer = (current_buffer % 2 == 0) ? buffer_one : buffer_two;
            
            // Update the current buffer state
            current_buffer = (current_buffer % 2) + 1;

            // Reset the buffer offset to 0
            buffer_offset = 0;
        }

        // Read 2 bytes from the device
        uint8_t data[2] = {0};
        if (read(i2c_bus, data, 2) != 2) {
            std::cerr << "Failed to read from the I2C device" << '\n';
            close(i2c_bus);
            exit(1);
        }

        // Process the data to convert it to 12 bits
        int16_t raw_adc = ((data[0] & 0x0F) << 8) | data[1];
        if (raw_adc > 2047) {
            raw_adc -= 4096;
        }

        //std::cout << "Sunglasses | Original Reading: " << raw_adc << '\n';

        // Need to split our reading in two parts because our reading is 12 bit and 
        // our buffer is for 8 bit values
        uint8_t lower_byte = raw_adc & 0xFF;        // Lower 8 bits of reading
        uint8_t upper_byte = (raw_adc >> 8) & 0xFF; // Upper 8 bits of reading

        //std::cout << "Sunglasses | Upper byte: " << std::bitset<8>(upper_byte) << '\n';
        //std::cout << "Sunglasses | Lower byte: " << std::bitset<8>(lower_byte) << '\n';

        // Ensure the buffer offset does not go out of bounds of the buffer array
        if(buffer_offset+1 >= buffer->size()) {
            std::cout << "Sunglasses | ERROR: Overran buffer" << '\n';
            exit(1); 
        }

        // Write the bytes from the reading to the buffer
        (*buffer)[buffer_offset] = lower_byte; 
        (*buffer)[(buffer_offset + 1)] = upper_byte; 

        // Increment the captured frame number and buffer position 
        frame_num++; 
        buffer_offset+=2; 

        // Sleep for some time between readings, as high FPS for sunglasses 
        // is not important
        std::this_thread::sleep_for(std::chrono::seconds(1));

    }

    // Output information about how much data we captured 
    std::cout << "Sunglasses | Captured Frames: " << frame_num << '\n';

    // Close the connection to the i2c_bus device
    std::cout << "Sunglasses | Closing..." << '\n'; 
    close(i2c_bus);
    std::cout << "Sunglasses | Closed." << '\n'; 

    // Save the recording performance for this recorder in the performance data struct
    performance_struct->S_captured_frames = frame_num; 
    
    return 0;
}

int main(int argc, char **argv) {
    /***************************************************************
     *                                                             *
     *                     VARIABLE INITIALIZATION                 *
     *                                                             *
     ***************************************************************/
    
    // Initialize variable to hold output directory path. Path need not exist
    fs::path output_dir;

    // Initialization container for the duration (in seconds) of the video to record. If this is 
    // negative, then it will be for infinity
    uint32_t duration; 

    // Initialize an array of sensor names. The index of these names will correspond to the sensor's info in other arrays. For instance, MS info will always be ind 0
    constexpr std::array<char, 4> controller_names = {'M', 'W', 'P', 'S'};  // this can be constexpr because values will never change 

    // Initialize controller flags as entirely false. This is because we will denote which controllers 
    // to use based on arguments passed. 
    std::array<bool, 4> controller_flags = {false, false, false, false}; // this CANNOT be constexpr because values will change 
    
    // Define the FPS of each of the sensors 
    constexpr std::array<uint8_t, 4> sensor_FPS = {1, 200, 120, 1};

    // Calculate the data size for each of the sensors per each second of capture. The sunglasses sensor is x2 because it returns a 16bit value and we are storing with 8 bit arrays
    constexpr std::array<uint64_t, 4> data_size_multiplers = {sensor_FPS[0]*148, sensor_FPS[1]*60*80*2, sensor_FPS[2]*400*400, sensor_FPS[3]*2}; // this can be constexpr because values will never change
    
    // Initialize a variable for the size of each sensors' buffer in seconds. This will be regularly written out and cleared
    constexpr uint8_t sensor_buffer_size = 10; 

    // Initialize an array of function pointers that point to the recorder functions for each sensor
    std::array<std::function<int(int32_t, std::vector<uint8_t>*, std::vector<uint8_t>*, uint16_t, performance_data*)>, 4> controller_functions = {minispect_recorder, world_recorder, pupil_recorder, sunglasses_recorder}; // this CANNOT be constexpr because function stubs are dynamic
    

    /***************************************************************
     *                                                             *
     *               ARGUMENT PARSING AND VALIDATION               *
     *                                                             *
     ***************************************************************/

    // Parse the commandline arguments.
    if(parse_args(argc, (const char**) argv, output_dir, controller_flags, duration)) {
        std::cerr << "ERROR: Could not properly parse args." << '\n'; 
        return 1; 
    }; 

    // If argparse was successful, we will ensure the output directory exists
    // First check to see if it does not already exist. If that is true, then we will make it. 
    // Then, we must check if that was succesful. If it was not successful, we output an error
    if(!fs::exists(output_dir) && !fs::create_directories(output_dir)) {
        std::cerr << "ERROR: Could not create output directory: " << output_dir << '\n'; 
        return 1;
    }

    // Find only the indices of sensors we are to use
    std::vector<size_t> used_controller_indices;
    for(size_t i = 0; i < controller_flags.size(); i++) {
        if(controller_flags[i] == true) {
            used_controller_indices.push_back(i);
        }
    }

    // Retrieve the number of sensors we are to use and ensure it is both greater than 0 
    // and within the range of sensors we have available
    const int num_active_sensors = used_controller_indices.size();
    if(num_active_sensors == 0 || (num_active_sensors > (int) controller_flags.size() )) {
        std::cerr << "ERROR: Invalid number of active sensors: " << num_active_sensors << '\n'; 
        return 1; 
    }

    // Output information about where this recording's data will be output, as well as 
    // the controllers we will use
    std::cout << "----ARGPARSE AND FILE SETUP SUCCESSFUL---" << '\n';

    std::cout << "Output Directory: " << output_dir << '\n';
    std::cout << "Duration: " << duration << " seconds" << '\n';
    std::cout << "Buffer size: " << std::to_string(sensor_buffer_size) << " seconds" << '\n'; // Not sure why but I had to use std::to_string to get this to show. I think it's because uint8_t is an alias for unsigned char
    std::cout << "Num Active Controllers: " << num_active_sensors << '\n';
    std::cout << "Controllers to use: " << '\n';
    for(size_t i = 0; i < controller_names.size(); i++) {
        std::cout << '\t' << controller_names[i] << " | " << controller_flags[i] << '\n';
    }

    /***************************************************************
     *                                                             *
     *                  BUFFER SETUP AND ALLOCATION                *
     *                                                             *
     ***************************************************************/


    // Once we know the duration and the sensors we are using, we are going to dynamically 
    // allocate two buffers of duration seconds per sensor of 8bit values. This is because 
    // we are going to spawn between them
    
    // First, allocate outer arrays for all of the potential sensors. We can use array here since we know that there will 
    // always be four controllers worth of buffers
    std::vector<std::vector<uint8_t>> buffers_one(controller_names.size());
    std::vector<std::vector<uint8_t>> buffers_two(controller_names.size());

    // Iterate over the inner buffers and reserve enough memory + fill in dummy values for all of the readings.
    // Only do this for the sensors we are actually using
    for(const auto& controller_idx: used_controller_indices) { 
        // Mutiply the duration times the data size. 
        // For instance:
            // the MS reads 148 bytes per second. 
            // the World cam reads at 200x60x80 bytes per second 
            // the Pupil cam reads at 120x400x400 bytes per second
            // the sunglasses sensor reads at 1x2 bytes per second 

        // Allocate the appropriate amount of space and initialize all values to 0 
        buffers_one[controller_idx].resize(sensor_buffer_size * data_size_multiplers[controller_idx], 0); 
        buffers_two[controller_idx].resize(sensor_buffer_size * data_size_multiplers[controller_idx], 0); 
    }


    // Output information about how the buffer allocation process went
    std::cout << "----BUFFER ALLOCATIONS SUCCESSFUL---" << '\n';
    std::cout << "Num recording buffers: " << 2 << '\n';
    std::cout << "Num sensor buffers: " << buffers_one.size() << '\n';
    std::cout << "Sensor buffer sizes | capacities(bytes): " << '\n';
    for(size_t i = 0; i < buffers_one.size(); i++) {
        std::cout << '\t' << controller_names[i] << ": " << buffers_one[i].size() << '|' << buffers_one[i].capacity() << '\n';
    }

    /***************************************************************
     *                                                             *
     *                      THREAD SPAWNING                        *
     *                                                             *
     ***************************************************************/

    // Begin parallel recording and enter performance critical section. All print statements below 
    // this point MUST use \n as a terminator instead of '\n', which is significantly slower, and all code should be 
    // absolutely optimally written in regards to time efficency. 
    std::vector<std::thread> threads;
    performance_data performance_struct; 
    performance_struct.duration = duration; 

    // We will spawn only threads for those controllers that we are going to use. 
    // Spawn them, with the duration of recording as an argument
    std::cout << "----SPAWNING THREADS---" << '\n';
    
    for (const auto& used_controller_idx: used_controller_indices) {
        threads.emplace_back(std::thread(controller_functions[used_controller_idx], 
                                         duration,
                                         &buffers_one[used_controller_idx], &buffers_two[used_controller_idx],
                                         sensor_buffer_size*sensor_FPS[used_controller_idx],
                                         &performance_struct));
    }

    // We will also spawn the parallel write process, to monitor output from these threads
    threads.emplace_back(std::thread(write_process_parallel, &output_dir, duration, 
                                                             sensor_buffer_size,
                                                             &buffers_one, &buffers_two));


    /***************************************************************
     *                                                             *
     *                      THREAD CLEANUP                         *
     *                                                             *
     ***************************************************************/


    // Join threads to ensure they complete before the program ends
    for (auto& t : threads) {
        t.join();
    }

    // Signal to the user that the threads has successfully closed their operation
    std::cout << "----THREADS CLOSED SUCCESSFULLY---" << '\n'; 


    /***************************************************************
     *                                                             *
     *                    PERFORMANCE METRICS                      *
     *                                                             *
     ***************************************************************/


    /*
    // Output the performance metrics in CSV Format
    fs::path performance_filepath = output_dir / "performance.csv";

    // Open the file in write mode
    std::ofstream performance_file(performance_filepath);

    // Check if the file is open
    if (!performance_file.is_open()) {
        std::cout << "ERROR: Could not open performance file" << '\n';
        return 1; 
    }

    // Write the performance data to the file
    performance_file << "Duration,M_frames,W_frames,P_frames,S_frames\n";
    performance_file << performance_struct.duration << ',' << performance_struct.M_captured_frames << ',' 
                     << performance_struct.W_captured_frames << ',' << performance_struct.P_captured_frames
                     << ',' << performance_struct.S_captured_frames << '\n';

    // Close the performance file
    performance_file.close();

    // Signal to the user that the threads has successfully closed their operation
    std::cout << "----LOGGED PERFORMANCE METRICS---" << '\n'; 

    */

    return 0; 
}