"""Debrid service integration - FIXED Torbox controltorrent API."""

import requests
from resources.lib.settings import Settings
from resources.lib.logger import log, log_error


class DebridService:
    """Base class for debrid services."""
    
    def __init__(self, api_key):
        """Initialize debrid service."""
        self.api_key = api_key
        self.timeout = 10
    
    def test_connection(self):
        """Test API connection."""
        raise NotImplementedError


class RealDebrid(DebridService):
    """Real-Debrid service."""
    
    BASE_URL = 'https://api.real-debrid.com/rest/1.0'
    
    def test_connection(self):
        """Test Real-Debrid API connection."""
        try:
            headers = {'Authorization': f'Bearer {self.api_key}'}
            response = requests.get(
                f'{self.BASE_URL}/user',
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            username = data.get('username', 'Unknown')
            return True, f"Connected as {username}"
        except requests.RequestException as e:
            return False, str(e)
    
    def unrestrict_link(self, link):
        """Unrestrict a link through Real-Debrid."""
        try:
            headers = {'Authorization': f'Bearer {self.api_key}'}
            data = {'link': link}
            response = requests.post(
                f'{self.BASE_URL}/unrestrict/link',
                headers=headers,
                data=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            return result.get('download')
        except Exception as e:
            log_error("Failed to unrestrict link with Real-Debrid", e)
            return None


class Torbox(DebridService):
    """Torbox service with FIXED controltorrent API."""
    
    BASE_URL = 'https://api.torbox.app/v1/api'
    
    def test_connection(self):
        """Test Torbox API connection."""
        try:
            headers = {'Authorization': f'Bearer {self.api_key}'}
            response = requests.get(
                f'{self.BASE_URL}/user/me',
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            if data.get('success'):
                email = data.get('data', {}).get('email', 'Unknown')
                return True, f"Connected as {email}"
            else:
                return False, "Invalid API key"
        except requests.RequestException as e:
            return False, str(e)
    
    def unrestrict_link(self, link):
        """
        Unrestrict a link through Torbox.
        
        FIXED: Use controltorrent API with proper JSON format!
        """
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'  # CRITICAL!
            }
            
            # Torbox createtorrent API expects form data for magnet
            data = {'magnet': link}
            
            log(f"Torbox: Creating torrent from magnet link")
            response = requests.post(
                f'{self.BASE_URL}/torrents/createtorrent',
                headers=headers,
                data=data,  # Use data= for form encoding (this API requires form data)
                timeout=self.timeout
            )
            
            log(f"Torbox API response status: {response.status_code}")
            
            response.raise_for_status()
            result = response.json()
            
            log(f"Torbox response: {result}")
            
            if result.get('success'):
                torrent_id = result.get('data', {}).get('torrent_id')
                if torrent_id:
                    log(f"Torrent created with ID: {torrent_id}")
                    
                    # Request cached info
                    info_response = requests.get(
                        f'{self.BASE_URL}/torrents/mylist',
                        headers=headers,
                        timeout=self.timeout
                    )
                    info_response.raise_for_status()
                    torrents = info_response.json().get('data', [])
                    
                    log(f"Got {len(torrents)} torrents from mylist")
                    
                    found_torrent = False
                    for torrent in torrents:
                        if torrent.get('id') == torrent_id:
                            found_torrent = True
                            log(f"Found torrent in mylist: {torrent.get('name', 'Unknown')}")
                            files = torrent.get('files', [])
                            log(f"Torrent has {len(files)} files")
                            
                            if files:
                                # Find the largest video file
                                video_extensions = ['.mkv', '.mp4', '.avi', '.m4v', '.mov']
                                video_files = [f for f in files if any(f.get('name', '').lower().endswith(ext) for ext in video_extensions)]
                                
                                if not video_files:
                                    video_files = files
                                
                                # Sort by size descending
                                video_files.sort(key=lambda x: x.get('size', 0), reverse=True)
                                largest_file = video_files[0]
                                
                                log(f"Largest video file: {largest_file.get('name', 'Unknown')} ({largest_file.get('size', 0)} bytes)")
                                
                                # === FIXED: Use controltorrent with JSON! ===
                                file_id = largest_file.get('id')
                                if file_id is not None:
                                    log(f"Getting download link for file ID: {file_id}")
                                    
                                    # CRITICAL FIX: Use json= instead of data= for controltorrent!
                                    control_payload = {
                                        'torrent_id': torrent_id,
                                        'operation': 'request_download_link',
                                        'file_id': file_id
                                    }
                                    
                                    log(f"Control torrent request: {control_payload}")
                                    
                                    control_response = requests.post(
                                        f'{self.BASE_URL}/torrents/controltorrent',
                                        headers=headers,
                                        json=control_payload,  # â† FIXED: Use json= not data=!
                                        timeout=self.timeout
                                    )
                                    
                                    log(f"Control torrent response status: {control_response.status_code}")
                                    
                                    control_response.raise_for_status()
                                    control_result = control_response.json()
                                    
                                    log(f"Control torrent response: {control_result}")
                                    
                                    if control_result.get('success'):
                                        download_url = control_result.get('data')
                                        if download_url:
                                            log(f"âœ“ Got download URL: {download_url[:100]}...")
                                            return download_url
                                        else:
                                            log("No download URL in control response")
                                    else:
                                        log(f"Control torrent failed: {control_result}")
                                else:
                                    log("File has no ID field")
                            else:
                                log("No files found in torrent")
                    
                    if not found_torrent:
                        log(f"ERROR: Torrent ID {torrent_id} not found in mylist!")
                else:
                    log("No torrent_id in response")
            else:
                log(f"Torbox API returned success=False: {result}")
            
            return None
            
        except requests.HTTPError as e:
            log_error(f"Torbox HTTP error: {e.response.status_code} - {e.response.text if hasattr(e.response, 'text') else 'No details'}", e)
            return None
        except Exception as e:
            log_error("Failed to unrestrict link with Torbox", e)
            return None


def get_debrid_service():
    """Get configured debrid service instance for magnet fallback (first enabled service)."""
    services = Settings.get_enabled_debrid_services()
    
    if not services:
        return None
    
    service_info = services[0]
    service_name = service_info['name']
    api_key = service_info['api_key']
    
    service_classes = {
        'realdebrid': RealDebrid,
        'torbox': Torbox
    }
    
    service_class = service_classes.get(service_name)
    if service_class:
        return service_class(api_key)
    
    return None


def get_all_debrid_services():
    """Get all enabled debrid service instances."""
    services = Settings.get_enabled_debrid_services()
    instances = []
    
    service_classes = {
        'realdebrid': RealDebrid,
        'torbox': Torbox
    }
    
    for service_info in services:
        service_name = service_info['name']
        api_key = service_info['api_key']
        
        service_class = service_classes.get(service_name)
        if service_class:
            instance = service_class(api_key)
            instance._service_code = service_info['code']
            instance._service_label = service_info['label']
            instances.append(instance)
    
    return instances


def test_debrid_connection():
    """Test all enabled debrid service connections."""
    services = Settings.get_enabled_debrid_services()
    
    if not services:
        return False, "No debrid services enabled. Please enable and configure at least one service."
    
    results = []
    all_success = True
    
    service_classes = {
        'realdebrid': (RealDebrid, "Real-Debrid"),
        'torbox': (Torbox, "Torbox")
    }
    
    for service_info in services:
        service_name = service_info['name']
        api_key = service_info['api_key']
        label = service_info['label']
        
        if service_name not in service_classes:
            continue
        
        service_class, display_name = service_classes[service_name]
        service = service_class(api_key)
        
        success, message = service.test_connection()
        
        if success:
            results.append(f"âœ… {display_name}: {message}")
        else:
            results.append(f"âŒ {display_name}: Failed - {message}")
            all_success = False
    
    if not results:
        return False, "No debrid services configured"
    
    summary = "\n".join(results)
    
    if all_success:
        summary += "\n\nAll services connected! Multi-debrid is active."
    else:
        summary += "\n\nSome services failed. Check API keys."
    
    return all_success, summary


