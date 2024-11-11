import pandas as pd
import yaml
import logging
import re

# === Load Configuration ===
with open('C:/Users/dhanv/OneDrive/Desktop/configV2.yaml', 'r') as config_file:
    config = yaml.safe_load(config_file)

# Configure logging
logging.basicConfig(filename=config['logging']['log_file'], 
                    level=getattr(logging, config['logging']['level'].upper()),
                    format='%(asctime)s - %(levelname)s - %(message)s')

# === Load Files with Error Handling ===
def load_data():
    """Load GPAC Master, Client Product Type Mapping, and Input Data with error handling."""
    try:
        gpac_master = pd.read_excel(config['file_paths']['gpac_master']['file'], sheet_name=config['file_paths']['gpac_master']['sheets']['product_mapping'])
        client_product_type_mapping = pd.read_excel(config['file_paths']['gpac_master']['file'], sheet_name=config['file_paths']['gpac_master']['sheets']['client_product_type_mapping'])
        input_data = pd.read_csv(config['file_paths']['input_data'])
        return gpac_master, client_product_type_mapping, input_data
    except FileNotFoundError as e:
        logging.error(f"File not found: {e}")
        raise
    except Exception as e:
        logging.error(f"Error loading files: {e}")
        raise

gpac_master, client_product_type_mapping, input_data = load_data()

# === CLIENT_PRODUCT_TYPE Tagging ===
def apply_client_product_type_tagging(row, client_product_type_mapping):
    """Tag based on CLIENT_PRODUCT_TYPE using the Client_Product_Type Mapping sheet."""
    try:
        client_product_type = row.get("CLIENT_PRODUCT_TYPE")
        logging.debug(f"Checking CLIENT_PRODUCT_TYPE: {client_product_type}")

        if pd.isna(client_product_type):
            return None

        matched = client_product_type_mapping[client_product_type_mapping['Keyword'] == client_product_type]
        
        if not matched.empty:
            logging.info(f"CLIENT_PRODUCT_TYPE matched for row {row.name} with Keyword {client_product_type}")
            return {
                'GPAC_Product_Level1': matched.iloc[0]['GPAC_Product_Level1'],
                'GPAC_Product_Level2': matched.iloc[0]['GPAC_Product_Level2'],
                'GPAC_Product_Level3': matched.iloc[0]['GPAC_Product_Level_3'],
                'Matched_Rule_ID': f"Client_Product_Type: {client_product_type}"
            }
        
        logging.debug(f"No match found for CLIENT_PRODUCT_TYPE: {client_product_type}")
        return None

    except Exception as e:
        logging.error(f"Error applying CLIENT_PRODUCT_TYPE tagging for row {row.name}: {e}")
        return None

# === Keyword Matching Tagging ===

stop_words = set(config['keyword_matching']['stop_words'])
frequency_threshold = config['keyword_matching']['frequency_threshold']

def clean_keywords(text):
    """Extracts keywords and phrases, removing stop words."""
    words = text.split(',')
    return [word.strip().lower() for word in words if word.strip().lower() not in stop_words]

def apply_keyword_matching(row, gpac_master):
    """Tag using keyword matching only."""
    try:
        for _, rule in gpac_master.iterrows():
            keywords = clean_keywords(rule.get("Keywords_Matched", ""))
            logging.debug(f"Checking keywords: {keywords} for row {row.name}")

            matched_phrases = [phrase for phrase in keywords if re.search(r'\b' + re.escape(phrase) + r'\b', str(row.values).lower())]
            
            if len(matched_phrases) >= frequency_threshold:
                logging.info(f"Phrase matched for row {row.name} with rule {rule['Rule_ID']}")
                rule_data = rule.to_dict()
                rule_data['Matched_Rule_ID'] = rule['Rule_ID']
                return rule_data  # Return matched rule data with Rule ID included

        return None  # No tag found
    except Exception as e:
        logging.error(f"Error in keyword matching for row {row.name}: {e}")
        return None

# === Main Tagging Function ===
def tag_assets(input_data, client_product_type_mapping, gpac_master):
    """Tag assets based on CLIENT_PRODUCT_TYPE and keyword matching only."""
    tagged_data = []

    for index, row in input_data.iterrows():
        tag = None

        # Step 1: Apply CLIENT_PRODUCT_TYPE tagging if present
        tag = apply_client_product_type_tagging(row, client_product_type_mapping)

        # If tagged, skip further tagging steps
        if tag:
            tagged_data.append({**row, **tag})
            continue

        # Step 2: Apply Keyword Matching if no match found in CLIENT_PRODUCT_TYPE
        tag = apply_keyword_matching(row, gpac_master)
        
        # If tagged, skip to next row
        if tag:
            tagged_data.append({**row, **tag})
            continue

        # Step 3: If no tag found after all steps, mark as unclassified
        tagged_data.append({**row, 'GPAC_Tag': 'Unclassified', 'Matched_Rule_ID': 'None'})
        logging.info(f"No tag found for row {row.name}. Marked as Unclassified.")

    return pd.DataFrame(tagged_data)

# === Run Tagging Process and Save Results with Error Handling ===
try:
    tagged_df = tag_assets(input_data, client_product_type_mapping, gpac_master)
    tagged_df.to_csv("tagged_output.csv", index=False)
    logging.info("Tagging completed successfully. Results saved to tagged_output.csv")
except Exception as e:
    logging.error(f"Tagging process failed: {e}")
