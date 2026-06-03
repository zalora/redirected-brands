import os
import re
import json
import time
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from utils import log
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

load_dotenv()

countries = ["SG", "MY", "HK", "ID"]
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_GOOGLE_API_RETRIES = 5
BASE_RETRY_DELAY_SECONDS = 2
BATCH_UPDATE_CHUNK_SIZE = 200
LOG_PREVIEW_LIMIT = 10


def get_brand_name(name):
    """Extract brand name by removing country suffix"""
    return name.rsplit(" - ", 1)[0].title()


def get_store_name(url):
    """Extract store name from URL using multiple patterns"""
    patterns = [
        r"(?:\/c\/beauty\/|\/c\/|\/store\/)([^\/\s?#]+)",  # /c/beauty/, /c/, /store/
        r"https?:\/\/[^\/]+\/([^\/\s?#]+)"                # fallback: domain.com/store-name
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            result = match.group(1)
            return result.replace("-", " ").title()
    
    # If no patterns match, return empty string
    return ""


def get_country(raw_key):
    """Extract country code from raw key"""
    suffix = raw_key.rsplit(" - ", 1)[-1].upper()
    if suffix in countries:
        return suffix
    return None


def process_brand_data(data):
    """Process raw data into structured format"""
    result = {}
    
    for raw_key, entries in data.items():
        brand_name = get_brand_name(raw_key)
        country = get_country(raw_key)
        keyword = entries["keyword"]
        store_name = entries["store_name"] if entries["store_name"] else get_store_name(entries["url"])

        unique_key = (brand_name, store_name)

        if unique_key not in result:
            # set up initial row with brand name, store name, and 0 for all countries
            row = {
                "Brand name": brand_name,
                "Keyword": ", ".join(keyword),
                "Store name": store_name,
            }
            for c in countries:
                # create the country and url keys in dict
                row[c] = 0
                row[f"{c} url"] = ""
            result[unique_key] = row

        if country:
            result[unique_key][country.upper()] = 1
            result[unique_key][f"{country.upper()} url"] = entries["url"]
    
    return result


def create_dataframe(result):
    """Convert result dict to formatted dataframe"""
    # Convert result dict to dataframe
    df = pd.DataFrame(result.values())

    # Add 'Status' column with default value "New Added"
    # Note: Chip-style dropdowns are configured manually in Sheets as a workaround for Python library limitations
    df["Store Redirection Status"] = "New Added"

    # Add datetime column with current date and time in dd-mm-yyyy hh:mm:ss format
    current_datetime = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    df["Date Time Added"] = current_datetime

    # set the column order; column A (No) is managed directly in Google Sheets
    df = df[
        ["Brand name", "Keyword", "Store name", "SG", "MY", "HK", "ID", "Store Redirection Status", "Date Time Added", "SG url", "MY url", "HK url", "ID url"]
    ]
    
    return df


def get_api_error_status_code(error):
    """Extract HTTP status code from gspread APIError when available."""
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is not None:
        return status_code

    message = str(error)
    for code in RETRYABLE_STATUS_CODES:
        if f"[{code}]" in message:
            return code
    return None


def is_retryable_api_error(error):
    """Return True if the error is transient and should be retried."""
    status_code = get_api_error_status_code(error)
    return status_code in RETRYABLE_STATUS_CODES


def run_google_api_with_retry(action_name, action):
    """Retry transient Google Sheets API errors with exponential backoff."""
    for attempt in range(1, MAX_GOOGLE_API_RETRIES + 1):
        try:
            return action()
        except Exception as error:
            if not is_retryable_api_error(error) or attempt == MAX_GOOGLE_API_RETRIES:
                raise

            delay = BASE_RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
            status_code = get_api_error_status_code(error)
            log(
                f"{action_name} failed with HTTP {status_code} "
                f"(attempt {attempt}/{MAX_GOOGLE_API_RETRIES}). Retrying in {delay}s..."
            )
            time.sleep(delay)


def apply_batch_updates(worksheet, updates):
    """Apply updates in chunks to reduce API pressure and payload size."""
    for start in range(0, len(updates), BATCH_UPDATE_CHUNK_SIZE):
        chunk = updates[start:start + BATCH_UPDATE_CHUNK_SIZE]
        run_google_api_with_retry(
            "Updating existing records",
            lambda current_chunk=chunk: worksheet.batch_update(current_chunk)
        )


def normalize_store_name(value):
    """Normalize store name for lookup and logging."""
    return str(value).strip()


def append_cell_update(batch_updates, col, row, value):
    """Append a single cell update payload for gspread batch_update."""
    batch_updates.append({
        "range": f"{col}{row}",
        "values": [[value]],
    })


def get_record_field(record, field_name):
    """Read field from either pandas Series or dict."""
    return record.get(field_name, "")


def log_name_preview(prefix, names):
    """Log a compact preview for long name lists."""
    if not names:
        return

    preview = names[:LOG_PREVIEW_LIMIT]
    suffix = "" if len(names) <= LOG_PREVIEW_LIMIT else ", ..."
    log(f"{prefix} ({len(names)}): [{', '.join(preview)}{suffix}]")


def export_to_google_sheets(df):
    """Export dataframe to Google Sheets - append new data if not already exists.

    Requires the GOOGLE_SERVICE_ACCOUNT environment variable to be set to either:
      - A JSON string (the full contents of a service account key file), or
      - A file path pointing to a service account JSON key file.

    Requires GOOGLE_SHEET_URL to be set to the full Google Sheets URL.
    """
    service_account_value = os.getenv("GOOGLE_SERVICE_ACCOUNT")

    if not service_account_value or not service_account_value.strip():
        raise EnvironmentError(
            "GOOGLE_SERVICE_ACCOUNT is not set or empty. "
            "Set it to the service account JSON string or a path to the JSON key file."
        )

    sheet_url = os.getenv("GOOGLE_SHEET_URL")
    if not sheet_url or not sheet_url.strip():
        raise EnvironmentError(
            "GOOGLE_SHEET_URL is not set or empty. "
            "Set it to the full Google Sheets URL."
        )

    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        service_account_info = json.loads(service_account_value)
        creds = Credentials.from_service_account_info(service_account_info, scopes=scope)
    except json.JSONDecodeError:
        creds = Credentials.from_service_account_file(service_account_value, scopes=scope)
    client = gspread.authorize(creds)

    spreadsheet = run_google_api_with_retry(
        "Opening spreadsheet",
        lambda: client.open_by_url(sheet_url)
    )
    worksheet = run_google_api_with_retry(
        "Opening worksheet",
        lambda: spreadsheet.get_worksheet(0)
    )

    def write_dataframe(dataframe, row, include_header, action_name):
        run_google_api_with_retry(
            action_name,
            lambda: set_with_dataframe(
                worksheet,
                dataframe,
                row=row,
                col=2,
                include_index=False,
                include_column_header=include_header,
            )
        )

    # Map each country to its (value column letter, url column letter) in the sheet
    # Columns: B=Brand name, C=Keyword, D=Store name, E=SG, F=MY, G=HK, H=ID,
    #          I=Store Redirection Status, J=Date Time Added, K=SG url, L=MY url, M=HK url, N=ID url
    country_col_map = {
        'SG': ('E', 'K'),
        'MY': ('F', 'L'),
        'HK': ('G', 'M'),
        'ID': ('H', 'N'),
    }
    fixed_col_map = {
        'Brand name': 'B',
        'Keyword': 'C',
        'Store Redirection Status': 'I',
        'Date Time Added': 'J',
    }

    def is_missing(value):
        return pd.isna(value) or str(value).strip() == ""

    # Get existing data from sheet
    try:
        existing_data = run_google_api_with_retry(
            "Reading existing sheet records",
            lambda: worksheet.get_all_records()
        )
        if existing_data:
            existing_df = pd.DataFrame(existing_data)
            log(f"Found {len(existing_df)} existing records in sheet")

            # Build lookup by store name only: {Store name: {'sheet_row': row_number, 'row': row_data_dict}}
            existing_lookup = {}
            for i, (_, row) in enumerate(existing_df.iterrows()):
                key = normalize_store_name(row['Store name'])
                sheet_row = i + 2  # +2: row 1 is header, data starts at row 2
                if key and key not in existing_lookup:
                    existing_lookup[key] = {
                        'sheet_row': sheet_row,
                        'row': row.to_dict(),
                    }

            new_records = []
            batch_updates = []
            seen_store_names = set(existing_lookup.keys())
            updated_existing_stores = set()

            for _, row in df.iterrows():
                key = normalize_store_name(get_record_field(row, 'Store name'))
                if not key:
                    continue

                if key not in seen_store_names:
                    new_records.append(row)
                    seen_store_names.add(key)
                else:
                    # Row already exists — fill missing fields and merge country/url updates.
                    entry = existing_lookup.get(key)
                    if not entry:
                        continue

                    sheet_row = entry['sheet_row']
                    existing_row = entry['row']
                    any_country_upgraded = False

                    # Fill fixed fields if they are missing in sheet.
                    for field in ['Brand name', 'Keyword', 'Store Redirection Status']:
                        existing_val = existing_row.get(field, "")
                        new_val = get_record_field(row, field)
                        if is_missing(existing_val) and not is_missing(new_val):
                            col = fixed_col_map[field]
                            append_cell_update(batch_updates, col, sheet_row, new_val)
                            existing_row[field] = new_val

                    for country in countries:
                        new_val = get_record_field(row, country)
                        raw_existing_val = existing_row.get(country, "")
                        country_col, url_col = country_col_map[country]

                        # Normalize empty country marks in sheet to 0.
                        if is_missing(raw_existing_val):
                            append_cell_update(batch_updates, country_col, sheet_row, 0)
                            existing_val = 0
                            existing_row[country] = 0
                        else:
                            try:
                                existing_val = int(raw_existing_val)
                            except (ValueError, TypeError):
                                existing_val = 0

                        new_url_val = get_record_field(row, f'{country} url')
                        existing_url_val = existing_row.get(f'{country} url', '')

                        if new_val == 1 and existing_val == 0:
                            any_country_upgraded = True
                            append_cell_update(batch_updates, country_col, sheet_row, 1)
                            if not is_missing(new_url_val):
                                append_cell_update(batch_updates, url_col, sheet_row, new_url_val)
                                existing_row[f'{country} url'] = new_url_val
                            existing_row[country] = 1
                        elif new_val == 1 and is_missing(existing_url_val) and not is_missing(new_url_val):
                            # Keep mark=1 and fill URL if it is missing.
                            append_cell_update(batch_updates, url_col, sheet_row, new_url_val)
                            existing_row[f'{country} url'] = new_url_val

                    # Date Time Added rules:
                    # 1) Override with current time if any country changes 0 -> 1.
                    # 2) If missing, fill it as current time.
                    current_datetime = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                    if any_country_upgraded or is_missing(existing_row.get('Date Time Added', '')):
                        append_cell_update(
                            batch_updates,
                            fixed_col_map['Date Time Added'],
                            sheet_row,
                            current_datetime,
                        )
                        existing_row['Date Time Added'] = current_datetime

                    if any_country_upgraded:
                        updated_existing_stores.add(key)

            new_record_brand_names = [
                normalize_store_name(get_record_field(r, 'Brand name'))
                for r in new_records
                if normalize_store_name(get_record_field(r, 'Brand name'))
            ]
            log_name_preview("New record Brand name(s)", new_record_brand_names)
            if batch_updates:
                apply_batch_updates(worksheet, batch_updates)
                log(f"Updated {len(batch_updates)} cell(s) in existing records")
                if updated_existing_stores:
                    log_name_preview("Updated existing store(s)", sorted(updated_existing_stores))

            if new_records:
                new_df = pd.DataFrame(new_records)
                new_store_names = sorted({
                    normalize_store_name(get_record_field(r, 'Store name'))
                    for r in new_records
                    if normalize_store_name(get_record_field(r, 'Store name'))
                })

                # Append new data below existing data; column A is managed directly in Google Sheets
                last_row = len(existing_df) + 2  # +2 because of header
                write_dataframe(new_df, last_row, False, "Appending new records")

                log(f"Appended {len(new_df)} new records to Google Sheets")
                if new_store_names:
                    log_name_preview("Appended new store(s)", new_store_names)
            else:
                log("No new records to add - all data already exists in sheet")
        else:
            # No existing data, add everything with headers
            # Then add the data starting from column B
            write_dataframe(df, 1, True, "Writing initial sheet data")
            log("Added data to empty Google Sheets")
            
    except Exception as e:
        log(f"Google Sheets export failed: {e}")
        raise


def exporter_run(data):
    """Main function to orchestrate the data processing"""
    
    # Process data 
    result = process_brand_data(data)
    
    # Create dataframe
    df = create_dataframe(result)
    
    # Export to Google Sheets
    export_to_google_sheets(df)
    
    log("Data processing completed successfully!")