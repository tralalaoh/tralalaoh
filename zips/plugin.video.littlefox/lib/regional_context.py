# -*- coding: utf-8 -*-
"""
Regional Search Context
Handles content region detection, name caching, and provider coordination

Architecture Layer: ORCHESTRATION
Version: 2.6.0 - Regional Detection System
"""

import json
import os

try:
    import xbmc
    KODI_ENV = True
except ImportError:
    KODI_ENV = False
    class xbmc:
        LOGDEBUG = 0
        LOGINFO = 1
        LOGWARNING = 2
        LOGERROR = 3
        @staticmethod
        def log(msg, level=1):
            print(f"[RegionalContext] {msg}")


class RegionalSearchContext:
    """
    Shared context for provider searches with regional intelligence
    
    Features:
    - Automatic content region detection (TR, AR, US, etc.)
    - Cross-provider name caching
    - Stream index caching per provider
    - Regional search strategies
    """
    
    # Region detection keywords
    REGION_KEYWORDS = {
        'TR': ['turkey', 'turkish', 'türk', 'turkiye', 'anatolia'],
        'AR': ['arab', 'arabic', 'مصر', 'عرب'],
        'KR': ['korea', 'korean', '한국'],
        'JP': ['japan', 'japanese', '日本'],
        'IN': ['india', 'indian', 'bollywood'],
        'CN': ['china', 'chinese', '中国'],
    }
    
    def __init__(self, tmdb_id, season, episode, title, tmdb_metadata=None):
        """
        Initialize regional search context
        
        Args:
            tmdb_id (int): TMDB series ID
            season (int): Season number
            episode (int): Episode number
            title (str): Series title
            tmdb_metadata (dict): Optional pre-fetched TMDB metadata
        """
        self.tmdb_id = tmdb_id
        self.season = season
        self.episode = episode
        self.title = title
        
        # Content region (auto-detected)
        self.content_region = None
        
        # All available names by language
        self.names = {
            'original': None,
            'original_lang': None,
            'ar': [],
            'en': [],
            'tr': [],
        }
        
        # Additional metadata for verification
        self.metadata = {
            'poster_url': None,
            'backdrop_url': None,
            'year': None,
            'genres': [],
            'origin_country': [],
            'original_language': None,
            'overview': None,
        }
        
        # Cross-provider caches
        self.name_cache = {}  # {provider_name: {'ar': 'name', 'en': 'name'}}
        self.search_results_cache = {}  # {provider_name: [results]} (in-memory only, not saved)
        
        # Verified names discovered during search
        self.verified_names = {}  # {source: {lang: name}}
        
        # Load metadata if provided
        if tmdb_metadata:
            self.load_from_tmdb_metadata(tmdb_metadata)
    
    def load_from_tmdb_metadata(self, data):
        """
        Load context from TMDB API response
        
        Args:
            data (dict): TMDB API response
        """
        # Extract names
        self.names['original'] = data.get('original_name')
        self.names['original_lang'] = data.get('original_language')
        
        # Primary name (might differ from original)
        primary_name = data.get('name')
        if primary_name and primary_name != self.names['original']:
            # Add to appropriate language list
            lang = self.names.get('original_lang', 'en')
            if lang == 'en' and primary_name not in self.names['en']:
                self.names['en'].append(primary_name)
            elif lang == 'tr' and primary_name not in self.names['tr']:
                self.names['tr'].append(primary_name)
            elif lang == 'ar' and primary_name not in self.names['ar']:
                self.names['ar'].append(primary_name)
        
        # Translations
        translations = data.get('translations', {}).get('translations', [])
        for trans in translations:
            lang = trans.get('iso_639_1')
            name = trans.get('data', {}).get('name', '')
            
            if name:
                if lang == 'ar' and name not in self.names['ar']:
                    self.names['ar'].append(name)
                elif lang == 'en' and name not in self.names['en']:
                    self.names['en'].append(name)
                elif lang == 'tr' and name not in self.names['tr']:
                    self.names['tr'].append(name)
        
        # Alternative titles
        alt_titles = data.get('alternative_titles', {}).get('results', [])
        for alt in alt_titles:
            title = alt.get('title', '')
            if title:
                # Try to guess language
                if self._is_arabic(title):
                    if title not in self.names['ar']:
                        self.names['ar'].append(title)
                elif any(c in title for c in ['ç', 'ğ', 'ı', 'ö', 'ş', 'ü', 'Ç', 'Ğ', 'İ', 'Ö', 'Ş', 'Ü']):
                    if title not in self.names['tr']:
                        self.names['tr'].append(title)
                else:
                    if title not in self.names['en']:
                        self.names['en'].append(title)
        
        # Metadata
        self.metadata['poster_url'] = data.get('poster_path')
        self.metadata['backdrop_url'] = data.get('backdrop_path')
        self.metadata['year'] = data.get('first_air_date', '')[:4] if data.get('first_air_date') else None
        self.metadata['genres'] = [g.get('name') for g in data.get('genres', [])]
        self.metadata['origin_country'] = data.get('origin_country', [])
        self.metadata['original_language'] = data.get('original_language')
        self.metadata['overview'] = data.get('overview')
        
        # Auto-detect region
        self.content_region = self._detect_region(data)
        
        self._log(f"Loaded metadata for '{self.names['original']}' - Region: {self.content_region}", xbmc.LOGINFO)
    
    def _detect_region(self, tmdb_data):
        """
        Auto-detect content region from TMDB metadata
        
        Args:
            tmdb_data (dict): TMDB metadata
        
        Returns:
            str: Region code (TR, AR, US, etc.) or None
        """
        # Priority 1: Origin country
        origin_country = tmdb_data.get('origin_country', [])
        if origin_country:
            country_map = {
                'TR': 'TR',
                'SA': 'AR', 'EG': 'AR', 'AE': 'AR', 'LB': 'AR', 'SY': 'AR', 'IQ': 'AR', 'JO': 'AR',
                'KR': 'KR',
                'JP': 'JP',
                'IN': 'IN',
                'CN': 'CN', 'TW': 'CN', 'HK': 'CN',
                'US': 'US', 'GB': 'US',
            }
            
            for country in origin_country:
                if country in country_map:
                    self._log(f"Region detected from origin_country: {country_map[country]}", xbmc.LOGDEBUG)
                    return country_map[country]
        
        # Priority 2: Original language
        original_lang = tmdb_data.get('original_language')
        lang_map = {
            'tr': 'TR',
            'ar': 'AR',
            'ko': 'KR',
            'ja': 'JP',
            'hi': 'IN',
            'zh': 'CN',
            'en': 'US',
        }
        
        if original_lang in lang_map:
            self._log(f"Region detected from language: {lang_map[original_lang]}", xbmc.LOGDEBUG)
            return lang_map[original_lang]
        
        # Priority 3: Keywords in title/overview
        searchable_text = ' '.join([
            tmdb_data.get('name', ''),
            tmdb_data.get('original_name', ''),
            tmdb_data.get('overview', ''),
        ]).lower()
        
        for region, keywords in self.REGION_KEYWORDS.items():
            if any(kw in searchable_text for kw in keywords):
                self._log(f"Region detected from keywords: {region}", xbmc.LOGDEBUG)
                return region
        
        # Default: Unknown
        self._log("Could not detect specific region", xbmc.LOGDEBUG)
        return None
    
    def is_turkish_content(self):
        """Check if content is Turkish"""
        return self.content_region == 'TR'
    
    def is_arabic_content(self):
        """Check if content is Arabic"""
        return self.content_region == 'AR'
    
    def get_names_for_language(self, lang):
        """
        Get all names for specific language
        
        Args:
            lang (str): Language code ('ar', 'en', 'tr', 'original')
        
        Returns:
            list: Names for that language
        """
        if lang == 'original':
            return [self.names['original']] if self.names['original'] else []
        
        return self.names.get(lang, [])
    
    def get_search_names_prioritized(self, provider_languages):
        """
        Get search names prioritized for provider's languages
        
        Args:
            provider_languages (list): Languages the provider uses (e.g., ['ar', 'tr'])
        
        Returns:
            list: Prioritized list of names to try
        """
        names = []
        
        # Add original name first if it matches provider's languages
        if self.names['original'] and self.names['original_lang'] in provider_languages:
            names.append(self.names['original'])
        
        # Add names for each provider language
        for lang in provider_languages:
            for name in self.get_names_for_language(lang):
                if name not in names:
                    names.append(name)
        
        # If no names yet, add original as fallback
        if not names and self.names['original']:
            names.append(self.names['original'])
        
        return names
    
    def cache_provider_names(self, provider_name, names_dict):
        """
        Cache names discovered by a provider
        
        Args:
            provider_name (str): Provider name
            names_dict (dict): {'ar': 'name', 'en': 'name', etc.}
        """
        self.name_cache[provider_name] = names_dict
        self._log(f"Cached names from {provider_name}: {names_dict}", xbmc.LOGDEBUG)
    
    def get_cached_name(self, provider_name, lang):
        """
        Get cached name for provider and language
        
        Args:
            provider_name (str): Provider name
            lang (str): Language code
        
        Returns:
            str: Cached name or None
        """
        return self.name_cache.get(provider_name, {}).get(lang)
    
    def get_regional_strategy(self):
        """
        Get recommended search strategy for detected region
        
        Returns:
            dict: Strategy configuration
        """
        if self.is_turkish_content():
            return {
                'name': 'TurkishContentStrategy',
                'reference_provider': 'EgyDead',
                'cache_languages': ['ar', 'en', 'tr'],
                'description': 'Use EgyDead as reference for Arabic name discovery'
            }
        
        elif self.is_arabic_content():
            return {
                'name': 'ArabicContentStrategy',
                'reference_provider': None,
                'cache_languages': ['ar', 'en'],
                'description': 'Standard Arabic content search'
            }
        
        else:
            return {
                'name': 'InternationalStrategy',
                'reference_provider': None,
                'cache_languages': ['en'],
                'description': 'Standard international content search'
            }
    
    def _is_arabic(self, text):
        """Check if text contains Arabic characters"""
        if not text:
            return False
        return any('\u0600' <= c <= '\u06FF' or '\u0750' <= c <= '\u077F' for c in text)
    
    def _log(self, message, level=xbmc.LOGINFO):
        """Log message"""
        if KODI_ENV:
            xbmc.log(f"🦊 RegionalContext: {message}", level)
        else:
            print(f"[RegionalContext] {message}")
    
    def to_dict(self):
        """Serialize context to dict for caching"""
        return {
            'tmdb_id': self.tmdb_id,
            'season': self.season,
            'episode': self.episode,
            'title': self.title,
            'content_region': self.content_region,
            'names': self.names,
            'metadata': self.metadata,
            'name_cache': self.name_cache,
            'verified_names': self.verified_names,
        }
    
    @classmethod
    def from_dict(cls, data):
        """Deserialize context from dict"""
        context = cls(
            tmdb_id=data['tmdb_id'],
            season=data['season'],
            episode=data['episode'],
            title=data['title']
        )
        
        context.content_region = data.get('content_region')
        context.names = data.get('names', {})
        context.metadata = data.get('metadata', {})
        context.name_cache = data.get('name_cache', {})
        context.verified_names = data.get('verified_names', {})
        
        return context


