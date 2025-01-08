function runDiscrimFlickerThresh(subjectID,NDlabel,refFreqHz,varargin)
% Psychometric measurement of discrmination thresholds at a set of
% frequencies for two post-receptoral directions (LMS and L-M).
%
% Examples:
%{
    subjectID = 'PILT_0001';
    NDlabel = '0x5';
    refFreqHz = [24,12,6,3,1.5];
    runDiscrimThreshExperiment(subjectID,NDlabel,refFreqHz);
%}

% Parse the parameters
p = inputParser; p.KeepUnmatched = false;
p.addParameter('dropBoxBaseDir',getpref('combiExperiments','dropboxBaseDir'),@ischar);
p.addParameter('dropBoxSubDir','FLIC_data',@ischar);
p.addParameter('projectName','combiLED',@ischar);
p.addParameter('modDirections',{'LminusM_wide','LightFlux'},@iscell);
p.addParameter('targetPhotoreceptorContrast',[0.075,0.333],@isnumeric);
p.addParameter('stimParamsHi',{linspace(0,3,51),linspace(0,3,51)},@isnumeric);
p.addParameter('stimParamsLow',{linspace(-3,0,51),linspace(-3,0,51)},@isnumeric);
p.addParameter('nTrialsPerBlock',30,@isnumeric);
p.addParameter('nBlocks',10,@isnumeric);
p.addParameter('useStaircase',false,@islogical);
p.addParameter('verboseCombiLED',false,@islogical);
p.addParameter('verbosePsychObj',true,@islogical);
p.addParameter('simulateResponse',false,@islogical);
p.addParameter('simulateStimuli',false,@islogical);
p.parse(varargin{:})

%  Pull out of the p.Results structure
nTrialsPerBlock = p.Results.nTrialsPerBlock;
nBlocks = p.Results.nBlocks;
useStaircase = p.Results.useStaircase;
modDirections = p.Results.modDirections;
targetPhotoreceptorContrast = p.Results.targetPhotoreceptorContrast;
verboseCombiLED = p.Results.verboseCombiLED;
verbosePsychObj = p.Results.verbosePsychObj;
simulateResponse = p.Results.simulateResponse;
simulateStimuli = p.Results.simulateStimuli;

% Set our experimentName
experimentName = 'DSCM';

% Set the labels for the high and low stimulus ranges
stimParamLabels = {'stimParamsHi','stimParamsLow'};

% Set a random seed
rng('shuffle');

% Define the modulation and data directories
subjectDir = fullfile(...
    p.Results.dropBoxBaseDir,...
    p.Results.dropBoxSubDir,...
    p.Results.projectName,...
    subjectID);

% Load a modResult file and extract the calibration. We need this to
% obtain a gamma table to pass to the combiLED, and this property of the
% device does not change with modulation direction
modResultFile = ...
    fullfile(subjectDir,[modDirections{1} '_ND' NDlabel],'modResult.mat');
load(modResultFile,'modResult');
cal = modResult.meta.cal;

% Set up the CombiLED
if simulateStimuli
    CombiLEDObj = [];
else

% Open the CombiLED and update the gamma table
CombiLEDObj = CombiLEDcontrol('verbose',verboseCombiLED);
CombiLEDObj.setGamma(cal.processedData.gammaTable);
end

% Provide instructions
fprintf('**********************************\n');
fprintf('On each of many trials you will be presented with 2 seconds of flicker\n');
fprintf('during each of two intervals. Your job is to indicate which interval\n');
fprintf('had the faster flickering stimulus by pressing the 1 or 2 key on the\n');
fprintf('numeric key pad. Each block has %d trials in a row after\n',nTrialsPerBlock);
fprintf('which you may take a brief break. There are a total of %d blocks.\n',nBlocks);
fprintf('**********************************\n\n');

