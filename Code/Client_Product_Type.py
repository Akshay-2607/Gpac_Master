import pandas as pd

# Load the main data file
file_path = "/Users/dnamas5/Downloads/ITE=WARRANT.csv"
df = pd.read_csv(file_path)

# Load the mapping file
mapping_file_path = "/Users/dnamas5/Downloads/GPAC Master V5 - Client_Product_Type Mapping.csv"
mapping_df = pd.read_csv(mapping_file_path)

# Dynamically create a mapping dictionary based on keywords found in the mapping file
# Assuming the columns are structured as: keyword_column, GPAC_Level1, GPAC_Level2, GPAC_Level3
# Update "keyword_column" to match the actual name of the column that contains the keywords in your mapping file
keyword_column = mapping_df.columns[0]  # Dynamically select the first column as the keyword source
mapping_dict = {
    row[keyword_column]: {
        'GPAC_Level1': row['GPAC_Product_Level1'],
        'GPAC_Level2': row['GPAC_Product_Level2'],
        'GPAC_Level3': row['GPAC_Product_Level_3']
    }
    for _, row in mapping_df.iterrows()
}

# Define a function to dynamically tag GPAC levels based on any keyword found in a row
def tag_gpac_levels(row):
    for keyword, levels in mapping_dict.items():
        # Check if the keyword is found in any value in the row (converted to string for uniformity)
        if any(keyword in str(value) for value in row):
            return pd.Series([levels['GPAC_Level1'], levels['GPAC_Level2'], levels['GPAC_Level3']])
    return pd.Series([None, None, None])  # No keyword match found

# Apply the function to each row
df[['GPAC_Product_Level1', 'GPAC_Product_Level2', 'GPAC_Product_Level3']] = df.apply(tag_gpac_levels, axis=1)

# Save the updated DataFrame to a new file
output_path = "/Users/dnamas5/Downloads/0611V1.1_TaggedWarrant_ClientProductType.csv"
df.to_csv(output_path, index=False)

print(f"Data with GPAC predictions saved to {output_path}")

