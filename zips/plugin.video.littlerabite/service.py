# -*- coding: utf-8 -*-
"""
Little Rabite Service Entry Point
Initializes the database and runs the monitoring loop.
Based on TMDbHelper's service architecture.
"""

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import sys
import os

# Add lib directory to path
addon = xbmcaddon.Addon()
addon_path = xbmcvfs.translatePath(addon.getAddonInfo('path'))
lib_path = os.path.join(addon_path, 'resources', 'lib')
sys.path.insert(0, lib_path)

from resources.lib.database import get_database
from resources.lib.monitor import ServiceMonitor


class LittleRabiteService:
    """
    Main service class for Little Rabite.
    Handles initialization and lifecycle management.
    """
    
    def __init__(self):
        """Initialize the service."""
        self.addon = xbmcaddon.Addon()
        self.addon_id = self.addon.getAddonInfo('id')
        self.addon_name = self.addon.getAddonInfo('name')
        self.addon_version = self.addon.getAddonInfo('version')
        
        self.log(f'Starting {self.addon_name} v{self.addon_version}')
        
        # Initialize database
        try:
            self.db = get_database()
            self.log('Database initialized successfully')
            
            # Log database stats
            stats = self.db.get_stats()
            self.log(f"Database stats: {stats['in_progress']} in progress, "
                    f"{stats['completed']} completed, "
                    f"{stats['authenticated_services']} services authenticated")
        except Exception as e:
            self.log(f'Failed to initialize database: {str(e)}', xbmc.LOGERROR)
            raise
        
        # Initialize monitor
        self.monitor = None
    
    def run(self):
        """
        Main service loop.
        Initializes the monitor and keeps service alive.
        """
        try:
            # Set service started property
            xbmcgui.Window(10000).setProperty('LittleRabite.ServiceStarted', 'true')
            
            # Initialize and start the service monitor
            self.monitor = ServiceMonitor(self.db)
            self.log('Service monitor initialized')
            
            # Run the monitor loop
            self.monitor.run()
            
        except Exception as e:
            self.log(f'Service error: {str(e)}', xbmc.LOGERROR)
            import traceback
            self.log(traceback.format_exc(), xbmc.LOGERROR)
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup before service shutdown."""
        self.log('Service shutting down...')
        
        # Clear service started property
        xbmcgui.Window(10000).clearProperty('LittleRabite.ServiceStarted')
        
        # Cleanup monitor if it exists
        if self.monitor:
            try:
                self.monitor.cleanup()
            except Exception as e:
                self.log(f'Error during monitor cleanup: {str(e)}', xbmc.LOGERROR)
        
        # Vacuum database periodically (on shutdown)
        try:
            self.db.vacuum()
            self.log('Database vacuumed')
        except Exception as e:
            self.log(f'Database vacuum failed: {str(e)}', xbmc.LOGWARNING)
        
        self.log('Service stopped')
    
    def log(self, message, level=xbmc.LOGINFO):
        """
        Log a message to Kodi log.
        
        Args:
            message: Message to log
            level: Log level
        """
        xbmc.log(f'[{self.addon_name}] {message}', level)


def main():
    """Main entry point for the service."""
    try:
        service = LittleRabiteService()
        service.run()
    except Exception as e:
        xbmc.log(f'[Little Rabite] Fatal error: {str(e)}', xbmc.LOGERROR)
        import traceback
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)


if __name__ == '__main__':
    main()
