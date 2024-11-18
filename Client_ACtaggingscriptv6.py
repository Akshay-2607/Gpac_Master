import pandas as pd
import re
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import io
import yaml

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Google Drive authentication
SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = "C:/Users/aksha/Downloads/pecten-project-aa4d3c0231d8.json"  # Replace with the actual path to your service account file
creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

# Load a file from Google Drive
def load_google_drive_file(file_name, folder_id):
    query = f"'{folder_id}' in parents and name='{file_name}'"
    results = drive_service.files().list(q=query, spaces='drive').execute()
    items = results.get('files', [])
    
    if not items:
        all_files = drive_service.files().list(q=f"'{folder_id}' in parents", spaces='drive').execute()
        available_files = [file['name'] for file in all_files.get('files', [])]
        logger.error(f"No file found on Google Drive with name: {file_name}. Available files: {available_files}")
        return None
    
    file_id = items[0]['id']
    request = drive_service.files().get(fileId=file_id).execute()
    mime_type = request.get("mimeType")
    file_content = io.BytesIO()
    
    if mime_type == "application/vnd.google-apps.spreadsheet":
        export_request = drive_service.files().export_media(fileId=file_id, mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        downloader = MediaIoBaseDownload(file_content, export_request)
    else:
        download_request = drive_service.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(file_content, download_request)
    
    done = False
    while not done:
        _, done = downloader.next_chunk()
    
    file_content.seek(0)
    if file_name.endswith('.csv'):
        return pd.read_csv(file_content)
    elif file_name.endswith('.xlsx') or mime_type == "application/vnd.google-apps.spreadsheet":
        return pd.read_excel(file_content, sheet_name=None)
    elif file_name.endswith('.yaml'):
        return yaml.safe_load(file_content)

# Load configuration and data files from Google Drive
config = load_google_drive_file("universalconfigv2.yaml", "1y0ywIvouxRKFE6WrTJWS-1XBcBdoPtgX")
logger.debug(f"Loaded configuration: {config}")

# Load only the GPAC_Asset_Master sheet
gpac_master_data = load_google_drive_file(config['file_paths']['gpac_master']['file_name'], config['file_paths']['gpac_master']['folder_id'])
gpac_asset_master = pd.DataFrame(gpac_master_data[config['file_paths']['gpac_master']['sheets']['asset_class_mapping']])

# Load input data and handle single or multiple sheets
input_data_raw = load_google_drive_file(config['file_paths']['input_data']['file_name'], config['file_paths']['input_data']['folder_id'])

# If input_data_raw is a dictionary of sheets, select the desired sheet
if isinstance(input_data_raw, dict):
    sheet_name = 'Sheet1'  # Update with actual sheet name if different
    input_data = pd.DataFrame(input_data_raw.get(sheet_name, []))
else:
    input_data = pd.DataFrame(input_data_raw)

# Main Tagging Function
def tag_assets(input_data, gpac_asset_master):
    tagged_data = []

    for index, row in input_data.iterrows():
        # Method 1: Direct Mapping from CLIENT_ASSET_CLASS
        tag = apply_direct_mapping(row, gpac_asset_master)
        
        # Method 2: Use CLIENT_SEC_TYPE and Related Columns if no direct mapping is found
        if not tag:
            tag = apply_sec_type_tagging(row, gpac_asset_master)
        
        # Method 3: Fallback to Keyword Matching if no tags were assigned
        if not tag:
            tag = apply_keyword_matching(row, gpac_asset_master)
        
        # Append the tagged row data, including 'Unclassified' if no tags were found
        tagged_data.append(tag if tag else default_unclassified_tag(row))
    
    # Create a DataFrame from the tagged data
    tagged_df = pd.DataFrame(tagged_data)
    
    # Merge the tagged columns with the original input data, adding tagged columns to the right
    output_df = pd.concat([input_data.reset_index(drop=True), tagged_df], axis=1)
    
    return output_df

# Method 1: Direct Mapping from CLIENT_ASSET_CLASS
def apply_direct_mapping(row, gpac_asset_master):
    client_asset_class = str(row.get(config['tagging_priority']['client_asset_code']['column_name'], ""))
    
    if client_asset_class and client_asset_class.startswith("AC_"):
        matched = gpac_asset_master[gpac_asset_master['Asset_Class_Code'] == client_asset_class]
        if not matched.empty:
            logger.info(f"Direct match found for CLIENT_ASSET_CLASS: {client_asset_class}")
            return {
                'GPAC_Asset_Class_Level1': matched.iloc[0]['GPAC_Asset_Class_Level1'],
                'GPAC_Asset_Class_Level2': matched.iloc[0]['GPAC_Asset_Class_Level2'],
                'GPAC_Asset_Class_Level3': matched.iloc[0]['GPAC_Asset_Class_Level3'],
                'Matched_Rule_ID': f"Asset_Class_Code: {client_asset_class}"
            }
    return None

# Method 2: Tagging Using CLIENT_SEC_TYPE and Related Columns in the Input Data
def apply_sec_type_tagging(row, gpac_asset_master):
    for column in config['column_priority']['primary_columns']:
        value = row.get(column, "")

        if pd.isna(value) or value == "":
            continue
        
        matched = gpac_asset_master[gpac_asset_master['Keywords_Matched'].str.contains(str(value), case=False, na=False)]
        
        if not matched.empty:
            logger.info(f"Match found in input column '{column}' with value: {value}")
            return {
                'GPAC_Asset_Class_Level1': matched.iloc[0].get('GPAC_Asset_Class_Level1', 'Unclassified'),
                'GPAC_Asset_Class_Level2': matched.iloc[0].get('GPAC_Asset_Class_Level2', 'Unclassified'),
                'GPAC_Asset_Class_Level3': matched.iloc[0].get('GPAC_Asset_Class_Level3', 'Unclassified'),
                'Matched_Rule_ID': f"Keyword Match: {value}"
            }
    return None

# Method 3: Column-Agnostic Keyword Matching
def apply_keyword_matching(row, gpac_asset_master):
    row_text = " ".join(
        [str(row[col]) for col in row.index if col not in config.get('ignore_columns', []) and pd.notna(row[col])]
    ).lower()
    stop_words = set(config['keyword_matching']['stop_words'])
    threshold = config['keyword_matching']['frequency_threshold']
    
    def clean_keywords(text):
        if not isinstance(text, str):
            return []
        words = text.split(',')
        return [word.strip().lower() for word in words if word.strip().lower() not in stop_words]
    
    for _, rule in gpac_asset_master.iterrows():
        keywords = clean_keywords(rule.get("Keywords_Matched", ""))
        matched_phrases = [phrase for phrase in keywords if re.search(r'\b' + re.escape(phrase) + r'\b', row_text)]
        if len(matched_phrases) >= threshold:
            logger.info(f"Keyword match found for row with rule {rule['Rule_ID']}")
            return {
                'GPAC_Asset_Class_Level1': rule['GPAC_Asset_Class_Level1'],
                'GPAC_Asset_Class_Level2': rule['GPAC_Asset_Class_Level2'],
                'GPAC_Asset_Class_Level3': rule['GPAC_Asset_Class_Level3'],
                'Matched_Rule_ID': rule['Rule_ID']
            }
    return None

# Default Unclassified Tag if no tag is found
def default_unclassified_tag(row):
    logger.info(f"No tag found for row {row.name}. Marked as Unclassified.")
    return {
        'ID': row.get('ID', ''),
        'GPAC_Asset_Class_Level1': 'Unclassified',
        'GPAC_Asset_Class_Level2': 'Unclassified',
        'GPAC_Asset_Class_Level3': 'Unclassified',
        'Matched_Rule_ID': 'None'
    }

# Save output to Google Drive
def save_to_google_drive(df, file_name, folder_id):
    csv_buffer = io.BytesIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)
    
    file_metadata = {
        'name': file_name,
        'parents': [folder_id],
        'mimeType': 'application/vnd.google-apps.spreadsheet'
    }
    
    media = MediaIoBaseUpload(csv_buffer, mimetype='text/csv')
    drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    logger.info(f"File saved to Google Drive as {file_name}")

# Run the tagging process and save results
try:
    output_df = tag_assets(input_data, gpac_asset_master)
    output_file_name = config['output']['output_file_name']
    output_folder_id = config['output']['folder_id']
    save_to_google_drive(output_df, output_file_name, output_folder_id)
    logger.info("Script execution completed successfully.")
except Exception as e:
    logger.error(f"Tagging process failed: {e}")

