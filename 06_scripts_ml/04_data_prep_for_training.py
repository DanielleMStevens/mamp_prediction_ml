#-----------------------------------------------------------------------------------------------
# Krasileva Lab - Plant & Microbial Biology Department UC Berkeley
# Author: Danielle M. Stevens
# Last Updated: 07/06/2020
# Script Purpose: 
# Inputs: 
# Outputs: 
#-----------------------------------------------------------------------------------------------
"""
Data preparation script for MAMP prediction model.

This script processes and prepares data for training a MAMP (Microbe-Associated Molecular Pattern) 
prediction model by:
1. Loading and processing MAMP prediction data from Excel files
2. Loading and parsing receptor ectodomain sequences from FASTA files
3. Combining the data and creating stratified train/test splits

Input Files Required:
- All_LRR_PRR_ligand_data.xlsx: Contains MAMP-receptor interaction data
- lrr_domain_sequences.fasta: Contains receptor protein sequences in FASTA format

Output:
- Generates train and test CSV files with processed data for model training
"""

import pandas as pd
import argparse
from pathlib import Path
from sklearn.model_selection import train_test_split
from typing import Dict, Tuple, List
import numpy as np


########################################################################################
# Parse a FASTA format file into a dictionary of sequences.
# Returns: Dict[str, str]: Dictionary mapping sequence headers to their corresponding sequences
# Note: Expected FASTA header format: >species|locus_id|receptor
########################################################################################

