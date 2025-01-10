close all
clear

subjectID = 'PILT_0004';
flickerFreqSetHz = [1.5,3,6,12,24];

dropBoxBaseDir=getpref('combiExperiments','dropboxBaseDir');
dropBoxSubDir='FLIC_data';
projectName='combiLED';
experimentName = 'DSCM';

% Set the labels for the light levels and directions
NDlabelsAll = {'0x5','3x5'};
modDirections = {'LminusM_wide','LightFlux'};
targetPhotoreceptorContrast = [0.075,0.333];
% Set the labels for the high and low stimulus ranges
stimParamLabels = {'stimParamsLow', 'stimParamsHi'};

% Define the modulation and data directories
subjectDir = fullfile(...
    dropBoxBaseDir,...
    dropBoxSubDir,...,
    projectName,...
    subjectID);

%% Plot the full psychometric functions

% Set up a figure
figHandle = figure(1);
figuresize(750,250,'units','pt');
tiledlayout(length(modDirections),length(flickerFreqSetHz),"TileSpacing","compact",'Padding','tight');

for ii = 1:length(modDirections)
    for rr = 1:length(flickerFreqSetHz)

        dataDir = fullfile(subjectDir,[modDirections{ii} '_ND' NDlabelsAll{2}],experimentName);
        nexttile;
        hold on

        % To plot the psychometric function - collect the high and low side
        % estimate objects in an array
        psychObjArray = {};

        for ss = 1:2

            % Load this measure
            psychFileStem = [subjectID '_' modDirections{ii} ...
                '_' experimentName '_' ...
                strrep(num2str(targetPhotoreceptorContrast(ii)),'.','x') ...
                '_refFreq-' num2str(flickerFreqSetHz(rr)) 'Hz' ...
                '_' stimParamLabels{ss}];
            filename = fullfile(dataDir,psychFileStem);
            load(filename,'psychObj');

            % Store some of these parameters
            questData = psychObj.questData;
            stimParamsDomainList = psychObj.stimParamsDomainList;
            psiParamsDomainList = psychObj.psiParamsDomainList;
            nTrials = length(psychObj.questData.trialData);

            % Get the Max Likelihood psi params, temporarily turning off verbosity.
            lb = cellfun(@(x) min(x),psychObj.psiParamsDomainList);
            ub = cellfun(@(x) max(x),psychObj.psiParamsDomainList);
            storeVerbose = psychObj.verbose;
            psychObj.verbose = false;
            [psiParamsQuest, psiParamsFit, psiParamsCI, fVal] = psychObj.reportParams('lb',lb,'ub',ub,'nBoots',100);
            psychObj.verbose = storeVerbose;

            % Get the proportion selected "test" for each stimulus
            stimCounts = qpCounts(qpData(questData.trialData),questData.nOutcomes);
            stim = zeros(length(stimCounts),questData.nStimParams);
            for cc = 1:length(stimCounts)
                stim(cc) = stimCounts(cc).stim;
                nTrials(cc) = sum(stimCounts(cc).outcomeCounts);
                pSelectTest(cc) = stimCounts(cc).outcomeCounts(2)/nTrials(cc);
            end

            % Plot these
            markerSizeIdx = discretize(nTrials,3);
            markerSizeSet = [25,50,100];
            for cc = 1:length(stimCounts)
                scatter(stim(cc),pSelectTest(cc),markerSizeSet(markerSizeIdx(cc)),'o', ...
                    'MarkerFaceColor',[pSelectTest(cc) 0 1-pSelectTest(cc)], ...
                    'MarkerEdgeColor','k', ...
                    'MarkerFaceAlpha',nTrials(cc)/max(nTrials));
                hold on
            end

            psychObjArray{ss} = psychObj;
        end

        % Add the psychometric function
        stimParamsDomainList = [psychObjArray{1}.stimParamsDomainList, psychObjArray{2}.stimParamsDomainList];

        % Get the Max Likelihood psi params, temporarily turning off verbosity.

        % Finding ub and lb based on the high and low side psychometric objects
        lb1 = cellfun(@(x) min(x),psychObjArray{1}.psiParamsDomainList);
        lb2 = cellfun(@(x) min(x),psychObjArray{2}.psiParamsDomainList);
        lb = min(lb1, lb2);
        ub1 = cellfun(@(x) max(x),psychObjArray{1}.psiParamsDomainList);
        ub2 = cellfun(@(x) max(x),psychObjArray{2}.psiParamsDomainList);
        ub = max(ub1, ub2);

        storeVerbose1 = psychObjArray{1}.verbose;
        storeVerbose2 = psychObjArray{2}.verbose;
        psychObjArray{1}.verbose = false;
        psychObjArray{2}.verbose = false;

        [psiParamsQuest, psiParamsFit, psiParamsCI, fVal] = psychObjArray{1}.reportCombinedParams(psychObjArray{2}, 'lb', lb, 'ub', ub, 'nBoots', 100);

        psychObjArray{1}.verbose = storeVerbose1;
        psychObjArray{2}.verbose = storeVerbose2;

        % Forcing the lapse rate to be 0
        psiParamsFit(1, 3) = 0;

        for cc = 1:length(stimParamsDomainList)
            outcomes = psychObjArray{1}.questData.qpPF(stimParamsDomainList(cc),psiParamsFit);
            fitCorrect(cc) = outcomes(2);
        end
        plot(stimParamsDomainList,fitCorrect,'-k');

        % Add a marker for the 50% point
        %        outcomes = psychObj.questData.qpPF(psiParamsFit(1),psiParamsFit);
        %        plot([psiParamsFit(1), psiParamsFit(1)],[0, outcomes(2)],':k')
        %        plot([min(stimParamsDomainList), psiParamsFit(1)],[0.5 0.5],':k')

        % Labels and range
        xlim([-3.0 3.0]);
        ylim([-0.1 1.1]);
        if rr == 6
            xlabel('stimulus difference [dB]');
        end
        if rr == 1
            ylabel('proportion pick test as faster');
        end

        % Add a title
        str = sprintf('%2.1f Hz',psychObj.refFreqHz);
        title(str);
        box off

        % Store the slope of the psychometric function
        if ii == 1
            slopeVals(rr) = normpdf(0,psiParamsFit(1),psiParamsFit(2));
            slopeValCI(rr,1) = normpdf(0,psiParamsCI(1,1),psiParamsCI(1,2));
            slopeValCI(rr,2) = normpdf(0,psiParamsCI(2,1),psiParamsCI(2,2));
                     
        end

        if ii == 2
            slopeVals2(rr) = normpdf(0,psiParamsFit(1),psiParamsFit(2));
            slopeValCI2(rr,1) = normpdf(0,psiParamsCI(1,1),psiParamsCI(1,2));
            slopeValCI2(rr,2) = normpdf(0,psiParamsCI(2,1),psiParamsCI(2,2));
        end
    end

