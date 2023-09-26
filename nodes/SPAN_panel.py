#!/usr/bin/env python3
"""
Polyglot v3 node server SPAN Smart Panels
Copyright (C) 2023 Matt Burke

MIT License
"""
import udi_interface
import sys
import http.client

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom

'''
This is our Panel device node. 
'''
class PanelNode(udi_interface.Node):
    id = 'panel'
    drivers = [
            {'driver': 'ST', 'value': 1, 'uom': 2},
            {'driver': 'GV0', 'value': 0, 'uom': 56},
            {'driver': 'GV1', 'value': 0, 'uom': 56},
            {'driver': 'GV2', 'value': 1, 'uom': 2}
            ]

    def __init__(self, polyglot, parent, address, name, spanIPAddress, bearerToken):
        super(PanelNode, self).__init__(polyglot, parent, address, name)

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

        LOGGER.info("Status Data: \n" + statusData + "\n")

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
    Then display a notice on the dashboard.
    '''
    def poll(self, polltype):

        if 'shortPoll' in polltype:
            if int(self.getDriver('GV2')) == 1:
                LOGGER.debug(f'{self.name} Polling...')
                
                self.count += 1

                self.setDriver('GV0', self.count, True, True)
                self.setDriver('GV1', (self.count * mult), True, True)

                # be fancy and display a notice on the polyglot dashboard
                self.poly.Notices[self.name] = '{}: Current polling count is {}'.format(self.name, self.count)
            else:
                LOGGER.debug(f'{self.name} NOT Incrementing poll count...')

    def set_increment(self,val=None):
        # On startup this will always go back to true which is the default, but how do we restort the previous user value?
        LOGGER.debug(f'{self.address} val={val}')
        self.setDriver('GV2',val)

    def cmd_set_increment(self,command):
        val = int(command.get('value'))
        LOGGER.debug(f'{self.address} val={val}')
        self.set_increment(val)

    commands = {
        "SET_INCREMENT": cmd_set_increment,
    }
