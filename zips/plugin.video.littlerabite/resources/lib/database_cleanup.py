# -*- coding: utf-8 -*-
"""
Database Cleanup Utilities
Tools for cleaning up and managing Continue Watching database.
"""

import sqlite3
import json
import time

try:
    import xbmc
    KODI_ENV = True
except ImportError:
    KODI_ENV = False


def deduplicate_continue_watching(db):
    """
    Remove duplicate entries from Continue Watching.
    
    Duplicates are items with:
    - Same media type (movie/episode)
    - Matching service IDs (any shared ID)
    - Same season/episode (for TV shows)
    
    Keeps the entry with:
    - Most recent last_watched_at
    - Highest progress
    - Most complete set of IDs
    
    Args:
        db: Database instance
        
    Returns:
        int: Number of duplicates removed
    """
    def log(msg):
        if KODI_ENV:
            xbmc.log(f'[LittleRabite-Cleanup] {msg}', xbmc.LOGINFO)
        else:
            print(f'[Cleanup] {msg}')
    
    log('Starting deduplication...')
    
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    removed = 0
    
    try:
        # Get all Continue Watching items
        cursor.execute("""
            SELECT * FROM progress 
            WHERE completed = 0 AND progress > 0
            ORDER BY last_watched_at DESC
        """)
        
        items = [dict(row) for row in cursor.fetchall()]
        
        log(f'Found {len(items)} items in Continue Watching')
        
        # Track which items to keep
        keep_ids = set()
        remove_ids = set()
        
        # Group items by potential duplicates
        for i, item in enumerate(items):
            if item['id'] in remove_ids:
                continue  # Already marked for removal
            
            if item['id'] in keep_ids:
                continue  # Already keeping this one
            
            item_ids = json.loads(item['service_ids'])
            media_type = item['type']
            season = item.get('season')
            episode = item.get('episode')
            
            # Find all duplicates of this item
            duplicates = [item]  # Include self
            
            for j, other in enumerate(items):
                if i == j:
                    continue
                
                if other['id'] in remove_ids or other['id'] in keep_ids:
                    continue
                
                # Check if duplicate
                if other['type'] != media_type:
                    continue
                
                # For episodes, must match season/episode
                if media_type == 'episode':
                    if other.get('season') != season or other.get('episode') != episode:
                        continue
                
                # Check for ID intersection
                other_ids = json.loads(other['service_ids'])
                
                has_match = False
                for key in item_ids:
                    if key in other_ids:
                        if str(item_ids[key]) == str(other_ids[key]):
                            has_match = True
                            break
                
                if has_match:
                    duplicates.append(other)
            
            if len(duplicates) > 1:
                # Found duplicates! Choose which to keep
                log(f'Found {len(duplicates)} duplicates of: {item["title"]}')
                
                # Sort by:
                # 1. Most recent last_watched_at
                # 2. Highest progress
                # 3. Most IDs
                duplicates.sort(key=lambda x: (
                    x['last_watched_at'] or 0,
                    x['progress'] or 0,
                    len(json.loads(x['service_ids']))
                ), reverse=True)
                
                # Keep the first one
                best = duplicates[0]
                keep_ids.add(best['id'])
                
                # Merge all IDs into the best one
                merged_ids = {}
                for dup in duplicates:
                    dup_ids = json.loads(dup['service_ids'])
                    merged_ids.update(dup_ids)
                
                # Update the best entry with merged IDs
                cursor.execute("""
                    UPDATE progress 
                    SET service_ids = ?
                    WHERE id = ?
                """, (json.dumps(merged_ids), best['id']))
                
                log(f'Keeping ID {best["id"]}: {best["title"]} ({best["progress"]}%)')
                log(f'Merged IDs: {merged_ids}')
                
                # Mark others for removal
                for dup in duplicates[1:]:
                    remove_ids.add(dup['id'])
                    log(f'Removing duplicate ID {dup["id"]}: {dup["title"]} ({dup["progress"]}%)')
            else:
                # No duplicates, keep it
                keep_ids.add(item['id'])
        
        # Remove the duplicates
        if remove_ids:
            remove_list = ','.join(str(id) for id in remove_ids)
            cursor.execute(f"DELETE FROM progress WHERE id IN ({remove_list})")
            removed = len(remove_ids)
            log(f'Removed {removed} duplicate entries')
        
        conn.commit()
        log('Deduplication complete!')
        
    except Exception as e:
        log(f'Deduplication error: {str(e)}')
        conn.rollback()
        raise
    finally:
        conn.close()
    
    return removed


def remove_from_continue_watching(db, item_id):
    """
    Remove a specific item from Continue Watching.
    
    Args:
        db: Database instance
        item_id: Database ID of item to remove
        
    Returns:
        bool: True if removed
    """
    try:
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        
        # Just delete the item
        cursor.execute("DELETE FROM progress WHERE id = ?", (item_id,))
        
        conn.commit()
        conn.close()
        
        if KODI_ENV:
            xbmc.log(f'[LittleRabite-Cleanup] Removed item {item_id} from Continue Watching', xbmc.LOGINFO)
        
        return True
        
    except Exception as e:
        if KODI_ENV:
            xbmc.log(f'[LittleRabite-Cleanup] Error removing item: {str(e)}', xbmc.LOGERROR)
        return False


def clear_continue_watching(db):
    """
    Clear ALL items from Continue Watching.
    
    This deletes all incomplete items but preserves completed ones.
    
    Args:
        db: Database instance
        
    Returns:
        int: Number of items cleared
    """
    try:
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        
        # Count items to be deleted
        cursor.execute("SELECT COUNT(*) FROM progress WHERE completed = 0 AND progress > 0")
        count = cursor.fetchone()[0]
        
        # Delete all incomplete items
        cursor.execute("DELETE FROM progress WHERE completed = 0 AND progress > 0")
        
        conn.commit()
        conn.close()
        
        if KODI_ENV:
            xbmc.log(f'[LittleRabite-Cleanup] Cleared {count} items from Continue Watching', xbmc.LOGINFO)
        
        return count
        
    except Exception as e:
        if KODI_ENV:
            xbmc.log(f'[LittleRabite-Cleanup] Error clearing: {str(e)}', xbmc.LOGERROR)
        return 0


def get_duplicate_count(db):
    """
    Count how many duplicates exist.
    
    Args:
        db: Database instance
        
    Returns:
        int: Number of duplicate entries
    """
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Get all Continue Watching items
        cursor.execute("""
            SELECT * FROM progress 
            WHERE completed = 0 AND progress > 0
        """)
        
        items = [dict(row) for row in cursor.fetchall()]
        
        seen = set()
        duplicates = 0
        
        for item in items:
            item_ids = json.loads(item['service_ids'])
            media_type = item['type']
            season = item.get('season')
            episode = item.get('episode')
            
            # Create a signature for this item
            signature = f"{media_type}"
            if media_type == 'episode':
                signature += f":{season}:{episode}"
            
            # Add all IDs to signature
            id_parts = []
            for key in sorted(item_ids.keys()):
                id_parts.append(f"{key}={item_ids[key]}")
            signature += ":" + ":".join(id_parts)
            
            if signature in seen:
                duplicates += 1
            else:
                seen.add(signature)
        
        return duplicates
        
    finally:
        conn.close()
