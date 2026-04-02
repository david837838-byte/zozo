import urllib.request
import json
import os

def download_repo_via_api():
    """Download repository using GitHub API"""
    
    owner = "david837838-byte"
    repo = "zozo"
    
    try:
        print("Connecting to GitHub API...")
        
        # Get repository structure
        api_base = f"https://api.github.com/repos/{owner}/{repo}/contents"
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/vnd.github.v3.raw'
        }
        
        def get_tree(path=""):
            """Recursively get and download files"""
            url = f"{api_base}/{path}" if path else api_base
            
            req = urllib.request.Request(url, headers=headers)
            
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    items = json.loads(response.read().decode())
                    
                    if not isinstance(items, list):
                        print(f"Single file or error: {items}")
                        return
                    
                    for item in items:
                        item_path = item['path']
                        item_type = item['type']
                        
                        if item_type == 'dir':
                            # Create directory
                            os.makedirs(item_path, exist_ok=True)
                            print(f"Created dir: {item_path}")
                            # Recurse into directory
                            get_tree(item_path)
                        else:
                            # Download file
                            file_url = item['download_url']
                            print(f"Downloading: {item_path}...", end=" ")
                            
                            # Create parent directories if needed
                            os.makedirs(os.path.dirname(item_path), exist_ok=True)
                            
                            file_req = urllib.request.Request(file_url, headers={
                                'User-Agent': 'Mozilla/5.0'
                            })
                            
                            with urllib.request.urlopen(file_req, timeout=30) as resp:
                                with open(item_path, 'wb') as f:
                                    f.write(resp.read())
                            
                            file_size = os.path.getsize(item_path)
                            print(f"OK ({file_size} bytes)")
            
            except Exception as e:
                print(f"Error processing {path}: {e}")
        
        # Create repo directory
        repo_dir = f"zozo-main"
        os.makedirs(repo_dir, exist_ok=True)
        os.chdir(repo_dir)
        
        get_tree()
        
        print("Download complete!")
        
    except Exception as e:
        import traceback
        print(f"Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    download_repo_via_api()
