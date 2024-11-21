import os 
import re
from natsort import natsorted


"""Group chunks' information together from a recording file and return them 
   as a list of tuples"""
def parse_chunk_paths(experiment_path: str) -> list:
    # Define a container for the sorted chunks 
    sorted_chunks: list = []

    # Find all of the names in the experiment path 
    experiment_files: list = os.listdir(experiment_path)

    # Find all of the bursts in sorted order
    burst_names: list = natsorted(set([re.search(r'burst\d+', file).group() 
                                      for file in experiment_files
                                      if 'burst' in file]))

    # Iterate over the burst names and build the filepaths
    # all of a given burst's readings
    for burst_idx, burst_name in enumerate(burst_names):
        # Initialize an empty dictionary for all sensors
        chunk_dict: dict = {name: [] 
                           for name in ('MS', 'Pupil', 'World', 'Sunglasses')}
        
        # Find all of the files of this burst
        burst_files: list = (os.path.join(experiment_path, file)
                             for file in experiment_files
                             if f'_{burst_name}_' in file)
        
        # Next, we will assign the files to their respective sensors
        for file in burst_files:
            # Append world sensor files to that category 
            if('world' in os.path.basename(file).lower()):
                chunk_dict['World'].append(file)
            
            # Append MS sensor files to that category
            elif('ms_readings' in os.path.basename(file).lower()):
                chunk_dict['MS'].append(file)
            
            # Append pupil sensor files to that category
            elif('pupil' in os.path.basename(file).lower()):
                chunk_dict['Pupil'].append(file)
            
            # THE .TXT HERE IS A KLUDGE. I FORGOT TO PUT SUNGLASSES
            # IN SOME FILENAMES FOR TESTING. IN THE FUTURE 
            # THE SUNGLASSES WILL BE ALL THAT IS NEEDED
            # Append sunglasses sensor files to that category
            elif('sunglasses' in os.path.basename(file).lower() 
                 or '.txt' in os.path.basename(file).lower()):
                 chunk_dict['Sunglasses'].append(file)

        # Go over all of the keys and values and sort the values 
        # so keys with multiple values always have their 
        # values show up in the same order 
        for key, val in chunk_dict.items(): 
            chunk_dict[key].sort()

        # Append this chunks' readings to the growing list
        sorted_chunks.append(chunk_dict)

    return sorted_chunks

def main():
    pass  

if(__name__ == '__main__'):
    pass