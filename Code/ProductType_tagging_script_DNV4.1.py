import pandas as pd
import re
import os
import logging
import config

# Set up logging to track the tagging process
log_file_path = config.config["file_paths"]["log_file"]
logging.basicConfig(filename=log_file_path, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info("Starting the product type tagging process")

# Load file paths from config
gpac_master_path = config.config["file_paths"]["gpac_master"]
country_mapping_path = config.config["file_paths"]["country_mapping"]
input_data_path = config.config["file_paths"]["input_data"]
output_file_path = config.config["file_paths"]["output_file"]

# Validate input file paths
for path_name, path in config.config["file_paths"].items():
    if path_name not in ["output_file", "log_file"]:  # Skip validation for output and log files
        if not os.path.exists(path):
            logging.error(f"File not found: {path}")
            raise FileNotFoundError(f"File not found: {path}")
        logging.info(f"{path_name} path is valid: {path}")

# Load data files
try:
    gpac_master_df = pd.read_excel(gpac_master_path, sheet_name="Client_Product_Type Mapping")
    logging.info("GPAC Master file loaded successfully")
except Exception as e:
    logging.error(f"Failed to load GPAC Master file: {e}")
    raise

try:
    country_mapping_df = pd.read_csv(country_mapping_path)
    logging.info("Country mapping file loaded successfully")
except Exception as e:
    logging.error(f"Failed to load country mapping file: {e}")
    raise

try:
    input_data_df = pd.read_csv(input_data_path, low_memory=False)
    logging.info("Input data file loaded successfully")
except Exception as e:
    logging.error(f"Failed to load input data file: {e}")
    raise

# Initialize the Tagged columns with NaN values
input_data_df['Tagged_Level_1'] = pd.NA
input_data_df['Tagged_Level_2'] = pd.NA
input_data_df['Tagged_Level_3'] = pd.NA

# Helper function for pattern matching column groups
def match_pattern_based_columns(row, patterns):
    for pattern in patterns:
        matching_columns = [col for col in row.index if re.match(pattern, col)]
        for col in matching_columns:
            if pd.notnull(row[col]):
                return col
    return None

# Primary tagging function based on Client Product Type
def tag_by_client_product_type(row):
    if config.config["tagging_priority"]["client_product_type"]["enabled"]:
        column_name = config.config["tagging_priority"]["client_product_type"]["column_name"]
        if pd.notnull(row['Tagged_Level_1']) and pd.notnull(row['Tagged_Level_2']) and pd.notnull(row['Tagged_Level_3']):
            return row  # Skip if already tagged
        if column_name in row and pd.notnull(row[column_name]):
            code = row[column_name]
            match = gpac_master_df[gpac_master_df['Keyword'] == code]
            if not match.empty:
                row['Tagged_Level_1'] = match['GPAC_Product_Level1'].values[0]
                row['Tagged_Level_2'] = match['GPAC_Product_Level2'].values[0]
                row['Tagged_Level_3'] = match['GPAC_Product_Level_3'].values[0]
                logging.info(f"Row {row.name}: Tagged by Client Product Type using code '{code}'")
    return row

# Secondary tagging based on keyword, attribute, and country mapping
def tag_by_secondary_rules(row):
    if pd.notnull(row['Tagged_Level_1']) and pd.notnull(row['Tagged_Level_2']) and pd.notnull(row['Tagged_Level_3']):
        return row  # Skip if already tagged

    apply_order = config.config["tagging_priority"]["keyword_attribute_country_combination"]["apply_order"]

    # Keyword Matching
    if "keyword_matching" in apply_order:
        if 'Keyword' in gpac_master_df.columns:
            keywords = gpac_master_df['Keyword'].dropna().unique()
            for keyword in keywords:
                if any(keyword in str(value) for value in row):
                    row['Tagged_Level_1'] = gpac_master_df.loc[gpac_master_df['Keyword'] == keyword, 'GPAC_Product_Level1'].values[0]
                    row['Tagged_Level_2'] = gpac_master_df.loc[gpac_master_df['Keyword'] == keyword, 'GPAC_Product_Level2'].values[0]
                    row['Tagged_Level_3'] = gpac_master_df.loc[gpac_master_df['Keyword'] == keyword, 'GPAC_Product_Level_3'].values[0]
                    logging.info(f"Row {row.name}: Tagged by keyword matching '{keyword}'")
                    break

    # Attribute Mapping
    if "attribute_mapping" in apply_order and config.config["attribute_mapping"]["enabled"]:
        for field in config.config["attribute_mapping"]["fields"]:
            if pd.notnull(row['Tagged_Level_1']) and pd.notnull(row['Tagged_Level_2']) and pd.notnull(row['Tagged_Level_3']):
                return row  # Skip if already tagged
            if field in row and pd.notnull(row[field]):
                attribute_match = gpac_master_df[gpac_master_df['Attribute'] == row[field]]
                if not attribute_match.empty:
                    row['Tagged_Level_1'] = attribute_match['GPAC_Product_Level1'].values[0]
                    row['Tagged_Level_2'] = attribute_match['GPAC_Product_Level2'].values[0]
                    row['Tagged_Level_3'] = attribute_match['GPAC_Product_Level_3'].values[0]
                    logging.info(f"Row {row.name}: Tagged by attribute mapping '{field}'")
                    break

    # Country Mapping
    if "country_mapping" in apply_order:
        if pd.notnull(row['Tagged_Level_1']) and pd.notnull(row['Tagged_Level_2']) and pd.notnull(row['Tagged_Level_3']):
            return row  # Skip if already tagged
        if "Country" in row and pd.notnull(row["Country"]):
            country_match = country_mapping_df[country_mapping_df['Country'] == row["Country"]]
            if not country_match.empty:
                row['Tagged_Level_2'] = country_match['Asset_Class_Level2'].values[0]
                row['Tagged_Level_3'] = country_match['Asset_Class_Level3'].values[0]
                logging.info(f"Row {row.name}: Tagged by country mapping '{row['Country']}'")
    return row

# Apply tagging rules to input data
input_data_df = input_data_df.apply(tag_by_client_product_type, axis=1)
input_data_df = input_data_df.apply(tag_by_secondary_rules, axis=1)

# Save the tagged data
input_data_df.to_csv(output_file_path, index=False)
logging.info(f"Tagged data saved to {output_file_path}")
print(f"Tagged data saved to {output_file_path}")




