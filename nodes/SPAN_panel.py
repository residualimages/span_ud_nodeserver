#!/usr/bin/env python3
"""
Polyglot v3 node server SPAN Smart Panels
Copyright (C) 2023 Matt Burke

MIT License
"""
import udi_interface
import sys
import http.client

# Standard Library
from typing import Optional, Any, TYPE_CHECKING

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom

'''
This is our Panel device node. 
'''
class PanelNode(udi_interface.Node):
    id = 'panel'
    drivers = [
            {'driver': 'ST', 'value': 1, 'uom': 2},
            {'driver': 'GV0', 'value': 1, 'uom': 56},
            {'driver': 'GV1', 'value': 1, 'uom': 2}
            ]

    def __init__(self, polyglot, parent, address, name, spanIPAddress, bearerToken):
        super(PanelNode, self).__init__(polyglot, parent, address, name)

        # set a flag to short circuit setDriver() until the node has been fully
        # setup in the Polyglot DB and the ISY (as indicated by START event)
        self._initialized: bool = False
        
        self.poly = polyglot
        self.count = 0

        self.Parameters = Custom(polyglot, 'customparams')
        
        LOGGER.debug("IP Address:" + spanIPAddress + "; Bearer Token: " + bearerToken)

        spanConnection = http.client.HTTPConnection(spanIPAddress)
        payload = ''
        headers = {
            "Authorization": "Bearer " + bearerToken
        }
        spanConnection.request("GET", "/api/v1/status", payload, headers)

        statusResponse = spanConnection.getresponse()
        statusData = statusResponse.read()
        statusData = statusData.decode("utf-8")

        LOGGER.info("\nStatus Data: \n\t\t" + statusData + "\n")

        # subscribe to the events we want
        polyglot.subscribe(polyglot.CUSTOMPARAMS, self.parameterHandler)
        polyglot.subscribe(polyglot.POLL, self.poll)
        
    # called by the interface after the node data has been put in the Polyglot DB
    # and the node created/updated in the ISY
    def start(self):
        # set the initlized flag to allow setDriver to work
        self._initialized = True
    
    # overload the setDriver() of the parent class to short circuit if 
    # node not initialized
    def setDriver(self, driver: str, value: Any, report: bool=True, force: bool=False, uom: Optional[int]=None):
        if self._initialized:
            super().setDriver(driver, value, report, force, uom)

    '''
    Read the user entered custom parameters.
    '''
    def parameterHandler(self, params):
        self.Parameters.load(params)

    '''
    This is where the real work happens.  When we get a shortPoll, do some work. 
    '''
    def poll(self, polltype):
        if 'shortPoll' in polltype:
            currentCount = self.getDriver('GV0')
            currentCount += 1
            self.setDriver('GV0', currentCount, 56, True)
            
            LOGGER.info('Current GV0 for polling is {}'.format(currentCount))
            
            self.count += 1
            LOGGER.info('Current self.count for polling is {}'.format(self.count))
          
            # be fancy and display a notice on the polyglot dashboard
            # self.poly.Notices[self.name] = '{}: Current polling count is {}'.format(self.name, self.count)

    def toggle_monitoring(self,val):
        # On startup this will always go back to true which is the default, but how do we restore the previous user value?
        LOGGER.debug(f'{self.address} val={val}')
        self.setDriver('GV1', val, 2, True)

    def cmd_toggle_monitoring(self,val):
        val = self.getDriver('GV1')
        LOGGER.debug(f'{self.address} val={val}')
        if val == 1:
            val = 0
        else:
            val = 1
        self.toggle_monitoring(val)

    commands = {
        "TOGGLE_MONITORING": cmd_toggle_monitoring,
    }
