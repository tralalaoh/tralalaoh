#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
🦝 Little Racun - Entry Point
Minimal entry point that delegates to the plugin module.
"""

import sys
from resources.lib.router import route

if __name__ == '__main__':
    route(sys.argv)
