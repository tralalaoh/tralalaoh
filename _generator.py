import os
import hashlib
import re

ADDONS_DIR = "zips"

def generate_addons_xml():
    xbmc_addons = []

    # 1. Scan ZIPS
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
                        print(f"Error: {e}")

    # 2. Scan ROOT Repo XML
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

    # Generate MD5
    m = hashlib.md5(final_xml.encode("utf-8")).hexdigest()
    with open("addons.xml.md5", "w") as f:
        f.write(m)

    print("✅ addons.xml & md5 generated.")

def generate_html_index():
    """Crée un fichier index.html pour que Kodi puisse voir les fichiers"""
    html = "<html><body><h1>Kodi Repo</h1><ul>"

    # Lien vers le dossier zips
    html += '<li><a href="zips/">zips/</a></li>'
    html += '<li><a href="addons.xml">addons.xml</a></li>'

    # Lister le contenu de zips
    for root, dirs, files in os.walk(ADDONS_DIR):
        relative_root = os.path.relpath(root, ".")
        if relative_root == ".": continue

        # Créer des index dans les sous-dossiers aussi
        sub_html = "<html><body><ul>"
        sub_html += '<li><a href="../">.. (Parent)</a></li>'
        for f in files:
            if f.endswith(".zip"):
                sub_html += f'<li><a href="{f}">{f}</a></li>'
        sub_html += "</ul></body></html>"

        with open(os.path.join(root, "index.html"), "w") as f:
            f.write(sub_html)

    html += "</ul></body></html>"
    with open("index.html", "w") as f:
        f.write(html)
    print("✅ index.html generated (Browsable Mode).")

if __name__ == "__main__":
    generate_addons_xml()
    generate_html_index()
