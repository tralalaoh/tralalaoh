#!/bin/bash
# Diagnose why Turkish123 isn't showing in browser

echo "========================================"
echo "Index.html Diagnosis"
echo "========================================"
echo ""

cd /var/home/bazzite/Documents/kodi-dev/my-kodi-repo

echo "1️⃣ Checking zips/index.html content..."
echo ""
cat zips/index.html
echo ""
echo "========================================"
echo ""

echo "2️⃣ Checking what _generator.py actually sees..."
echo ""

python3 << 'PYEOF'
import os

print("Directories in zips/:")
for item in os.listdir("zips"):
    full_path = os.path.join("zips", item)
    if os.path.isdir(full_path):
        print(f"  📁 {item}/")
        # Check if it starts with "."
        if item.startswith("."):
            print(f"     ⚠️  Starts with . (hidden by _generator.py)")
    else:
        print(f"  📄 {item}")

print("\nFolders that should appear in index:")
for item in os.listdir("zips"):
    full_path = os.path.join("zips", item)
    if os.path.isdir(full_path) and not item.startswith(".") and item != "venv":
        print(f"  ✅ {item}/")
PYEOF

echo ""
echo "========================================"
echo ""

echo "3️⃣ Testing if browser can see the folder..."
echo ""
echo "URL to test in browser:"
echo "file:///var/home/bazzite/Documents/kodi-dev/my-kodi-repo/zips/index.html"
echo ""

echo "4️⃣ Testing direct access to Turkish123..."
echo ""
if [ -f "zips/plugin.video.turkish123/index.html" ]; then
    echo "✅ Turkish123 index.html exists"
    echo "Direct URL: file:///var/home/bazzite/Documents/kodi-dev/my-kodi-repo/zips/plugin.video.turkish123/index.html"
else
    echo "❌ Turkish123 index.html missing"
fi

echo ""
echo "5️⃣ Raw directory listing (what browser sees)..."
ls -la zips/ | grep -v "^total"

echo ""
echo "========================================"
