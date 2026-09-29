import os
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

DEFAULT_PARENT_FOLDER_ID = "1Q3KE3Ncfm-Nn6FIbGhFXs25HFIq-InOn"

SUBFOLDERS = [
    "01_Summary_Excel_Results",
    "02_Flux_Data",
    "03_Simulation_Outputs",
    "04_Input_Decks",
    "05_Execution_Logs_and_Benchmarks"
]

def get_drive_service(oauth_json_str_or_path: str = None):
    """Khoi tao Google Drive API service tu JSON string hoac file path."""
    if oauth_json_str_or_path is None:
        oauth_json_str_or_path = os.environ.get("GDRIVE_OAUTH_JSON")
        if not oauth_json_str_or_path:
            local_default = r"C:\antigravity_goat\user_oauth_creds.json"
            if os.path.exists(local_default):
                oauth_json_str_or_path = local_default

    if not oauth_json_str_or_path:
        raise ValueError("Khong tim thay thong tin xac thuc GDRIVE_OAUTH_JSON.")

    # Check neu la duong dan file
    if os.path.exists(oauth_json_str_or_path):
        creds = Credentials.from_authorized_user_file(oauth_json_str_or_path)
    else:
        # La chuoi JSON
        info = json.loads(oauth_json_str_or_path)
        creds = Credentials.from_authorized_user_info(info)

    return build("drive", "v3", credentials=creds)

def get_or_create_subfolders(service, parent_id: str = None):
    parent_id = parent_id or os.environ.get("GDRIVE_FOLDER_ID") or DEFAULT_PARENT_FOLDER_ID
    q = f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    existing = service.files().list(q=q, fields="files(id, name)").execute().get("files", [])
    existing_map = {f["name"]: f["id"] for f in existing}

    folder_ids = {}
    for sf in SUBFOLDERS:
        if sf in existing_map:
            folder_ids[sf] = existing_map[sf]
        else:
            meta = {
                "name": sf,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id]
            }
            created = service.files().create(body=meta, fields="id, name").execute()
            folder_ids[sf] = created["id"]
    return folder_ids

def upload_file_to_folder(service, local_path: str, target_folder_id: str, target_name: str = None):
    p = Path(local_path)
    if not p.exists():
        raise FileNotFoundError(f"{local_path} khong ton tai")
    name = target_name or p.name

    # Neu da co file cung ten thi xoa de ghi de
    q = f"'{target_folder_id}' in parents and name = '{name}' and trashed = false"
    old_files = service.files().list(q=q, fields="files(id)").execute().get("files", [])
    for old in old_files:
        try:
            service.files().delete(fileId=old["id"]).execute()
        except Exception:
            pass

    meta = {
        "name": name,
        "parents": [target_folder_id]
    }
    media = MediaFileUpload(str(p), resumable=True)
    f = service.files().create(body=meta, media_body=media, fields="id, name, webViewLink").execute()
    return f

def get_completed_jobs_from_drive(service, flux_folder_id: str) -> set:
    """Quet toan bo file flux_runner_*.csv hoac flux_all.csv tren Drive de lay danh sach job da chay xong."""
    q = f"'{flux_folder_id}' in parents and trashed = false"
    files = service.files().list(q=q, fields="files(id, name)").execute().get("files", [])
    completed = set()

    for f in files:
        if f["name"].endswith(".csv"):
            try:
                content = service.files().get_media(fileId=f["id"]).execute().decode("utf-8", errors="ignore")
                for line in content.splitlines()[1:]:
                    parts = line.strip().split(",")
                    if parts and parts[0]:
                        completed.add(parts[0])
            except Exception as e:
                print(f"Loi khi doc {f['name']} tu Drive: {e}")
    return completed
