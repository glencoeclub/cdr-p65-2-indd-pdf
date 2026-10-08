#!/usr/bin/env python3
"""
Backward-compatibility shim for p65_parser.

The actual parser classes have been refactored into pagemaker_parser.py.
This module re-exports P65Parser so existing code continues to work.
"""

from pagemaker_parser import P65Parser, PageMakerBaseParser, OLEFILE_AVAILABLE

__all__ = ['P65Parser', 'PageMakerBaseParser', 'OLEFILE_AVAILABLE']
