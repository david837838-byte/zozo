import urllib.request
import urllib.error
import zipfile
import os
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

try:
    # Try direct GitHub link
    url = 'https://github.com/david837838-byte/zozo/archive/main.zip'
    
    print(f"Downloading from {url}...")
    
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    )
    
    with urllib.request.urlopen(req, timeout=60) as response:
        file_size = int(response.headers.get('Content-Length', 0))
        print(f"File size: {file_size} bytes")
        
        with open('zozo.zip', 'wb') as f:
            downloaded = 0
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
    
    print(f"Downloaded: {downloaded} bytes")
    
    # Verify it's a real ZIP
    with open('zozo.zip', 'rb') as f:
        header = f.read(4)
        print(f"ZIP header: {header}")
        if header == b'PK\x03\x04':
            print("Extracting...")
            with zipfile.ZipFile('zozo.zip', 'r') as z:
                z.extractall()
            
            os.remove('zozo.zip')
            
            dirs = [d for d in os.listdir('.') if 'zozo' in d.lower()]
            print(f"Successfully extracted: {dirs}")
        else:
            print("File is not a valid ZIP!")
            with open('zozo.zip', 'r') as f:
                content = f.read(500)
                print(f"Content preview: {content[:500]}")
    
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.reason}")
except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()
