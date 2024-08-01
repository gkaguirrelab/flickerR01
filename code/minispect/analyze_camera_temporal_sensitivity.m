function analyze_camera_temporal_sensitivty(cal_path, output_filename)
% Analyzes the temporal sensitivity of the spectacle camera
%
% Syntax:
%   analyze_camera_temporal_sensitivty(cal_path, output_filename)
%
% Description:
%  Generates temporal sensitivity plots for both high and low light levels
%  of the camera unit on the spectacles. Also displays the ideal device for 
%  comparison. 
%
% Inputs:
%   cal_path              - String. Represents the path to the light source
%                           calibration file.      
%
%   output_filename       - String. Represents the name of the output video
%                           and graph files      
%
% Outputs:
%    modResult             - Struct. Contains the information used to compose
%                           the flicker profile. 
%
% Examples:
%{
  
%}
    
    % Step 1: Define remote connection to raspberry pi
    host = '10.103.10.181'; % IP/Hostname
    username = 'eds'; % Username to log into
    password = '1234'; % Password for this user
    remote_executer_path = '~/Documents/MATLAB/projects/combiExperiments/code/minispect/raspberry_pi_firmware/utility/remote_execute.py';  % the script to execute remote commands
    recordings_dir = '~/Documents/MATLAB/projects/combiExperiments/code/minispect/raspberry_pi_firmware/recordings/';

    disp('Trying remote connection to RP...')
    ssh2_conn = ssh2_config(host, username, password); % attempt to open a connection

    % Step 2: Define recording script to use
    recorder_path = '~/combiExperiments/code/minispect/raspberry_pi_firmware/Camera_com.py';

    % Step 3: Define parameters for the recording and command to execute 
    duration = 10; 
    
    % Step 4: Load in the calibration file for the CombiLED
    calDir = fullfile(tbLocateProjectSilent('combiExperiments'),'cal'); % Which Cal file to use (currently hard-coded)
    calFileName = 'CombiLED_shortLLG_testSphere_ND0x2.mat';

    cal_path = fullfile(calDir,calFileName);

    load(cal_path,'cals'); % Load the cal file
    cal = cals{end};
    
    % Step 5: Initialize the combiLED
    disp('Opening connection to CombiLED...')
    CL = CombiLEDcontrol(); % Initialize CombiLED Object
    CL.setGamma(cal.processedData.gammaTable);  % Update the combiLED's gamma table

    % Step 6: Collect information to compose flicker profile
    observerAgeInYears = str2double(GetWithDefault('Age in years','30'));
    pupilDiameterMm = str2double(GetWithDefault('Pupil diameter in mm','3'));
    photoreceptors = photoreceptorDictionaryHuman('observerAgeInYears',observerAgeInYears,'pupilDiameterMm',pupilDiameterMm);

    % Step 7: Compose flicker profile
    modResult = designModulation('LightFlux',photoreceptors,cal);
    CL.setSettings(modResult);
    CL.setWaveformIndex(1);
    CL.setContrast(0.8);
    
    % Step 8: Define the NDF range and frequencies
    % for which to conduct the experiment 
    ndf_range = [5, 0.2];
    frequencies = [0.5, 1];

    
    for bb = 1:numel(ndf_range) % Iterate over the NDF bounds
        NDF = ndf_range(bb);

        fprintf('Place %.1f filter onto light source. Press any key when ready\n', NDF);
        pause()
        fprintf('You now have 30 seconds to leave the room if desired.\n');
        pause(30)
        
       
        for ff = 1:numel(frequencies)  % At each NDF level, examine different frequencies
            frequency = frequencies(ff);

            CL.setFrequency(frequency); % Set the CL flicker to current frequency

            % Step 8: Start flickering 
            CL.startModulation();
            
            % Step 9 : Begin recording to the desired output path for the desired duration
            disp('Begin recording...')
            
            remote_command = sprintf('python3 %s %s %f', recorder_path, sprintf('%s_%.1f_%.1f.h264', output_filename, frequency, NDF), duration);
            ret = system(sprintf('python3 %s %s %d %s %s "%s"', remote_executer_path, host, 22, username, password, remote_command));  % Execute the remote command via the python script

            % Check if the Python subscript errored
            if(ret ~= 0)
                error('Unable to remotely execute');
            end

            pause(4*duration) % Pause for duration plus a buffer to allow for recording, saving, error checking, etc
            
            % Step 10 : Retrieve the file from the raspberry pi and save it in the recordings 
            % directory
            disp('Retrieving the file...')
            ssh2_conn = scp_get(ssh2_conn, output_filename, recordings_dir, './'); 

            % Step 11: Stop the flicker of this frequency
            CL.stopModulation(); 

        end
    end
    

    % Step 12: Close the remote connection to the raspberry pi
    disp('Closing connection to RP...')
    ssh2_conn = ssh2_close(ssh2_conn);

    % Step 13: Close the connection to the CombiLED
    CL.serialClose(); 

    % Step 14: Plot the temporal sensitivity with the help of
    % Python to parse the video, generate source/measured curves 
    % over the course of the frames
    util_module_path = '~/Documents/MATLAB/projects/combiExperiments/code/minispect/raspberry_pi_firmware/utility/Camera_util.py';

    if count(py.sys.path, util_module_path) == 0     % Add the module path to sys.path if it's not already there
        insert(py.sys.path, int32(0), util_module_path);
    end
    
    Camera_util = py.importlib.import_module('Camera_util');

    intensity_xy_values = Camera_util.analyze_temporal_sensitivty(recording_dir, output_filename);
    
    source = intensity_xy_values{1}; % Extract the parsed source and measured intensity values across the video
    measured = intensity_xy_values{2};

    % Step 15: Plot the source and measured values
    figure ; 

    plot(source)
    hold on ; 
    plot(measured)

    % Step 16: Save the flicker information
    drop_box_dir = [getpref('combiExperiments','dropboxBaseDir'), '/FLIC_admin/Equipment/SpectacleCamera/calibration/graphs/'];
    save(sprintf('%s%s_TemporalSensitivityFlicker.mat', drop_box_dir, 'camera'), 'modResult');

    return ;
end

%{

I had to use the following dicussion found in the MATLAB library discussion by Quan Chen
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