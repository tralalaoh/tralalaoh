import os
import hashlib
import re

# Configuration
ADDONS_DIR = "zips"

def generate_addons_xml():
    """ Generates addons.xml and addons.xml.md5 by scanning zips/ folder """
    xbmc_addons = []

    print("🚀 Generating Addons XML...")

    if os.path.exists(ADDONS_DIR):
        # Look at every folder inside zips/
        for addon_id in os.listdir(ADDONS_DIR):
            addon_folder = os.path.join(ADDONS_DIR, addon_id)

            # Skip if it's not a folder
            if not os.path.isdir(addon_folder):
                continue

            xml_path = os.path.join(addon_folder, "addon.xml")

            if os.path.exists(xml_path):
                try:
                    with open(xml_path, "r", encoding="utf-8") as f:
                        xml_content = f.read().strip()
                        # Remove <?xml> declaration to prevent duplication
                        if xml_content.startswith("<?xml"):
                            xml_content = re.sub(r'<\?xml[^>]*\?>', '', xml_content, count=1).strip()
                        xbmc_addons.append(xml_content)
                        print(f"  Found: {addon_id}")
                except Exception as e:
                    print(f"  ❌ Error reading {xml_path}: {e}")

    # Build the final XML content
    final_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n'
    final_xml += "\n".join(xbmc_addons)
    final_xml += '\n</addons>'

    # Write addons.xml
    with open("addons.xml", "w", encoding="utf-8") as f:
        f.write(final_xml)

    # Write addons.xml.md5
    m = hashlib.md5(final_xml.encode("utf-8")).hexdigest()
    with open("addons.xml.md5", "w") as f:
        f.write(m)

    print("✅ addons.xml & md5 generated successfully.")

def generate_directory_indexes():
    """ Creates index.html files so Kodi can read the folders """
    start_dir = "."
    for root, dirs, files in os.walk(start_dir):
        if ".git" in root: continue

        html = "<!DOCTYPE html><html><head><title>Index of /</title></head><body>"
        html += "<h1>Index of /</h1><hr><pre>"
        html += '<a href="../">../</a>\n'

        for d in dirs:
            if d.startswith(".") or d == "venv": continue
            html += f'<a href="{d}/">{d}/</a>\n'

        for f in files:
            if f in ["index.html", "_generator.py", ".gitignore", ".DS_Store"]: continue
            html += f'<a href="{f}">{f}</a>\n'

        html += "</pre><hr></body></html>"

        with open(os.path.join(root, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)

    print("✅ Directory Indexes generated.")

if __name__ == "__main__":
    generate_addons_xml()
    generate_directory_indexes()
