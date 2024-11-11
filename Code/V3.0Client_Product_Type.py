import pandas as pd
import yaml
import logging
import re

# === Load Configuration ===
with open('config.yml', 'r') as config_file:
    config = yaml.safe_load(config_file)

# Configure logging
logging.basicConfig(filename=config['logging']['log_file'], 
                    level=getattr(logging, config['logging']['level'].upper()),
                    format='%(asctime)s - %(levelname)s - %(message)s')

# === Load Files with Error Handling ===
def load_data():
    """Load GPAC Master, Country Mapping, and Input Data with error handling."""
    try:
        gpac_master = pd.read_csv(config['file_paths']['gpac_master'])
        country_mapping = pd.read_csv(config['file_paths']['country_mapping'])
        input_data = pd.read_csv(config['file_paths']['input_data'])
        return gpac_master, country_mapping, input_data
    except FileNotFoundError as e:
        logging.error(f"File not found: {e}")
        raise
    except Exception as e:
        logging.error(f"Error loading files: {e}")
        raise

gpac_master, country_mapping, input_data = load_data()

# === Keyword and Phrase Matching ===

stop_words = set(config['keyword_matching']['stop_words'])
frequency_threshold = config['keyword_matching']['frequency_threshold']

def clean_keywords(text):
    """Extracts keywords and phrases, removing stop words."""
    words = text.split(',')
    return [word.strip().lower() for word in words if word.strip().lower() not in stop_words]

def apply_client_product_code_tagging(row, gpac_master):
    """Tag based on Client Product Code if available, prioritizing this tagging step."""
    try:
        client_code = row.get(config['tagging_priority']['client_product_code']['column_name'])
        if pd.isna(client_code):
            return None  # No product code found, move to next tagging step
        
        matched = gpac_master[gpac_master['Client_product_code'] == client_code]
        if not matched.empty:
            logging.info(f"Client Product Code matched for row {row.name} with rule {matched.iloc[0]['Rule_ID']}")
            return matched.iloc[0].to_dict()  # Return the first matched rule as a dictionary
        return None
    except Exception as e:
        logging.error(f"Error applying Client Product Code tagging for row {row.name}: {e}")
        return None

def apply_keyword_attribute_country_combination(row, gpac_master, country_mapping):
    """Tag using keyword phrases, attribute mapping, and country mapping."""
    
    try:
        # === Step 1: Keyword Phrase Matching ===
        for _, rule in gpac_master.iterrows():
            keywords = clean_keywords(rule.get("Keywords_Matched", ""))
            matched_phrases = [phrase for phrase in keywords if re.search(r'\b' + re.escape(phrase) + r'\b', str(row.values).lower())]
            
            if len(matched_phrases) >= frequency_threshold:
                logging.info(f"Phrase matched for row {row.name} with rule {rule['Rule_ID']}")
                rule_data = rule.to_dict()
                rule_data['Matched_Rule_ID'] = rule['Rule_ID']
                return rule_data  # Return matched rule data with Rule ID included

        # === Step 2: Attribute Mapping ===
        for field in config['attribute_mapping']['fields']:
            if field in row:
                value = row.get(field)
                matched = gpac_master[gpac_master[field] == value]
                if not matched.empty:
                    logging.info(f"Attribute matched for row {row.name} with rule {matched.iloc[0]['Rule_ID']}")
                    rule_data = matched.iloc[0].to_dict()
                    rule_data['Matched_Rule_ID'] = matched.iloc[0]['Rule_ID']
                    return rule_data  # Return matched rule with Rule ID
        
        # === Step 3: Country Mapping ===
        if config['country_mapping']['enabled']:
            issue_country = row.get("ISSUE_COUNTRY")
            if issue_country and issue_country in country_mapping['Country'].values:
                country_data = country_mapping[country_mapping['Country'] == issue_country].iloc[0]
                for level in ['Market Classification', 'Islamic Compliance', 'Asset Region']:
                    if country_data.get(level) and country_data[level] in row.values:
                        logging.info(f"Country mapping matched for row {row.name} with rule {level}")
                        country_data_dict = country_data.to_dict()
                        country_data_dict['Matched_Rule_ID'] = level
                        return country_data_dict  # Return matched country data with level as Rule ID

        return None  # No tag found
    except Exception as e:
        logging.error(f"Error in keyword-attribute-country tagging for row {row.name}: {e}")
        return None

# === Main Tagging Function ===
def tag_assets(input_data, gpac_master, country_mapping):
    """Tag assets based on Client Product Code, Keywords, Attributes, and Country Mapping with logging."""
    tagged_data = []

    for index, row in input_data.iterrows():
        tag = None
        # Step 1: Apply Client Product Code tagging if enabled
        if config['tagging_priority']['client_product_code']['enabled']:
            tag = apply_client_product_code_tagging(row, gpac_master)

        # Step 2: Apply Keyword and Attribute-Country Combination if no match found in Client Product Code
        if tag is None and config['tagging_priority']['keyword_attribute_country_combination']['enabled']:
            tag = apply_keyword_attribute_country_combination(row, gpac_master, country_mapping)

        # Step 3: Append tag or mark as unclassified
        if tag:
            tagged_data.append({**row, **tag, 'Matched_Rule_ID': tag.get('Matched_Rule_ID', 'N/A')})  # Append Rule ID
        else:
            tagged_data.append({**row, 'GPAC_Tag': 'Unclassified', 'Matched_Rule_ID': 'None'})
            logging.info(f"No tag found for row {row.name}. Marked as Unclassified.")

    return pd.DataFrame(tagged_data)

# === Run Tagging Process and Save Results with Error Handling ===
try:
    tagged_df = tag_assets(input_data, gpac_master, country_mapping)
    tagged_df.to_csv("tagged_output.csv", index=False)
    logging.info("Tagging completed successfully. Results saved to tagged_output.csv")
except Exception as e:
    logging.error(f"Tagging process failed: {e}")
