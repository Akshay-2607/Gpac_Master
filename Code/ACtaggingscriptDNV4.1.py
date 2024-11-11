import pandas as pd
import config
import os
import logging

# Set up logging to track the output file's tagging details
log_file_path = config.config["file_paths"]["log_file"]
logging.basicConfig(filename=log_file_path, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

logging.info("Starting GPAC tagging process")

# Load file paths from config
gpac_master_path = config.config["file_paths"]["gpac_master"]
country_mapping_path = config.config["file_paths"]["country_mapping"]
input_data_path = config.config["file_paths"]["input_data"]

# Validate file paths
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

# Primary tagging function based on Client Asset Class
def tag_by_client_asset_class(row):
    if config.config["tagging_priority"]["client_asset_class"]["enabled"]:
        column_name = config.config["tagging_priority"]["client_asset_class"]["column_name"]
        if pd.notnull(row['Tagged_Level_1']) and pd.notnull(row['Tagged_Level_2']) and pd.notnull(row['Tagged_Level_3']):
            return row  # Skip if already tagged
        if column_name in row and pd.notnull(row[column_name]):
            code = row[column_name]
            match = gpac_master_df[gpac_master_df['Keyword'] == code]
            if not match.empty:
                row['Tagged_Level_1'] = match['GPAC_Product_Level1'].values[0]
                row['Tagged_Level_2'] = match['GPAC_Product_Level2'].values[0]
                row['Tagged_Level_3'] = match['GPAC_Product_Level_3'].values[0]
                logging.info(f"Row {row.name}: Tagged by Client Asset Class using code '{code}' - Levels: {row['Tagged_Level_1']}, {row['Tagged_Level_2']}, {row['Tagged_Level_3']}")
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
                    logging.info(f"Row {row.name}: Tagged by keyword matching '{keyword}' - Levels: {row['Tagged_Level_1']}, {row['Tagged_Level_2']}, {row['Tagged_Level_3']}")
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
                    logging.info(f"Row {row.name}: Tagged by attribute mapping '{field}' - Levels: {row['Tagged_Level_1']}, {row['Tagged_Level_2']}, {row['Tagged_Level_3']}")
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
                logging.info(f"Row {row.name}: Tagged by country mapping '{row['Country']}' - Levels: {row['Tagged_Level_2']}, {row['Tagged_Level_3']}")

    return row

# Apply tagging rules to input data
input_data_df = input_data_df.apply(tag_by_client_asset_class, axis=1)
input_data_df = input_data_df.apply(tag_by_secondary_rules, axis=1)

# Save the tagged data
output_path = config.config["file_paths"]["output_file"]
input_data_df.to_csv(output_path, index=False)
logging.info(f"Tagged data saved to {output_path}")
print(f"Tagged data saved to {output_path}")
