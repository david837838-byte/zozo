import urllib.request
import json

try:
    # Check commits
    print("Checking commits...")
    req = urllib.request.Request(
        'https://api.github.com/repos/david837838-byte/zozo/commits',
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    resp = urllib.request.urlopen(req)
    commits = json.loads(resp.read())
    print(f"Found {len(commits)} commits")
    
    # Check contents
    print("\nChecking contents...")
    req = urllib.request.Request(
        'https://api.github.com/repos/david837838-byte/zozo/contents',
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    
    try:
        resp = urllib.request.urlopen(req)
        contents = json.loads(resp.read())
        print(f"Found {len(contents)} items in root")
        for item in contents[:5]:
            print(f"  - {item['name']} ({item['type']})")
    except urllib.error.HTTPError as e:
        print(f"Contents endpoint error: {e.code} {e.reason}")
        print("Repository might be empty or have different structure")
    
except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()
