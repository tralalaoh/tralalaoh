# Tralalaoh's Kodi Repository

Welcome to my personal Kodi addon repository! 🎬

![Kodi](https://img.shields.io/badge/Kodi-19%2B-blue)
![Addons](https://img.shields.io/badge/addons-2-green)
![Status](https://img.shields.io/badge/status-active-success)

## 📦 Available Addons

### 🎬 Turkish123
Stream Turkish series from Turkish123.org with advanced features.

**Features:**
- 🔍 Browse complete Turkish series catalog
- 🔎 Search functionality
- ⭐ Favorites system
- 📺 Continue watching & watch history
- ⚡ Smart caching (prevents 403 errors)
- 🛡️ Anti-403 protection with proper headers
- 💾 Fresh stream URLs every play
- 🎯 inputstream.adaptive integration

**Version:** 1.0.0  
**Requirements:** Kodi 19+, inputstream.adaptive

[Download Turkish123](https://tralalaoh.github.io/tralalaoh/zips/plugin.video.turkish123/plugin.video.turkish123-1.0.0.zip)

---

### 📺 3SK Video
3SK Video Streaming Addon for Turkish content.

**Version:** 1.0.0  
**Requirements:** Kodi 19+

[Download 3SK](https://tralalaoh.github.io/tralalaoh/zips/plugin.video.3sk/plugin.video.3sk-1.0.0.zip)

---

## 🚀 How to Install

### Method 1: Install from Repository (Recommended)

1. **Open Kodi**
2. **Settings → File Manager → Add source**
   - Click "Add source"
   - Enter: `https://tralalaoh.github.io/tralalaoh/`
   - Name it: "Tralalaoh Repo"
   - Click OK

3. **Settings → Add-ons → Install from repository**
   - Select "Tralalaoh Repo"
   - Video add-ons
   - Choose your addon
   - Click Install

4. **Install dependencies when prompted**
   - For Turkish123: Install inputstream.adaptive

### Method 2: Install from ZIP

1. Download the addon ZIP:
   - [Turkish123 v1.0.0](https://tralalaoh.github.io/tralalaoh/zips/plugin.video.turkish123/plugin.video.turkish123-1.0.0.zip)
   - [3SK v1.0.0](https://tralalaoh.github.io/tralalaoh/zips/plugin.video.3sk/plugin.video.3sk-1.0.0.zip)

2. In Kodi:
   - **Settings → Add-ons → Install from zip file**
   - Browse to downloaded ZIP
   - Click to install

---

## ⚙️ Requirements

### For Turkish123:
- **Kodi 19+** (Matrix or newer)
- **inputstream.adaptive** (for HLS playback)

### Install inputstream.adaptive:
1. **Settings → Add-ons → Install from repository**
2. **Kodi Add-on repository → VideoPlayer InputStream**
3. **InputStream Adaptive** → Install
4. Restart Kodi

---

## 🎯 Repository URLs

**GitHub Pages (Primary):**
```
https://tralalaoh.github.io/tralalaoh/
```

**GitHub Raw (Alternative):**
```
https://raw.githubusercontent.com/tralalaoh/tralalaoh/main/
```

**Repository Source:**
```
https://github.com/tralalaoh/tralalaoh
```

---

## 📱 Supported Platforms

- ✅ Windows
- ✅ macOS
- ✅ Linux
- ✅ Android / Android TV
- ✅ Fire TV
- ✅ Raspberry Pi
- ✅ Xbox
- ✅ iOS / tvOS

---

## 🔧 Troubleshooting

### Turkish123 Won't Play Videos

**Problem:** Video doesn't start or shows error

**Solutions:**

1. **Install inputstream.adaptive:**
   - Settings → Add-ons → Install from repository
   - Kodi Add-on repository → VideoPlayer InputStream
   - InputStream Adaptive

2. **Check internet connection:**
   - Need 5+ Mbps for streaming

3. **Try Force Refresh:**
   - Right-click episode → Context menu
   - Force Refresh Servers

### Can't Install Addon

**Problem:** "Unable to connect" or "Dependency not met"

**Solutions:**

1. **Check repository URL:**
   - Must be: `https://tralalaoh.github.io/tralalaoh/`
   - NOT: `https://tralalaoh.github.io/tralalaoh/zips/`

2. **Enable unknown sources:**
   - Settings → System → Add-ons
   - Enable "Unknown sources"

3. **Install dependencies:**
   - Install Python 3.x support
   - Install requests module
   - Install BeautifulSoup4

### Buffering Issues

**Solutions:**

1. Try different server (Force Refresh)
2. Adjust buffer in Kodi settings
3. Check network speed

---

## 📖 Addon Documentation

### Turkish123

**Features in Detail:**

- **Smart Caching:** Caches which servers work (24h), gets fresh URLs every play
- **Anti-403 Protection:** Sends proper headers to prevent CDN blocking
- **No Expiring URLs:** Always gets fresh tokens to avoid 403 errors
- **Favorites:** Bookmark your favorite series for quick access
- **Watch History:** Automatically tracks what you've watched
- **Continue Watching:** Pick up where you left off
- **Search:** Find series by name

**Known Issues:**
- Stream URLs expire in 5-15 minutes (this is normal, addon handles it)
- First play may take 10-15 seconds to test servers
- Subsequent plays are 3-5 seconds (uses cached server)

---

## 🤝 Contributing

Want to add an addon to this repository?

1. Fork this repository
2. Add your addon to `zips/` folder
3. Run `python3 _generator.py` to update repository files
4. Submit a pull request

---

## 📜 License

Individual addons may have their own licenses. Please check each addon's folder for details.

- **Turkish123:** MIT License
- **3SK:** MIT License

---

## ⚠️ Disclaimer

This repository does not host or distribute any content. The addons provide access to publicly available streams from their respective sources.

- Turkish123 addon accesses content from Turkish123.org
- 3SK addon accesses content from 3SK.media

The repository maintainer has no affiliation with the content providers.

All trademarks, service marks, trade names, product names and logos are the property of their respective owners.

---

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/tralalaoh/tralalaoh/issues)
- **Repository:** [GitHub](https://github.com/tralalaoh/tralalaoh)

---

## 📊 Statistics

- **Total Addons:** 2
- **Total Downloads:** [Coming Soon]
- **Last Updated:** December 26, 2025

---

## 🎉 Thanks for Using This Repository!

Enjoy your Turkish series! 🎬

If you find these addons useful, consider:
- ⭐ Starring the repository on GitHub
- 🐛 Reporting bugs or issues
- 💡 Suggesting new features

---

**Repository maintained by [tralalaoh](https://github.com/tralalaoh)**

Last updated: 2025-12-26
