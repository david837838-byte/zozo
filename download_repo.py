import urllib.request
import urllib.error
import ssl
import zipfile
import os

# Disable SSL verification for troubleshooting
ssl._create_default_https_context = ssl._create_unverified_context

try:
    print("Downloading repository...")
    
    # Use codeload.github.com which handles archives better
    url = 'https://codeload.github.com/david837838-byte/zozo/zip/main'
    
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    
    with urllib.request.urlopen(req, timeout=30) as response:
        file_size = int(response.headers.get('Content-Length', 0))
        print(f"Downloading {file_size} bytes...")
        
        with open('zozo.zip', 'wb') as f:
            chunk_size = 8192
            downloaded = 0
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if file_size > 0:
                    percent = (downloaded / file_size) * 100
                    print(f"Progress: {percent:.1f}%", end='\r')
    
    print("\nDownload complete!")
    
    # Check file
    with open('zozo.zip', 'rb') as f:
        header = f.read(4)
        print(f"File header: {header}")
        if header != b'PK\x03\x04':
            print("Warning: File doesn't look like a ZIP file!")
    
    print("Extracting...")
    with zipfile.ZipFile('zozo.zip', 'r') as z:
        z.extractall()
    
    os.remove('zozo.zip')
    
    # List extracted directory
    dirs = [d for d in os.listdir('.') if os.path.isdir(d) and 'zozo' in d.lower()]
    print(f"Extracted: {dirs}")
    print("Download and extraction complete!")
    
except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()