% Prepare to loop over blocks
for bb=1:nBlocks

    % Switch back and forth between the modulation directions
    directionIdx = mod(bb,2)+1;

    % Which direction we will use this time
    modResultFile = ...
        fullfile(subjectDir,[modDirections{directionIdx} '_ND' NDlabel],'modResult.mat');

    % Load the previously generated modResult file for this direction
    load(modResultFile,'modResult');

    % Create a directory for the subject
    dataDir = fullfile(subjectDir,[modDirections{directionIdx} '_ND' NDlabel],experimentName);
    if ~isfolder(dataDir)
        mkdir(dataDir)
    end

    % Assemble the psychObj array, looping over the high and low range of
    % the discrimination function AND the reference frequencies
    psychObjArray = cell(2, length(refFreqHz));
    for ss = 1:2
        for rr = 1:length(refFreqHz)

            % Define the filestem for this psychometric object
            dataDir = fullfile(subjectDir,[modDirections{directionIdx} '_ND' NDlabel],experimentName);
            psychFileStem = [subjectID '_' modDirections{directionIdx} '_' experimentName ...
                '_' strrep(num2str(targetPhotoreceptorContrast(directionIdx)),'.','x') ...
                '_refFreq-' num2str(refFreqHz(rr)) 'Hz' ...
                '_' stimParamLabels{ss}];

            % Calculate the testContrast
            maxPhotoreceptorContrast = mean(abs(modResult.contrastReceptorsBipolar(modResult.meta.whichReceptorsToTarget)));
            testContrast = targetPhotoreceptorContrast(directionIdx) / maxPhotoreceptorContrast;

            % Obtain the relevant stimParam values
            stimParamsDomainList = p.Results.(stimParamLabels{ss}){directionIdx};

            % Create or load the psychometric object
            filename = fullfile(dataDir,[psychFileStem '.mat']);
            if isfile(filename)
                % Load the object
                load(filename,'psychObj');
                % Put in the fresh CombiLEDObj
                psychObj.CombiLEDObj = CombiLEDObj;
                % Initiate the CombiLED settings
                psychObj.initializeDisplay;
                % Increment blockIdx
                psychObj.blockIdx = psychObj.blockIdx+1;
                psychObj.blockStartTimes(psychObj.blockIdx) = datetime();
                % Update the useStaircase flag in case this has changed
                psychObj.useStaircase = useStaircase;
            else
                % Create the object
                psychObj = PsychDiscrimFlickerThreshold(CombiLEDObj,modResult,refFreqHz(rr),...
                    'refContrast',testContrast,'testContrast',testContrast,...
                    'stimParamsDomainList',stimParamsDomainList,'verbose',verbosePsychObj, ...
                    'simulateResponse',simulateResponse,'simulateStimuli',simulateStimuli,...
                    'useStaircase', useStaircase);
                % Store the filename
                psychObj.filename = filename;
            end

            % Store in the psychObjArray
            psychObjArray{ss, rr} = psychObj;

            % Clear the psychObj
            clear psychObj

        end

    end

    % Start the block
    fprintf('Press enter to start block %d...',bb);
    input('');

    % Store the block start time
    for ss = 1:2
        for rr = 1:length(refFreqHz)
            blockStartTime = datetime();
            psychObjArray{ss, rr}.blockStartTimes(psychObjArray{ss,rr}.blockIdx) = blockStartTime;
        end
    end
    
    % Create two vectors, one containing estimate types (high or low side)
    % and the other containing reference frequencies

    % High or low side estimate vector
    estimateType = zeros(1, nTrialsPerBlock);
    % Assign the first half of the values as 1 and the second half as 2
    estimateType(1, 1:(nTrialsPerBlock/2)) = 1;
    estimateType(1, (nTrialsPerBlock/2)+1:nTrialsPerBlock) = 2;

    % Reference frequency vector, which will contain indices of refFreqHz
    refFreqHzIndex = zeros(1, nTrialsPerBlock);

    group = ceil(nTrialsPerBlock / length(refFreqHz)); 
    startIdx = 1;

    % Loop through indices
    for ii = 1:length(refFreqHz)

        % Find the end index for the current group (range of columns)
        endIdx = startIdx + group - 1;
      
        % Assign the current refFreqHz index value to the current group
        refFreqHzIndex(1, startIdx:endIdx) = ii;

        startIdx = endIdx + 1;

    end

    % Permute the elements of both lists to randomize them
    estimateType = estimateType(randperm(length(estimateType)));
    refFreqHzIndex = refFreqHzIndex(randperm(length(refFreqHzIndex)));

    % Present nTrials
    for ii = 1:nTrialsPerBlock
        psychObjArray{estimateType(ii), refFreqHzIndex(ii)}.presentTrial
    end

    % Report completion of this block
    fprintf('done.\n');

    % Store the psychObjArray entries
    for ss = 1:2
        for rr = 1:length(refFreqHz)
            % Grab the next psychObj
            psychObj = psychObjArray{ss, rr};
            % empty the CombiLEDObj handle and save the psychObj
            psychObj.CombiLEDObj = [];
            save(psychObj.filename,'psychObj');
        end
    end

end % block loop

% Clean up
if ~simulateStimuli
    CombiLEDObj.goDark;
    CombiLEDObj.serialClose;
end
clear CombiLEDObj

end % function
