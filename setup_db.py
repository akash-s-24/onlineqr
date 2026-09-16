import os
import sys
from config import Config
import database

def setup():
    print("=" * 60)
    print("  EventMate – Database & Environment Setup Script")
    print("=" * 60)
    
    # 1. Ensure certificates directory exists
    cert_dir = Config.CERTIFICATE_FOLDER
    if not os.path.exists(cert_dir):
        os.makedirs(cert_dir, exist_ok=True)
        print(f"[OK] Created Certificates directory: {cert_dir}")
    else:
        print(f"[OK] Certificates directory already exists: {cert_dir}")

    # 2. Ensure static/images directory exists
    images_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'images')
    os.makedirs(images_dir, exist_ok=True)
    print(f"[OK] Verified Static Assets directory: {images_dir}")

    # 3. Initialize Database and Tables
    print("\n[*] Initializing Database & Seed Data...")
    try:
        database.init_db()
        print("[OK] Database initialized. Set ADMIN_PASSWORD in the environment before creating accounts.")
        print(f"[OK] Core Events: CodeCraft, CodeStorm, CodeVerse, ByteBattle")
    except Exception as e:
        print(f"[ERROR] Database initialization encountered an error: {e}")
        return False

    print("\n" + "=" * 60)
    print("  Setup completed successfully! You can now run: python app.py")
    print("=" * 60)
    return True

if __name__ == '__main__':
    setup()
