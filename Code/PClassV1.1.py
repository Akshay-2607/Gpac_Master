import pandas as pd
import config  # Import the config file with column priorities

rules_df = pd.read_csv(config.RULES_FILE)
input_df = pd.read_csv(config.INPUT_FILE)

# Get the column priorities from the config file
column_priorities = config.COLUMN_PRIORITIES
client_product_type_dict = config.CLIENT_PRODUCT_TYPE_DICT

# Function to create searchable text from prioritized columns dynamically
def create_searchable_text(row):
    # Combine all columns into one searchable text string
    searchable_text = " ".join(
        str(value).lower() for value in row if pd.notna(value)
    )
    print(f"Searchable Text for Row: {searchable_text}")  # Debug: Show combined text for each row
    return searchable_text


# Apply tagging rules to each row in the input data
def apply_tagging_rules(row):
    searchable_text = create_searchable_text(row)

    # Step 1: Check for any client product type in the searchable text
    for client_product_type, client_tags in client_product_type_dict.items():
        if client_product_type.lower() in searchable_text:
            print(f"Client product type match found: {client_product_type} with tags {client_tags}")
            # Apply client product type tags and override any other tags
            return {
                "GPAC_product_type_level_1": client_tags[0],
                "GPAC_product_type_level_2": client_tags[1],
                "GPAC_product_type_level_3": client_tags[2],
            }

    # Step 2: Apply primary tagging from Dynamic Master Rules Engine only if no client product type is found
    for _, rule in rules_df.iterrows():
        keywords = rule["Keywords"]

        if isinstance(keywords, str):
            keywords_list = [keyword.strip().lower() for keyword in keywords.split(",")]
            print(f"Keywords List: {keywords_list}")  # Debug: Show keywords being checked

            if any(keyword in searchable_text for keyword in keywords_list):
                print(f"Primary tag found for keywords '{keywords_list}' in text: {searchable_text}")

                # Apply tags based on the first matching keyword rule
                return {
                    "GPAC_product_type_level_1": rule["GPAC_Product_Level1"],
                    "GPAC_product_type_level_2": rule["GPAC_Product_Level2"],
                    "GPAC_product_type_level_3": rule["GPAC_Product_Level3"],
                }

    # Return None if no tags were applied
    return {
        "GPAC_product_type_level_1": None,
        "GPAC_product_type_level_2": None,
        "GPAC_product_type_level_3": None,
    }


# Apply tagging to each row in the input DataFrame and create new columns for tags
tagged_data = input_df.apply(apply_tagging_rules, axis=1, result_type="expand")
input_df = pd.concat([input_df, tagged_data], axis=1)

# Count the number of rows that were successfully tagged
tagged_count = tagged_data.dropna(how="all").shape[0]
print(f"Total rows tagged: {tagged_count} out of {len(input_df)}")

# Save the tagged data to a new file
output_file = "/Users/dnamas5/Downloads/0411V3.3_Tagged_PClass.csv"
log_file = output_file.rsplit(".", 1)[0] + ".log"
input_df.to_csv(output_file, index=False)
input_df.to_csv(log_file, index=False)

print(f"Tagging completed. Output saved to {output_file}")