end

%% Plot the slopes of the psychometric functions with two arms

% Plotting the slopes with CIs
% Set up a second figure
figHandle2 = figure(2);
figuresize(750,250,'units','pt');
tiledlayout(length(modDirections),1,"TileSpacing","compact",'Padding','tight');

for ii = 1:length(modDirections)
    for rr = 1:length(flickerFreqSetHz)

        dataDir = fullfile(subjectDir,[modDirections{ii} '_ND' NDlabelsAll{1}],experimentName);

        xData = log10(flickerFreqSetHz);

        for ss = 1:2 % High and low side estimates

            % Load this measure
            psychFileStem = [subjectID '_' modDirections{ii} ...
                '_' experimentName '_' ...
                strrep(num2str(targetPhotoreceptorContrast(ii)),'.','x') ...
                '_refFreq-' num2str(flickerFreqSetHz(rr)) 'Hz' ...
                '_' stimParamLabels{ss}];
            filename = fullfile(dataDir,psychFileStem);
            load(filename,'psychObj');

            % Get params
            [psiParamsQuest, psiParamsFit, psiParamsCI, fVal] = psychObj.reportParams('lb',lb,'ub',ub,'nBoots',100);

            % Calculate slopes and CIs for the current mod direction and
            % estimate type
            if ii == 1
                if ss == 1
                    slopeVals_LminusM_LowTest(rr) = normpdf(0,psiParamsFit(1),psiParamsFit(2));
                    slopeValCI_LminusM_LowTest(rr,1) = normpdf(0,psiParamsCI(1,1),psiParamsCI(1,2));
                    slopeValCI_LminusM_LowTest(rr,2) = normpdf(0,psiParamsCI(2,1),psiParamsCI(2,2));
                elseif ss == 2
                    slopeVals_LminusM_HiTest(rr) = normpdf(0,psiParamsFit(1),psiParamsFit(2));
                    slopeValCI_LminusM_HiTest(rr,1) = normpdf(0,psiParamsCI(1,1),psiParamsCI(1,2));
                    slopeValCI_LminusM_HiTest(rr,2) = normpdf(0,psiParamsCI(2,1),psiParamsCI(2,2));
                end               
            end

            if ii == 2
                if ss == 1
                    slopeVals_LightFlux_LowTest(rr) = normpdf(0,psiParamsFit(1),psiParamsFit(2));
                    slopeValCI_LightFlux_LowTest(rr,1) = normpdf(0,psiParamsCI(1,1),psiParamsCI(1,2));
                    slopeValCI_LightFlux_LowTest(rr,2) = normpdf(0,psiParamsCI(2,1),psiParamsCI(2,2));
                elseif ss == 2
                    slopeVals_LightFlux_HiTest(rr) = normpdf(0,psiParamsFit(1),psiParamsFit(2));
                    slopeValCI_LightFlux_HiTest(rr,1) = normpdf(0,psiParamsCI(1,1),psiParamsCI(1,2));
                    slopeValCI_LightFlux_HiTest(rr,2) = normpdf(0,psiParamsCI(2,1),psiParamsCI(2,2));
                end
            end

        end

    end

    if ii == 1 % L minus M

        nexttile;
        hold on;

        plot(xData, slopeVals_LminusM_LowTest, '-o', 'LineWidth', 2, 'Color', [0, 0, 0.5]);
        plot(xData,  slopeVals_LminusM_HiTest, '-o', 'LineWidth', 2, 'Color', [0, 0.5, 0]);

        for rr = 1:length(flickerFreqSetHz)
            % Plot the confidence interval for each slope value
            plot([xData(rr), xData(rr)], [slopeValCI_LminusM_LowTest(rr, 1), slopeValCI_LminusM_LowTest(rr, 2)], '-', 'LineWidth', 3, 'Color', [0, 0, 0.5]); % vertical line for CI
            plot([xData(rr), xData(rr)], [slopeValCI_LminusM_HiTest(rr, 1), slopeValCI_LminusM_HiTest(rr, 2)], '-g', 'LineWidth', 3, 'Color', [0, 0.5, 0]); % vertical line for CI
        end

        title('L minus M');

    elseif ii == 2 % LightFlux

        nexttile;
        hold on;

        plot(xData, slopeVals_LightFlux_LowTest, '-o', 'LineWidth', 2, 'Color', [0, 0, 0.5]);
        plot(xData, slopeVals_LightFlux_HiTest, '-o', 'LineWidth', 2, 'Color', [0, 0.5, 0]);

        for rr = 1:length(flickerFreqSetHz)
            % Plot the confidence interval for each slope value
            plot([xData(rr), xData(rr)], [slopeValCI_LightFlux_LowTest(rr, 1), slopeValCI_LightFlux_LowTest(rr, 2)], '-b', 'LineWidth', 3, 'Color', [0, 0, 0.5]); % vertical line for CI
            plot([xData(rr), xData(rr)], [slopeValCI_LightFlux_HiTest(rr, 1), slopeValCI_LightFlux_HiTest(rr, 2)], '-g', 'LineWidth', 3, 'Color', [0, 0.5, 0]); % vertical line for CI
        end

        title('Light Flux');

    end

    xlabel('log reference frequency (Hz)');
    ylabel('slope of psychometric function');
    ylim([0,2]);
    legend('Low Test', 'High Test');

