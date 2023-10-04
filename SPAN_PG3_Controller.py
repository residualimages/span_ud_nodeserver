#!/usr/bin/env python3
"""
Polyglot v3 node server SPAN Smart Panels
Copyright (C) 2023 Matt Burke

MIT License
"""
import udi_interface
import sys
import time
import string
import re

from nodes import SPAN_ctl

import urllib.parse,http.client,math,time,datetime,base64

LOGGER = udi_interface.LOGGER

if __name__ == "__main__":
    try:
        polyglot = udi_interface.Interface([])
        polyglot.start()

        nodes = polyglot.getNodes()
        allNodesString = ''
        for node in nodes:
            allNodesString = allNodesString + '\t\t' + node + '\n'
            
        LOGGER.debug("\n\n\tAll Nodes under root polyglot object:\n" + allNodesString + "\n")

        # Create the controller node if not created
        nodes = polyglot.getNodes()
        if 'controller' not in nodes:
            SPAN_ctl.Controller(polyglot, 'controller', 'controller', 'SPAN Panel - Nodeserver')
            LOGGER.warning("\n\tNodeServer's root 'controller' node does NOT exist. Creating...\n")
        else:
            LOGGER.debug("\n\tNodeServer's root 'controller' node DOES exist. Attempting to publish a 'GPV' NodeServer Message to IoX...\n")
            nodes['controller'].pushTextToDriver('GPV','NodeServer STARTING')

        # Just sit and wait for events
        polyglot.runForever()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
        

