import os
import hashlib
import re

# Configuration
# Path where your addon ZIPs are located
ADDONS_DIR = "zips"

def generate_addons_xml():
    """
    Generates the main addons.xml file.
    It collects all addon.xml files from zips/ and the root folder.
    """
    xbmc_addons = []

    # 1. Search for the Repository addon.xml in the ROOT folder
    if os.path.exists("addon.xml"):
        try:
            with open("addon.xml", "r", encoding="utf-8") as f:
                xml_content = f.read().strip()
                # Clean XML declaration
                if xml_content.startswith("<?xml"):
                    xml_content = re.sub(r'<\?xml[^>]*\?>', '', xml_content, 1).strip()
                xbmc_addons.append(xml_content)
                print("✅ Found Repository addon.xml in root")
        except Exception as e:
            print(f"❌ Error reading root addon.xml: {e}")
    else:
        print("⚠️  WARNING: No 'addon.xml' found in root. Your repo might not work correctly.")

    # 2. Search for Plugin addon.xml files in the ZIPS folder
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
                            print(f"✅ Found Plugin in: {addon_path}")
                    except Exception as e:
                        print(f"❌ Error reading {addon_path}: {e}")

    # 3. Compile the final addons.xml
    final_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n'
    final_xml += "\n".join(xbmc_addons)
    final_xml += '\n</addons>'

    # Write the file
    with open("addons.xml", "w", encoding="utf-8") as f:
        f.write(final_xml)

    print(f"🎉 Generated addons.xml with {len(xbmc_addons)} entries.")
    return final_xml

def generate_md5(xml_content):
    """
    Generates the addons.xml.md5 validation file.
    """
    try:
        m = hashlib.md5(xml_content.encode("utf-8")).hexdigest()
        with open("addons.xml.md5", "w") as f:
            f.write(m)
        print("🎉 Generated addons.xml.md5")
    except Exception as e:
        print(f"❌ Error generating MD5: {e}")

if __name__ == "__main__":
    xml = generate_addons_xml()
    generate_md5(xml)