end

%% Plot the sigmas or slopes of the full psychometric functions with CIs

% Set up a third figure
figHandle3 = figure(3);
figuresize(750,250,'units','pt');
% tiledlayout(length(modDirections),1,"TileSpacing","compact",'Padding','tight');

count = 1;

while true    

    if count == 1
        subjectID = 'PILT_0003';

        % dropBoxBaseDir=getpref('combiExperiments','dropboxBaseDir');
        % dropBoxSubDir='FLIC_data';
        % projectName='combiLED';
        % experimentName = 'DSCM';

        subjectDir = fullfile(...
            dropBoxBaseDir,...
            dropBoxSubDir,...,
            projectName,...
            subjectID);

        NDlabel = NDlabelsAll{1};

    elseif count == 2
        subjectID = 'PILT_0004';
        % 
        % dropBoxBaseDir=getpref('combiExperiments','dropboxBaseDir');
        % dropBoxSubDir='FLIC_data';
        % projectName='combiLED';
        % experimentName = 'DSCM';

        subjectDir = fullfile(...
            dropBoxBaseDir,...
            dropBoxSubDir,...,
            projectName,...
            subjectID);

        NDlabel = NDlabelsAll{2};
    end

    count = count + 1;

    hold on

    for ii = 1:length(modDirections)
        for rr = 1:length(flickerFreqSetHz)

            dataDir = fullfile(subjectDir,[modDirections{ii} '_ND' NDlabel],experimentName);

            xData = log10(flickerFreqSetHz);

            psychObjArray = {};

            for ss = 1:2 % High and low side estimates

                % Load this measure
                psychFileStem = [subjectID '_' modDirections{ii} ...
                    '_' experimentName '_' ...
                    strrep(num2str(targetPhotoreceptorContrast(ii)),'.','x') ...
                    '_refFreq-' num2str(flickerFreqSetHz(rr)) 'Hz' ...
                    '_' stimParamLabels{ss}];
                filename = fullfile(dataDir,psychFileStem);
                load(filename,'psychObj');

                psychObjArray{ss} = psychObj;

            end

            % Get params
            lb1 = cellfun(@(x) min(x),psychObjArray{1}.psiParamsDomainList);
            lb2 = cellfun(@(x) min(x),psychObjArray{2}.psiParamsDomainList);
            lb = min(lb1, lb2);
            ub1 = cellfun(@(x) max(x),psychObjArray{1}.psiParamsDomainList);
            ub2 = cellfun(@(x) max(x),psychObjArray{2}.psiParamsDomainList);
            ub = max(ub1, ub2);

            [psiParamsQuest, psiParamsFit, psiParamsCI, fVal] = psychObjArray{1}.reportCombinedParams(psychObjArray{2},'lb',lb,'ub',ub,'nBoots',100);

            % Calculate sigmas and CIs for the current mod direction and
            % estimate type
            if ii == 1
                % Sigmas
                % slopeVals_LminusM(rr) = psiParamsFit(2);
                % slopeValCI_LminusM(rr,1) = psiParamsCI(1,2);
                % slopeValCI_LminusM(rr,2) = psiParamsCI(2,2);

                % Slopes
                slopeVals_LminusM(rr) = normpdf(0,psiParamsFit(1),psiParamsFit(2));
                slopeValCI_LminusM(rr,1) = normpdf(0,psiParamsCI(1,1),psiParamsCI(1,2));
                slopeValCI_LminusM(rr,2) = normpdf(0,psiParamsCI(2,1),psiParamsCI(2,2));
            end

            if ii == 2
                % Sigmas
                % slopeVals_LightFlux(rr) = psiParamsFit(2);
                % slopeValCI_LightFlux(rr,1) = psiParamsCI(1,2);
                % slopeValCI_LightFlux(rr,2) = psiParamsCI(2,2);

                % Slopes
                slopeVals_LightFlux(rr) = normpdf(0,psiParamsFit(1),psiParamsFit(2));
                slopeValCI_LightFlux(rr,1) = normpdf(0,psiParamsCI(1,1),psiParamsCI(1,2));
                slopeValCI_LightFlux(rr,2) = normpdf(0,psiParamsCI(2,1),psiParamsCI(2,2));
            end

        end

        if ii == 1 % L minus M

            subplot(2, 1, 1);
            hold on;

            plot(xData, slopeVals_LminusM, '-o', 'LineWidth', 2, 'Color', [0, 0, 0.5]);

            for rr = 1:length(flickerFreqSetHz)
                % Plot the confidence interval for each slope value
                plot([xData(rr), xData(rr)], [slopeValCI_LminusM(rr, 1), slopeValCI_LminusM(rr, 2)], '-', 'LineWidth', 3, 'Color', [0, 0, 0.5]); % vertical line for CI
            end

            title('L minus M');

        elseif ii == 2 % LightFlux

            subplot(2, 1, 2);
            hold on;

            plot(xData, slopeVals_LightFlux, '-o', 'LineWidth', 2, 'Color', [0, 0, 0.5]);

            for rr = 1:length(flickerFreqSetHz)
                % Plot the confidence interval for each slope value
                plot([xData(rr), xData(rr)], [slopeValCI_LightFlux(rr, 1), slopeValCI_LightFlux(rr, 2)], '-b', 'LineWidth', 3, 'Color', [0, 0, 0.5]); % vertical line for CI
            end

            title('Light Flux');

        end

        xlabel('log reference frequency (Hz)');
        ylabel('slope value');
        ylim([0,2]);

    end

    if count == 2
        break
    end

end % while loop 










