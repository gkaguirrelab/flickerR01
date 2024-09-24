function collect_camera_temporal_sensitivity_measurements(cal_path, output_filename, email)
% Collect recordings from the world camera used for generating the TTF plot
%
% Syntax:
%   collect_camera_temporal_sensitivty_measurements(cal_path, output_filename)
%
% Description:
%   Remotely communicates with the RPI to record a series of videos at different
%   NDF levels and frequencies, saved to dropbox. Notifies the given email 
%   when to change the NDF level as well as when collection as finished. 
%
% Inputs:
%   cal_path              - String. Represents the path to the light source
%                           calibration file.      
%
%   output_filename       - String. Represents the name of the output video
%                           and graph files      
%   email                 - String. Email to notify when user needs to exchange
%                           NDF levels, as well as when experiment is finished
%
% Outputs:
%    experiment_results    - Struct. Contains the amplitudes per frequency 
%                           for all of the bounds
%
%    modResult             - Struct. Contains the information used to compose
%                           the flicker profile. 
%
% Examples:
%{
    [~, calFileName, calDir] = selectCal();
    output_filename = 'myTest';
    collect_camera_temporal_sensitivity_measurements(fullfile(calDir,calFileName), output_filename);
%}
    % Step 1: Add paths to and retrieve libraries
    addpath('~/Library/Application Support/MathWorks/MATLAB Add-Ons/Collections/SSH_SFTP_SCP For Matlab (v2)/ssh2_v2_m1_r7') % add path to ssh_command library
    addpath('~/Documents/MATLAB/projects/combiExperiments/code/lightLogger/libraries_matlab/')

    current_dir = pwd; 
    cd('~/Documents/MATLAB/projects/combiExperiments/code/lightLogger/libraries_python/')
    remote_execute = py.importlib.import_module('remote_execute');
    cd('~/Documents/MATLAB/projects/combiExperiments/code/lightLogger/camera/')
    Camera_util = py.importlib.import_module('Camera_util');
    cd(current_dir);
    pickle = py.importlib.import_module('pickle');
    ndf2str_path = '~/Documents/MATLAB/projects/combiExperiments/code/minispect';
    addpath(ndf2str_path); 

    % Step 2: Define remote connection to raspberry pi
    % NOTE: Sometimes the IP will change, double check this with hostname -I on the RPI

    host = '10.102.183.211'; % IP/Hostname
    username = 'eds'; % Username to log into
    password = '1234'; % Password for this user
    recordings_dir = [getpref('combiExperiments','dropboxBaseDir'), '/FLIC_data/recordings/'];
    metadata_dir = [getpref('combiExperiments','dropboxBaseDir'), '/FLIC_data/recordings_metadata/'];
    external_ssd_path = '/media/eds/EXTERNAL1/'; 

    disp('Trying remote connection to RP...')
    ssh2_conn = ssh2_config(host, username, password); % attempt to open a connection

    % Step 3: Define recording script to use
    recorder_path = '~/combiExperiments/code/lightLogger/raspberry_pi_firmware/Camera_com.py';

    % Step 4: Define parameters for the recording and command to execute 
    % 30 seconds for warmup, 10 seconds for real recording
    warmup = 30; 
    duration = 10;
    
    % Step 5: Load in the calibration file for the CombiLED
    load(cal_path,'cals'); % Load the cal file
    cal = cals{end};
    
    % Step 6: Initialize the combiLED
    disp('Opening connection to CombiLED...')
    CL = CombiLEDcontrol(); % Initialize CombiLED Object
    CL.setGamma(cal.processedData.gammaTable);  % Update the combiLED's gamma table

    % Step 7: Collect information to compose flicker profile
    observerAgeInYears = 30;
    pupilDiameterMm = 3;
    photoreceptors = photoreceptorDictionaryHuman('observerAgeInYears',observerAgeInYears,'pupilDiameterMm',pupilDiameterMm);

    % Step 8: Compose flicker profile
    modResult = designModulation('LightFlux',photoreceptors,cal);
    CL.setSettings(modResult);
    CL.setWaveformIndex(1);
    CL.setContrast(0.5);
    
    % Step 9: Define the NDF range and frequencies
    % for which to conduct the experiment 
    ndf_range = [0];    % NDFs to try: [0,1,2,3,4]
    frequencies = [25];  % Frequencies we have been doing + also 0.5hz

    for bb = 1:numel(ndf_range) % Iterate over the NDF bounds
        NDF = ndf_range(bb);

        fprintf('Place %.1f filter onto light source. Press any key when ready\n', NDF);
        pause()
        fprintf('You now have 30 seconds to leave the room if desired.\n');
        pause(30)

        fprintf('Taking %.1f NDF warm up video...\n', NDF); 
        warmup_file = sprintf('%s%s_0hz_%sNDF_warmup.avi', external_ssd_path, output_filename, ndf2str(NDF)); 
        warmup_metadata = sprintf('%s%s_0hz_%sNDF_warmup_settingsHistory.pkl', external_ssd_path, output_filename, ndf2str(NDF)); 
        
        % Record the warm up video
        remote_command = sprintf('python3 %s "%s" %f --save_video 0', recorder_path, warmup_file, warmup);
        remote_execute.run_ssh_command(py.str(char(host)), py.int(22), py.str(char(username)), py.str(char(password)), py.str(char(remote_command)))
        

        % Retrieve the warmup settings
        disp('Retrieving the settings file...')
        [~, baseName, ext] = fileparts(warmup_metadata);
        ssh2_conn = scp_get(ssh2_conn, [baseName, ext], metadata_dir, external_ssd_path); 

        % Delete the warmup settings and video
        disp('Deleting the file over of raspberry pi...')
        ssh2_conn = ssh2_command(ssh2_conn, sprintf('rm "%s"', warmup_metadata));

        % Retrieve the initial gain and exposure value to set the camera with
        fileID = py.open(fullfile(metadata_dir, [baseName, ext]), 'rb');
        py_data = pickle.load(fileID);
        warmup_metadata_struct = struct(py_data);
        gain_values = double(warmup_metadata_struct.gain_history);
        exposure_values = double(warmup_metadata_struct.exposure_history);

        initial_gain = gain_values(end);
        initial_exposure = exposure_values(end);
               
        for ff = 1:numel(frequencies)  % At each NDF level, examine different frequencies
            frequency = frequencies(ff);
            fprintf('Recording %0.1f NDF %0.1f hz\n', NDF, frequency);
            fprintf('with initial gain %f and initial exposure %d\n', initial_gain, initial_exposure);
            output_file = sprintf('%s%s_%.1fhz_%sNDF.avi', external_ssd_path, output_filename, frequency, ndf2str(NDF)); 
            metadata_file = sprintf('%s%s_%.1fhz_%sNDF_settingsHistory.pkl', external_ssd_path, output_filename, frequency, ndf2str(NDF)); 

            CL.setFrequency(frequency); % Set the CL flicker to current frequency

            % Step 8: Start flickering 
            CL.startModulation();
            
            % Step 9 : Begin recording to the desired output path for the desired duration
            disp('Begin recording...')
            remote_command = sprintf('python3 %s %s %f --save_video 1 --initial_gain %f --initial_exposure %d', recorder_path, output_file, duration, initial_gain, initial_exposure);
            remote_execute.run_ssh_command(py.str(char(host)), py.int(22), py.str(char(username)), py.str(char(password)), py.str(char(remote_command)))
            
            % Step 10: Stop the flicker of this frequency
            CL.goDark();
            CL.stopModulation(); 
            
            % Step 11 : Retrieve the files from the raspberry pi and save it in the recordings 
            % directory
            disp('Retrieving the settings file...')
            [~, baseName, ext] = fileparts(metadata_file);
            ssh2_conn = scp_get(ssh2_conn, [baseName, ext], metadata_dir, external_ssd_path); 

            disp('Retrieving the video file...')
            [~, baseName, ext] = fileparts(output_file);
            ssh2_conn = scp_get(ssh2_conn, [baseName, ext], recordings_dir, external_ssd_path); 

            % Step 12: Delete the file from the raspberry pi
            disp('Deleting the file over of raspberry pi...')
            ssh2_conn = ssh2_command(ssh2_conn, sprintf('rm %s', output_file));

        end

        % Notify the user it is time to change the NDF level 
        sendmail(email, 'Change the NDF filter for camera temporal sensitivity measurement')

    end

    % Step 12: Close the remote connection to the raspberry pi
    disp('Closing connection to RP...')
    ssh2_conn = ssh2_close(ssh2_conn);

    % Step 13: Close the connection to the CombiLED
    CL.serialClose(); 

    % Parse the resulting videos and save the information to plot the TTF in MATLAB
    TTF_info = struct(Camera_util.generate_TTF(py.str(recordings_dir), py.str(experiment_filename), py.list(arrayfun(@ndf2str, ndf_range, "UniformOutput", false))));

    % Step 16: Save the results and flicker information
    drop_box_dir = [getpref('combiExperiments','dropboxBaseDir'), '/FLIC_admin/Equipment/SpectacleCamera/calibration/graphs/'];
    save(sprintf('%sTTF_info.mat', drop_box_dir), 'TTF_info');
    save(sprintf('%s_TemporalSensitivityFlicker.mat', drop_box_dir), 'modResult');

    % Notify the user the collection as finished 
    sendmail(email, 'Finished collecting camera temporal sensitivity measurment')

end

%{

I had to use the following dicussion found in the MATLAB SSH library discussion by Quan Chen
to enable the ssh module to work. Note I also had to add the + in front of ssh-rsa to get it 
to work AND have regular password-based SSH work. 

I got the same error as Gernot after I upgrade my server to Ubuntu 20.04.  The dreadful "SSH2 could not connect to the ssh2 host - "ip"".  A quick check of the /var/log/auth.log showed "no matching key exchange method found. Their offer: diffie-hellman-group-exchange-sha1,diffie-hellman-group14-sha1,diffie-hellman-group1-sha1 [preauth]"
The following is my fix:
On the ssh server side, sudo vi /etc/ssh/sshd_config  (you can use your favorite editor)
append the following two lines 
KexAlgorithms diffie-hellman-group16-sha512,diffie-hellman-group18-sha512,diffie-hellman-group14-sha256,diffie-hellman-group14-sha1
HostKeyAlgorithms +ssh-rsa,ssh-dss
Save.  run the command: sudo systemctl restart ssh
Now the ssh from matlab side works.
If you don't have sudo rights on the server you are attempt to connect, there are ways to modify the ~/.ssh/config under your account to get it work.  However, I didn't test that route.


%}