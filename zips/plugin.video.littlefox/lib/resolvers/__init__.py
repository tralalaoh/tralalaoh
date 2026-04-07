# -*- coding: utf-8 -*-
"""
Resolvers Module - Sub-Resolver Pattern
Stream extraction layer for various video hosts

Architecture Layer: EXTRACTION
"""

from .youtube_resolver import YouTubeResolver

__all__ = ['YouTubeResolver']
