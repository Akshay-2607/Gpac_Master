import pandas as pd
import config
import os

# Load file paths from config
gpac_master_path = config.config["file_paths"]["gpac_master"]
country_mapping_path = config.config["file_paths"]["country_mapping"]
input_data_path = config.config["file_paths"]["input_data"]

# Validate file paths
for path_name, path in config.config["file_paths"].items():
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    print(f"{path_name} path is valid: {path}")

# Load data files
gpac_master_df = pd.read_excel(gpac_master_path)
country_mapping_df = pd.read_csv(country_mapping_path)
input_data_df = pd.read_csv(input_data_path)

# Initialize the Tagged columns with NaN values
input_data_df['Tagged_Level_1'] = pd.NA
input_data_df['Tagged_Level_2'] = pd.NA
input_data_df['Tagged_Level_3'] = pd.NA


# Primary tagging function based on Client Product Code
def tag_by_client_product_code(row):
    if config.config["tagging_priority"]["client_product_code"]["enabled"]:
        column_name = config.config["tagging_priority"]["client_product_code"]["column_name"]
        if column_name in row and pd.notnull(row[column_name]):
            code = row[column_name]
            # Match code in gpac_master_df
            match = gpac_master_df[gpac_master_df['Client_Product_Code'] == code]
            if not match.empty:
                row['Tagged_Level_1'] = match['GPAC_Product_Level1'].values[0]
                row['Tagged_Level_2'] = match['GPAC_Product_Level2'].values[0]
                row['Tagged_Level_3'] = match['GPAC_Product_Level3'].values[0]
    return row


# Secondary tagging based on keyword, attribute, and country mapping
def tag_by_secondary_rules(row):
    apply_order = config.config["tagging_priority"]["keyword_attribute_country_combination"]["apply_order"]

    # Keyword Matching
    if "keyword_matching" in apply_order:
        if config.config["keyword_matching"]["frequency_threshold"]:
            keywords = gpac_master_df['Keywords_Matched'].dropna().unique()
            for keyword in keywords:
                if any(keyword in str(value) for value in row):
                    row['Tagged_Level_1'] = \
                    gpac_master_df.loc[gpac_master_df['Keywords_Matched'] == keyword, 'GPAC_Product_Level1'].values[0]
                    row['Tagged_Level_2'] = \
                    gpac_master_df.loc[gpac_master_df['Keywords_Matched'] == keyword, 'GPAC_Product_Level2'].values[0]
                    row['Tagged_Level_3'] = \
                    gpac_master_df.loc[gpac_master_df['Keywords_Matched'] == keyword, 'GPAC_Product_Level3'].values[0]
                    break

    # Attribute Mapping
    if "attribute_mapping" in apply_order and config.config["attribute_mapping"]["enabled"]:
        for field in config.config["attribute_mapping"]["fields"]:
            if field in row and pd.notnull(row[field]):
                attribute_match = gpac_master_df[gpac_master_df['Attribute'] == row[field]]
                if not attribute_match.empty:
                    row['Tagged_Level_1'] = attribute_match['GPAC_Product_Level1'].values[0]
                    row['Tagged_Level_2'] = attribute_match['GPAC_Product_Level2'].values[0]
                    row['Tagged_Level_3'] = attribute_match['GPAC_Product_Level3'].values[0]
                    break

    # Country Mapping
    if "country_mapping" in apply_order:
        if "Country" in row and pd.notnull(row["Country"]):
            country_match = country_mapping_df[country_mapping_df['Country'] == row["Country"]]
            if not country_match.empty:
                row['Tagged_Level_2'] = country_match['Asset_Class_Level2'].values[0]
                row['Tagged_Level_3'] = country_match['Asset_Class_Level3'].values[0]

    return row


# Apply tagging rules to input data
input_data_df = input_data_df.apply(tag_by_client_product_code, axis=1)
input_data_df = input_data_df.apply(tag_by_secondary_rules, axis=1)

# Save the tagged data
output_path = "/Users/dnamas5/Downloads/Tagged_Output.csv"
input_data_df.to_csv(output_path, index=False)
print(f"Tagged data saved to {output_path}")
