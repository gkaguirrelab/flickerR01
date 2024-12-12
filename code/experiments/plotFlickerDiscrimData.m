
close all

subjectID = 'PILT_0003';
flickerFreqSetHz = [24,12,6,3,1.5];

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

slopeVals = [];
slopeValCI = [];

% Set up a figure
figHandle = figure();
figuresize(750,250,'units','pt');
tiledlayout(1,5,"TileSpacing","compact",'Padding','tight');

for ii = 1:length(modDirections)
    for rr = 1:length(flickerFreqSetHz)

        dataDir = fullfile(subjectDir,[modDirections{ii} '_ND' NDlabelsAll{1}],experimentName);

        % Load the low-side measurements
        psychFileStem = [subjectID '_' modDirections{ii} ...
                         '_' experimentName '_' ...
                 strrep(num2str(targetPhotoreceptorContrast(ii)),'.','x') ...
                '_refFreq-' num2str(flickerFreqSetHz(rr)) 'Hz' ...
                 '_' stimParamLabels{1}];
        filename = fullfile(dataDir,psychFileStem);
        load(filename,'psychObj');

        % Store some of these parameters
        questData = psychObj.questData;
        stimParamsDomainList = psychObj.stimParamsDomainList;
        psiParamsDomainList = psychObj.psiParamsDomainList;

        % Load the high side measurements
         psychFileStem = [subjectID '_' modDirections{ii} ...
                         '_' experimentName '_' ...
                 strrep(num2str(targetPhotoreceptorContrast(ii)),'.','x') ...
                '_refFreq-' num2str(flickerFreqSetHz(rr)) 'Hz' ...
                 '_' stimParamLabels{2}];
        filename = fullfile(dataDir,psychFileStem);
        load(filename,'psychObj');

        % Combine the two measurement sets
        questData.trialData = [questData.trialData; psychObj.questData.trialData];
        stimParamsDomainList = unique([stimParamsDomainList, psychObj.stimParamsDomainList]);
        nTrials = length(psychObj.questData.trialData);

        % Get the Max Likelihood psi params, temporarily turning off verbosity.
        lb = cellfun(@(x) min(x),psychObj.psiParamsDomainList);
        ub = cellfun(@(x) max(x),psychObj.psiParamsDomainList);
        storeVerbose = psychObj.verbose;
        psychObj.verbose = false;
        [~, psiParamsFit] = psychObj.reportParams('lb',lb,'ub',ub);
        psychObj.verbose = storeVerbose;

        % Now the proportion correct for each stimulus type, and the psychometric
        % function fit. Marker transparancy (and size) visualizes number of trials
        % (more opaque -> more trials), while marker color visualizes percent
        % correct (more red -> more correct).
        nexttile
        hold on

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

        % Add the psychometric function
        for cc = 1:length(stimParamsDomainList)
            outcomes = obj.questData.qpPF(stimParamsDomainList(cc),psiParamsFit);
            fitCorrect(cc) = outcomes(2);
        end
        plot(stimParamsDomainList,fitCorrect,'-k')

        % Add a marker for the 50% point
        outcomes = obj.questData.qpPF(psiParamsFit(1),psiParamsFit);
        plot([psiParamsFit(1), psiParamsFit(1)],[0, outcomes(2)],':k')
        plot([min(stimParamsDomainList), psiParamsFit(1)],[0.5 0.5],':k')

        % Labels and range
        xlim([-1.5 1.5]);
        ylim([-0.1 1.1]);
        if rr == 5
            xlabel('stimulus difference [dB]')
        end
        if rr == 3
            ylabel('proportion pick test as faster');
        end

        % Add a title
        % str = sprintf('%2.1f PSI',psychObj.refPuffPSI);
        % title(str);
        % box off

        % Store the slope of the psychometric function
        slopeVals(rr) = normpdf(0,psiParamsFit(1),psiParamsFit(2));
        slopeValCI(rr,1) = normpdf(0,psiParamsCI(1,1),psiParamsCI(1,2));
        slopeValCI(rr,2) = normpdf(0,psiParamsCI(2,1),psiParamsCI(2,2));

    end
end

figure
figuresize(250,250,'units','pt');

yvals = [mean(slopeVals(3:4)) mean(slopeVals(3:4)) mean(slopeVals([4 6])) mean(slopeVals(6:7)) mean(slopeVals(6:7))];
semilogx(flickerFreqSetHz(3:7),yvals,'-k');
hold on
for rr = 3:length(flickerFreqSetHz)
    semilogx([flickerFreqSetHz(rr) flickerFreqSetHz(rr)],...
        slopeValCI(rr,:),'-k' );
    hold on
    semilogx(flickerFreqSetHz(rr),slopeVals(rr),'or','MarkerSize',15);

end

ylim([0,1.5]);
ylabel('discrimination slope [% response / dB]');
a = gca();
a.XTick = flickerFreqSetHz(3:end);
a.XTickLabel = {'4.5','6.6','9.7','14.1','20.6'};
xlim([3.7,24.9]);
xlabel('Reference stimulus intensity [PSI]')
box off