class ContextCache:
    """
    Persistent cache for RegionalSearchContext objects
    Stores to disk for session persistence
    """
    
    def __init__(self, cache_dir):
        """
        Initialize cache
        
        Args:
            cache_dir (str): Directory to store cache files
        """
        self.cache_dir = cache_dir
        
        # Create cache directory if needed
        if not os.path.exists(cache_dir):
            try:
                os.makedirs(cache_dir)
            except:
                pass
    
    def get_cache_key(self, tmdb_id, season, episode):
        """Generate cache key"""
        return f"context_{tmdb_id}_s{season:02d}e{episode:02d}.json"
    
    def save(self, context):
        """Save context to cache"""
        cache_key = self.get_cache_key(context.tmdb_id, context.season, context.episode)
        cache_path = os.path.join(self.cache_dir, cache_key)
        
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(context.to_dict(), f, ensure_ascii=False, indent=2)
            
            if KODI_ENV:
                xbmc.log(f"🦊 ContextCache: Saved {cache_key}", xbmc.LOGDEBUG)
        
        except Exception as e:
            if KODI_ENV:
                xbmc.log(f"🦊 ContextCache: Failed to save {cache_key}: {e}", xbmc.LOGERROR)
    
    def load(self, tmdb_id, season, episode):
        """Load context from cache"""
        cache_key = self.get_cache_key(tmdb_id, season, episode)
        cache_path = os.path.join(self.cache_dir, cache_key)
        
        if not os.path.exists(cache_path):
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            context = RegionalSearchContext.from_dict(data)
            
            if KODI_ENV:
                xbmc.log(f"🦊 ContextCache: Loaded {cache_key}", xbmc.LOGDEBUG)
            
            return context
        
        except Exception as e:
            if KODI_ENV:
                xbmc.log(f"🦊 ContextCache: Failed to load {cache_key}: {e}", xbmc.LOGERROR)
            return None
    
    def clear_episode(self, tmdb_id, season, episode):
        """Clear cache for specific episode"""
        cache_key = self.get_cache_key(tmdb_id, season, episode)
        cache_path = os.path.join(self.cache_dir, cache_key)
        
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
            except:
                pass
    
    def clear_all(self):
        """Clear entire cache"""
        if os.path.exists(self.cache_dir):
            try:
                for filename in os.listdir(self.cache_dir):
                    if filename.startswith('context_') and filename.endswith('.json'):
                        os.remove(os.path.join(self.cache_dir, filename))
            except:
                pass
