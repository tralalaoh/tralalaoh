import os
import hashlib
import re

# Configuration
ADDONS_DIR = "zips"

def generate_addons_xml():
    """ Generates addons.xml and addons.xml.md5 """
    xbmc_addons = []

    if os.path.exists(ADDONS_DIR):
        for root, dirs, files in os.walk(ADDONS_DIR):
            for file_name in files:
                if file_name == "addon.xml":
                    addon_path = os.path.join(root, file_name)
                    try:
                        with open(addon_path, "r", encoding="utf-8") as f:
                            xml_content = f.read().strip()
                            if xml_content.startswith("<?xml"):
                                xml_content = re.sub(r'<\?xml[^>]*\?>', '', xml_content, 1).strip()
                            xbmc_addons.append(xml_content)
                    except Exception as e:
                        print(f"Error reading {addon_path}: {e}")

    if os.path.exists("addon.xml"):
        with open("addon.xml", "r", encoding="utf-8") as f:
            xml_content = f.read().strip()
            if xml_content.startswith("<?xml"):
                xml_content = re.sub(r'<\?xml[^>]*\?>', '', xml_content, 1).strip()
            xbmc_addons.append(xml_content)

    final_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n'
    final_xml += "\n".join(xbmc_addons)
    final_xml += '\n</addons>'

    with open("addons.xml", "w", encoding="utf-8") as f:
        f.write(final_xml)

    m = hashlib.md5(final_xml.encode("utf-8")).hexdigest()
    with open("addons.xml.md5", "w") as f:
        f.write(m)

    print("✅ addons.xml & md5 generated.")

def generate_directory_indexes():
    """
    Recursively creates index.html files
    so Kodi can browse folders on GitHub Pages
    """
    # Start from current directory
    start_dir = "."

    for root, dirs, files in os.walk(start_dir):
        # Skip .git folder
        if ".git" in root: continue

        # Build HTML content
        html = "<!DOCTYPE html><html><head><title>Index of /</title></head><body>"
        html += "<h1>Index of /</h1><hr><pre>"

        # Link to Parent Directory
        html += '<a href="../">../</a>\n'

        # List Directories
        for d in dirs:
            if d.startswith(".") or d == "venv": continue
            html += f'<a href="{d}/">{d}/</a>\n'

        # List Files
        for f in files:
            if f in ["index.html", "_generator.py", ".gitignore", ".DS_Store"]: continue
            html += f'<a href="{f}">{f}</a>\n'

        html += "</pre><hr></body></html>"

        # Write index.html in the current folder
        index_path = os.path.join(root, "index.html")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html)

    print("✅ Directory Indexes generated (Recursive).")

if __name__ == "__main__":
    generate_addons_xml()
    generate_directory_indexes()