def parse_fasta(fasta_path: Path) -> Dict[str, str]:
    sequences = {}
    current_header = None
    current_sequence = []
    
    with open(fasta_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            # Handle FASTA header lines (starting with '>')
            if line.startswith('>'):
                # Save the previous sequence if it exists
                if current_header:
                    sequences[current_header] = ''.join(current_sequence)
                #print(current_header)
                
                # Parse the new header
                header = line[1:]  # Remove '>' character
                parts = header.split('|')
                if len(parts) >= 3:
                    # Standard format: species|locus_id|receptor
                    species = parts[0]
                    locus_id = parts[1]
                    receptor = parts[2]
                    current_header = f"{species}|{locus_id}|{receptor}"
                else:
                    # Fallback for non-standard headers
                    current_header = header
                
                current_sequence = []
            else:
                # Accumulate sequence lines
                current_sequence.append(line)
                
    # Save the last sequence
    if current_header:
        sequences[current_header] = ''.join(current_sequence)
    #print(sequences)
    return sequences


########################################################################################
# Load receptor protein sequences from the FASTA file
# Returns: Dict[str, str]: Dictionary mapping receptor identifiers to their sequences
# Raises: FileNotFoundError: If the FASTA file is not found at the expected location
########################################################################################

def load_receptor_sequences(in_data_dir: Path) -> Dict[str, str]:
    fasta_path = in_data_dir.parent / "03_out_data" / "lrr_domain_sequences.fasta"
    if not fasta_path.exists():
        raise FileNotFoundError(f"Could not find receptor sequence file at {fasta_path}")
        
    return parse_fasta(fasta_path)


########################################################################################
# Process and combine MAMP prediction data from Excel and FASTA files.
# Returns: pd.DataFrame: Processed dataframe containing combined receptor-ligand data
# Raises: FileNotFoundError: If required Excel file is not found
########################################################################################

def process_data(in_data_dir: Path, use_legacy_columns: bool = True) -> pd.DataFrame:

# Load Excel data
    excel_path = in_data_dir / "All_LRR_PRR_ligand_data.xlsx"
    if not excel_path.exists():
        raise FileNotFoundError(f"Could not find Excel data file at {excel_path}")
    data_df = pd.read_excel(excel_path)

    # Select required columns and create a copy
    required_columns = ["Plant species", "Receptor", "Locus ID/Genbank", "Ligand", "Ligand Sequence", "Immunogenicity"]
    receptor_ligand_pairs = data_df[required_columns]

    # Create standardized receptor identifiers (used for mapping)
    original_receptor_names = receptor_ligand_pairs.apply(
        lambda x: f"{x['Plant species'].replace(' ', '_')}|{x['Locus ID/Genbank']}|{x['Receptor']}",
        axis=1
    )


    # Load receptor sequences
    receptor_ligand_pairs['Header_Name'] = original_receptor_names
    receptor_name_to_seq = load_receptor_sequences(in_data_dir)
    receptor_ligand_pairs['Receptor Sequence'] = original_receptor_names.map(receptor_name_to_seq)
    receptor_ligand_pairs = receptor_ligand_pairs.dropna(subset=['Receptor Sequence'])
    print(receptor_ligand_pairs)

    # Log missing sequences
    missing_sequences = receptor_ligand_pairs['Receptor Sequence'].isna().sum()
    if missing_sequences > 0:
        print(f"\nWARNING: Found {missing_sequences} rows with missing receptor sequences after mapping.")
        print("\nMissing sequences for the following Header_Names:")
        missing_headers = receptor_ligand_pairs[receptor_ligand_pairs['Receptor Sequence'].isna()]['Header_Name']
        for header in missing_headers:
            print(f"- {header}")
        # Optionally filter out missing sequences if needed:
        # receptor_ligand_pairs = receptor_ligand_pairs.dropna(subset=['Receptor Sequence'])
        # print(f"Retained {len(receptor_ligand_pairs)} rows after filtering.")


    # Handle legacy column names if needed
    if use_legacy_columns:
        column_mapping = {
            'Ligand': 'Epitope',
            'Ligand Sequence': 'Sequence',
            'Immunogenicity': 'Known Outcome'
        }
    receptor_ligand_pairs = receptor_ligand_pairs.rename(columns=column_mapping)
    
    return receptor_ligand_pairs

########################################################################################
# Create a stratified train/test split
# Returns: Tuple[pd.DataFrame, pd.DataFrame]: Training and test dataframes
# Note: Attempts stratified split based on 'Known Outcome' column
# Note: Uses 80/20 train/test split ratio
########################################################################################

# we can use sklearn.model_selection.train_test_split to split the data -> ex. stratify 
def stratified_split(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    train_df, test_df = train_test_split(
            df, 
            test_size=0.2, 
            random_state=123,
            stratify=df['Known Outcome']
    )
    return train_df, test_df


def split_randomly(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    # First split the original unshuffled data
    train_df, test_df = train_test_split(df, test_size=0.2, random_state=42)
    
    # Create shuffled version of training data only
    train_df_shuffled = train_df.copy()
    
    # Shuffle epitope columns within training set only
    shuffled_indices = np.random.RandomState(42).permutation(len(train_df))
    epitope_cols = ['Epitope', 'Sequence', 'Known Outcome'] 
    for col in epitope_cols:
        train_df_shuffled[col] = train_df[col].values[shuffled_indices]
    
    return train_df_shuffled, test_df



# -----------------------------------------------------------------------------------------------
def get_args_parser():
    parser = argparse.ArgumentParser("Data preparation for MAMP prediction model")
    parser.add_argument("--split_type", type=str, help="seq_stratify|immuno_stratify|random")
    return parser


def main(args):
    """
    Main execution function that orchestrates the data preparation process.
    
    Steps:
    1. Set up input/output paths
    2. Process raw data from Excel and FASTA files
    3. Create train/test splits
    4. Save processed datasets
    5. Print dataset statistics
    """
    # Setup paths
    base_dir = Path(__file__).parent.parent
    in_data_dir = base_dir / "02_in_data"
    out_dir = base_dir / "05_datasets" 
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Process data and create splits
    receptor_ligand_pairs = process_data(in_data_dir, use_legacy_columns=True)
    if args.split_type == "seq_stratify":
        train_df, test_df = stratified_split(receptor_ligand_pairs)
    if args.split_type == "immuno_stratify":
        train_df, test_df = stratified_split(receptor_ligand_pairs)
    elif args.split_type == "random":
        train_df, test_df = split_randomly(receptor_ligand_pairs)
    else:
        raise ValueError("Please specify a valid split type: 'immuno_stratify' or 'random'. "
                        "Example: python 04_data_prep_for_training.py --split_type immuno_stratify"
                        "Stratified split preserves class distribution between train/test sets. "
                        "Random split performs standard random splitting.")
    
    # Save processed datasets
    train_df.to_csv(out_dir / f"train_{args.split_type}.csv", index=False)
    test_df.to_csv(out_dir / f"test_{args.split_type}.csv", index=False)
    
    # Print statistics
    print("\nDataset statistics:")
    print(f"Total samples: {len(receptor_ligand_pairs)}")
    print(f"Training samples: {len(train_df)}")
    print(f"Test samples: {len(test_df)}")
    print("\nClass distribution:")
    print("Training set:")
    print(train_df.groupby(['Known Outcome']).size())
    print("\nTest set:")
    print(test_df.groupby(['Known Outcome']).size())

if __name__ == "__main__":
    args = get_args_parser()
    args = args.parse_args()
    main(args) 

