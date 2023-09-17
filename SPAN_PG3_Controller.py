#!/usr/bin/env python3
"""
Polyglot v3 node server SPAN Smart Panels
Copyright (C) 2023 Matt Burke

MIT License
"""
import udi_interface
import sys
from nodes import count_ctl

LOGGER = udi_interface.LOGGER

if __name__ == "__main__":
    try:
        polyglot = udi_interface.Interface([])
        polyglot.start()

        # Create the controller node
        count_ctl.Controller(polyglot, 'controller', 'controller', 'SPAN Smart Panels')

        # Just sit and wait for events
        polyglot.runForever()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
        

