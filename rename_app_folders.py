#!/usr/bin/env python3
"""
Script to rename application folders to match the format: company_roleTitle_jobID
based on the app_details.json file in each folder.
"""

import os
import json
import shutil
from pathlib import Path
from typing import Optional

def get_app_id(company_name: str, role_title: str, job_id: Optional[str] = None) -> str:
    """Creates a safe directory name from company, role, and optional job ID.
    This function matches exactly the logic in app/backend/utils.py"""
    safe_company = "".join(c if c.isalnum() else '_' for c in company_name)
    safe_role = "".join(c if c.isalnum() else '_' for c in role_title)
    if job_id:
        safe_job_id = "".join(c if c.isalnum() else '_' for c in job_id)
        return f"{safe_company}_{safe_role}_{safe_job_id}"
    return f"{safe_company}_{safe_role}"

def rename_app_folders(applications_dir):
    """Rename application folders to match app_details.json content."""
    applications_path = Path(applications_dir)
    
    if not applications_path.exists():
        print(f"Applications directory not found: {applications_dir}")
        return
    
    print(f"Scanning applications directory: {applications_dir}")
    
    # Get all subdirectories
    app_dirs = [d for d in applications_path.iterdir() if d.is_dir()]
    print(f"Found {len(app_dirs)} application directories")
    
    renamed_count = 0
    errors = []
    
    for app_dir in app_dirs:
        try:
            app_details_path = app_dir / "app_details.json"
            
            if not app_details_path.exists():
                print(f"⚠️  No app_details.json found in {app_dir.name}, skipping...")
                continue
            
            # Read app details
            with open(app_details_path, 'r', encoding='utf-8') as f:
                details = json.load(f)
            
            company = details.get("companyName", "")
            role = details.get("roleTitle", "")
            job_id = details.get("jobId", "")
            
            if not company or not role:
                print(f"⚠️  Missing company or role in {app_dir.name}, skipping...")
                continue
            
            # Generate new folder name
            new_name = get_app_id(company, role, job_id)
            
            if new_name == app_dir.name:
                print(f"✅ {app_dir.name} - already correctly named")
                continue
            
            # Check if target name already exists
            target_path = applications_path / new_name
            if target_path.exists() and target_path != app_dir:
                print(f"⚠️  Target name {new_name} already exists, skipping {app_dir.name}")
                continue
            
            print(f"🔄 Renaming: {app_dir.name} → {new_name}")
            
            # Rename the folder
            app_dir.rename(target_path)
            renamed_count += 1
            
        except Exception as e:
            error_msg = f"❌ Error processing {app_dir.name}: {str(e)}"
            print(error_msg)
            errors.append(error_msg)
    
    print(f"\n📊 Summary:")
    print(f"✅ Successfully renamed: {renamed_count} folders")
    if errors:
        print(f"❌ Errors: {len(errors)}")
        for error in errors:
            print(f"   {error}")
    else:
        print("🎉 All folders processed successfully!")

def main():
    """Main function."""
    # Default applications directory (relative to script location)
    default_apps_dir = "applications"
    
    print("🔄 Application Folder Renamer")
    print("=" * 40)
    
    # Check if applications directory exists
    if os.path.exists(default_apps_dir):
        print(f"Found applications directory: {default_apps_dir}")
        use_default = input("Use this directory? (y/n): ").lower().strip()
        
        if use_default == 'y':
            applications_dir = default_apps_dir
        else:
            applications_dir = input("Enter path to applications directory: ").strip()
    else:
        applications_dir = input("Enter path to applications directory: ").strip()
    
    if not applications_dir:
        print("❌ No directory specified. Exiting.")
        return
    
    # Confirm before proceeding
    print(f"\n📁 Target directory: {applications_dir}")
    print("⚠️  This will rename application folders based on app_details.json content.")
    confirm = input("Continue? (y/n): ").lower().strip()
    
    if confirm != 'y':
        print("❌ Operation cancelled.")
        return
    
    try:
        rename_app_folders(applications_dir)
    except KeyboardInterrupt:
        print("\n❌ Operation interrupted by user.")
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")

if __name__ == "__main__":
    main()
