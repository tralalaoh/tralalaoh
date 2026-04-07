"""Custom Stremio scraper manager dialog."""

import xbmc
import xbmcgui

from resources.lib.addon_registry import AddonRegistry
from resources.lib.logger import log, log_error

TITLE = 'Little Tigre - Custom Scrapers'


class AddonManagerDialog:
    """
    Kodi dialog UI for managing unlimited custom Stremio scrapers.

    - Add any Stremio-compatible addon by pasting its manifest URL
    - Auto-detects addon name, supported content types, and ID formats
    - Enable / disable / rename / remove scrapers at any time
    - All scrapers are queried alongside the built-in ones on every playback
    """

    def show(self):
        """Main loop — keeps showing the list until the user presses Back."""
        while True:
            addons = AddonRegistry.get_all()
            items, labels = self._build_list(addons)

            choice = xbmcgui.Dialog().select(
                f"{TITLE}  ({len(addons)} scrapers)",
                labels
            )

            if choice < 0:
                break
            elif choice == len(addons):
                # Last item is always "Add New"
                self._add_new()
            else:
                self._manage_existing(addons[choice])

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_list(self, addons):
        """Build display list. Returns (addons, label_strings)."""
        labels = []
        for addon in addons:
            enabled = addon.get('enabled', True)
            status = '[COLOR green]ON [/COLOR]' if enabled else '[COLOR gray]OFF[/COLOR]'
            types = ', '.join(addon.get('types', ['movie', 'series']))
            prefixes = ', '.join(addon.get('id_prefixes', ['tt']))
            labels.append(f"[{status}]  {addon['name']}  —  {types}  |  IDs: {prefixes}")

        labels.append('[COLOR gold][ + Add New Scraper ][/COLOR]')
        return addons, labels

    def _add_new(self):
        """Prompt for a URL, fetch the manifest, confirm, and save."""
        dialog = xbmcgui.Dialog()

        url = dialog.input(
            'Paste the Stremio addon manifest URL\n'
            'e.g.  https://my.addon.com/config123/manifest.json',
            type=xbmcgui.INPUT_ALPHANUM
        )

        if not url or not url.strip():
            return

        # Fetch manifest with progress indicator
        progress = xbmcgui.DialogProgress()
        progress.create('Little Tigre', 'Fetching addon manifest...')
        progress.update(20, 'Connecting...')

        try:
            manifest = AddonRegistry.fetch_manifest(url.strip())
        except Exception as e:
            log_error('AddonManager: Unexpected error fetching manifest', e)
            manifest = None
        finally:
            progress.close()

        if not manifest:
            dialog.ok(
                'Little Tigre',
                'Could not fetch the manifest.\n\n'
                'Make sure:\n'
                '  • The URL is correct and the addon is online\n'
                '  • Paste the full manifest URL ending in /manifest.json\n'
                '    or the addon base URL\n\n'
                'Example:\n'
                '  https://comet.elfhosted.com/abc123/manifest.json'
            )
            return

        # Show detected info and ask user to confirm
        types_str = ', '.join(manifest.get('types', []))
        prefixes_str = ', '.join(manifest.get('id_prefixes', []))
        version_str = f"  v{manifest['version']}" if manifest.get('version') else ''

        confirmed = dialog.yesno(
            'Addon Detected — Add?',
            f"Name:    {manifest['name']}{version_str}\n"
            f"URL:     {manifest['base_url']}\n"
            f"Types:   {types_str}\n"
            f"IDs:     {prefixes_str}\n\n"
            f"Add this scraper to Little Tigre?"
        )

        if not confirmed:
            return

        # Let user rename (optional)
        custom_name = dialog.input(
            'Scraper name  (leave unchanged or type a custom name)',
            defaultt=manifest['name'],
            type=xbmcgui.INPUT_ALPHANUM
        )
        if custom_name and custom_name.strip():
            manifest['name'] = custom_name.strip()

        entry, error = AddonRegistry.add(manifest)

        if error == 'already_exists':
            dialog.ok('Little Tigre', 'This addon is already in your scraper list.')
        elif entry:
            dialog.notification(
                'Little Tigre',
                f"'{entry['name']}' added!",
                xbmcgui.NOTIFICATION_INFO,
                3000
            )
            log(f"AddonManager: Added scraper '{entry['name']}'")
        else:
            dialog.ok('Little Tigre', 'Failed to save. Check Kodi logs.')

    def _manage_existing(self, addon):
        """Show options dialog for an existing addon."""
        dialog = xbmcgui.Dialog()
        enabled = addon.get('enabled', True)
        name = addon['name']

        options = [
            'Disable' if enabled else 'Enable',
            'Rename',
            'View Details',
            '[COLOR red]Remove[/COLOR]',
        ]

        choice = dialog.select(f"  {name}", options)

        if choice == 0:
            new_state = AddonRegistry.toggle(addon['id'])
            if new_state is not None:
                state_label = 'enabled' if new_state else 'disabled'
                dialog.notification(
                    'Little Tigre',
                    f"'{name}' {state_label}",
                    xbmcgui.NOTIFICATION_INFO,
                    2000
                )

        elif choice == 1:
            new_name = dialog.input(
                'New name',
                defaultt=name,
                type=xbmcgui.INPUT_ALPHANUM
            )
            if new_name and new_name.strip() and new_name.strip() != name:
                AddonRegistry.update_name(addon['id'], new_name)
                dialog.notification('Little Tigre', f"Renamed to '{new_name.strip()}'",
                                    xbmcgui.NOTIFICATION_INFO, 2000)

        elif choice == 2:
            self._show_details(addon)

        elif choice == 3:
            confirmed = dialog.yesno(
                'Remove Scraper',
                f"Remove '{name}' from your scraper list?\n\nThis cannot be undone."
            )
            if confirmed:
                AddonRegistry.remove(addon['id'])
                dialog.notification(
                    'Little Tigre',
                    f"'{name}' removed",
                    xbmcgui.NOTIFICATION_INFO,
                    2000
                )

    def _show_details(self, addon):
        """Show full addon details in a text viewer."""
        enabled = addon.get('enabled', True)
        version = f"v{addon['version']}" if addon.get('version') else 'unknown'
        types = ', '.join(addon.get('types', []))
        prefixes = ', '.join(addon.get('id_prefixes', []))

        xbmcgui.Dialog().textviewer(
            addon['name'],
            f"Name:      {addon['name']}\n"
            f"Version:   {version}\n"
            f"Status:    {'Enabled' if enabled else 'Disabled'}\n"
            f"Types:     {types}\n"
            f"IDs:       {prefixes}\n"
            f"Added:     {addon.get('added_at', 'unknown')}\n\n"
            f"Base URL:\n{addon.get('base_url', '')}\n\n"
            f"Manifest URL:\n{addon.get('manifest_url', '')}"
        )
