import pandas as pd
import yaml
import logging
import re

# === Load Configuration ===
with open('C:/Users/dhanv/OneDrive/Desktop/ACconfigV1.yaml', 'r') as config_file:
    config = yaml.safe_load(config_file)

# Configure logging to output to both a file and the console
log_file = config['logging']['log_file']
log_level = getattr(logging, config['logging']['level'].upper())

# Create a custom logger
logger = logging.getLogger()
logger.setLevel(log_level)

# File handler for logging to a file
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(log_level)

# Stream handler for logging to the console
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)

# Define a logging format
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Initial log to confirm script start
logger.info("ACtaggingscriptV1.py has started running.")

# === Load Files with Error Handling ===
def load_data():
    """Load GPAC Master, Client Asset Class Mapping, and Input Data with error handling."""
    try:
        gpac_master = pd.read_excel(config['file_paths']['gpac_master']['file'], sheet_name=config['file_paths']['gpac_master']['sheets']['asset_class_mapping'])
        client_asset_class_mapping = pd.read_excel(config['file_paths']['gpac_master']['file'], sheet_name=config['file_paths']['gpac_master']['sheets']['client_asset_class_mapping'])
        input_data = pd.read_csv(config['file_paths']['input_data'], low_memory=False)
        logger.info("Data loaded successfully")
        return gpac_master, client_asset_class_mapping, input_data
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading files: {e}")
        raise

gpac_master, client_asset_class_mapping, input_data = load_data()

# === CLIENT_ASSET_CLASS Tagging ===
def apply_client_asset_class_tagging(row, client_asset_class_mapping):
    """Tag based on CLIENT_ASSET_CLASS using the Client_Asset_Class Mapping sheet."""
    try:
        client_asset_class = row.get(config['tagging_priority']['client_product_code']['column_name'])
        logger.debug(f"Checking CLIENT_ASSET_CLASS: {client_asset_class}")

        if pd.isna(client_asset_class):
            return None

        matched = client_asset_class_mapping[client_asset_class_mapping['Keyword'] == client_asset_class]
        
        if not matched.empty:
            logger.info(f"CLIENT_ASSET_CLASS matched for row {row.name} with Keyword {client_asset_class}")
            return {
                'GPAC_Asset_Class_Level1': matched.iloc[0]['GPAC_Asset_Class_Level1'],
                'GPAC_Asset_Class_Level2': matched.iloc[0]['GPAC_Asset_Class_Level2'],
                'GPAC_Asset_Class_Level3': matched.iloc[0]['GPAC_Asset_Class_Level3'],
                'Matched_Rule_ID': f"Client_Asset_Class: {client_asset_class}"
            }
        
        logger.debug(f"No match found for CLIENT_ASSET_CLASS: {client_asset_class}")
        return None

    except Exception as e:
        logger.error(f"Error applying CLIENT_ASSET_CLASS tagging for row {row.name}: {e}")
        return None

# === Keyword Matching Tagging ===

stop_words = set(config['keyword_matching']['stop_words'])
frequency_threshold = config['keyword_matching']['frequency_threshold']

def clean_keywords(text):
    """Extracts keywords and phrases, removing stop words, and handles non-string input."""
    if not isinstance(text, str):
        return []
    words = text.split(',')
    return [word.strip().lower() for word in words if word.strip().lower() not in stop_words]

def apply_keyword_matching(row, gpac_master):
    """Tag using keyword matching only."""
    try:
        # Join only primary columns for row text to reduce matching load
        row_text = ' '.join([str(row[col]) for col in config['column_priority']['primary_columns'] if col in row.index]).lower()
        logger.debug(f"Row text for keyword matching: {row_text}")

        for _, rule in gpac_master.iterrows():
            keywords = clean_keywords(rule.get("Keywords_Matched", ""))
            logger.debug(f"Checking keywords: {keywords} for row {row.name}")

            matched_phrases = [phrase for phrase in keywords if re.search(r'\b' + re.escape(phrase) + r'\b', row_text)]
            
            if len(matched_phrases) >= frequency_threshold:
                logger.info(f"Phrase matched for row {row.name} with rule {rule['Rule_ID']}")
                rule_data = rule.to_dict()
                rule_data['Matched_Rule_ID'] = rule['Rule_ID']
                return rule_data  # Return matched rule data with Rule ID included

        return None  # No tag found
    except Exception as e:
        logger.error(f"Error in keyword matching for row {row.name}: {e}")
        return None

# === Main Tagging Function ===
def tag_assets(input_data, client_asset_class_mapping, gpac_master):
    """Tag assets based on CLIENT_ASSET_CLASS and keyword matching only."""
    tagged_data = []

    for index, row in input_data.iterrows():
        tag = None

        # Step 1: Apply CLIENT_ASSET_CLASS tagging if present
        tag = apply_client_asset_class_tagging(row, client_asset_class_mapping)

        # If tagged, skip further tagging steps
        if tag:
            tagged_data.append({**row, **tag})
            continue

        # Step 2: Apply Keyword Matching if no match found in CLIENT_ASSET_CLASS
        tag = apply_keyword_matching(row, gpac_master)
        
        # If tagged, skip to next row
        if tag:
            tagged_data.append({**row, **tag})
            continue

        # Step 3: If no tag found after all steps, mark as unclassified
        tagged_data.append({**row, 'GPAC_Tag': 'Unclassified', 'Matched_Rule_ID': 'None'})
        logger.info(f"No tag found for row {row.name}. Marked as Unclassified.")

    return pd.DataFrame(tagged_data)

# === Run Tagging Process and Save Results with Error Handling ===
try:
    tagged_df = tag_assets(input_data, client_asset_class_mapping, gpac_master)
    
    # Updated to specify the absolute path to your Desktop and add logging
    logger.info("Attempting to save the output file to Desktop...")
    tagged_df.to_csv("C:/Users/dhanv/OneDrive/Desktop/tagged_output_OLDGPAC.csv", index=False)
    logger.info("Output file saved successfully as tagged_output.csv on Desktop.")
    
    logger.info("Script execution completed successfully.")
except Exception as e:
    logger.error(f"Tagging process failed: {e}")