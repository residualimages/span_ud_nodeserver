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

import math,time,datetime
import xml.etree.ElementTree as ET

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom

'''
This is our Panel device node. 
'''
class PanelNode(udi_interface.Node):
    id = 'panel'
    drivers = [
            {'driver': 'TPW', 'value': 0, 'uom': 73},
            {'driver': 'PULSCNT', 'value': 0, 'uom': 56},
            {'driver': 'TIME', 'value': 0, 'uom': 151},
            {'driver': 'ST', 'value': 'Initializing...', 'uom': 145},
            {'driver': 'AWAKE', 'value': 1, 'uom': 2}
            ]

    def __init__(self, polyglot, parent, address, name, spanIPAddress, bearerToken):
        super(PanelNode, self).__init__(polyglot, parent, address, name)

        # set a flag to short circuit setDriver() until the node has been fully
        # setup in the Polyglot DB and the ISY (as indicated by START event)
        self._initialized: bool = False
        
        self.poly = polyglot

        self.Parameters = Custom(polyglot, 'customparams')
        self.ipAddress = spanIPAddress
        self.token = bearerToken
        tokenLastTen = self.token[-10:]
        LOGGER.debug("IP Address:" + self.ipAddress + "; Bearer Token (last 10 characters): " + tokenLastTen)

        spanConnection = http.client.HTTPConnection(self.ipAddress)
        payload = ''
        headers = {
            "Authorization": "Bearer " + self.token
        }
        spanConnection.request("GET", "/api/v1/status", payload, headers)

        statusResponse = spanConnection.getresponse()
        statusData = statusResponse.read()
        statusData = statusData.decode("utf-8")

        LOGGER.info("\nStatus Data: \n\t\t" + statusData + "\n")

        spanConnection.request("GET", "/api/v1/circuits", payload, headers)

        circuitsResponse = spanConnection.getresponse()
        circuitsData = circuitsResponse.read()
        circuitsData = circuitsData.decode("utf-8")
        
        LOGGER.info("\nCircuits Data: \n\t\t" + circuitsData + "\n\t\tCount of circuits: " + str(circuitsData.count('id:')) + "\n")
        self.setDriver('PULSCNT', circuitsData.count('id:'), True, True)

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
    #def setDriver(self, driver: str, value: Any, report: bool=True, force: bool=False, uom: Optional[int]=None):
    #    if self._initialized:
    #        super().setDriver(driver, value, report, force, uom)

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
            if self.getDriver('AWAKE') == 1:
                # back when the PULSCNT was being used to increment and show if Querying was Active vs Inactive (via AWAKE)...
                # currentCount = self.getDriver('PULSCNT')
                # currentCount = int(currentCount)
                # currentCount += 1
                # self.setDriver('PULSCNT', currentCount, True, True)
                # LOGGER.info('Current PULSCNT for polling on {} is {}'.format(self.name,currentCount))
                tokenLastTen = self.token[-10:]
                LOGGER.info('About to query Panel node of {}, using token ending in {}'.format(self.ipAddress,tokenLastTen))
        
                spanConnection = http.client.HTTPConnection(self.ipAddress)
                payload = ''
                headers = {
                    "Authorization": "Bearer " + self.token
                }
                spanConnection.request("GET", "/api/v1/panel", payload, headers)
        
                panelResponse = spanConnection.getresponse()
                panelData = panelResponse.read()
                panelData = panelData.decode("utf-8")
                LOGGER.info("\nPanel Data: \n\t\t" + panelData + "\n")
               
                #panelDataAsXml = ET.fromstring(panelData)
                #LOGGER.info('panelDataAsXml: {}'.format(panelDataAsXml))
                #feedthroughPowerW = panelDataAsXml.find('feedthroughPowerW')
                
                feedthroughPowerW_tuple = panelData.partition("feedthroughPowerW")
                feedthroughPowerW = feedthroughPowerW_tuple[2]
                LOGGER.debug("\n\t\t1st level Parsed feedthroughPowerW:\t" + feedthroughPowerW + "\n")
                feedthroughPowerW_tuple = feedthroughPowerW.partition(",")
                feedthroughPowerW = feedthroughPowerW_tuple[0]
                LOGGER.debug("\n\t\t2nd level Parsed feedthroughPowerW:\t" + feedthroughPowerW + "\n")
                feedthroughPowerW_tuple = feedthroughPowerW.partition(":")
                feedthroughPowerW = feedthroughPowerW_tuple[2]
                LOGGER.debug("\n\t\t3rd level Parsed feedthroughPowerW:\t" + feedthroughPowerW + "\n")                
                feedthroughPowerW = math.ceil(float(feedthroughPowerW)*100)/100

                instantGridPowerW_tuple = panelData.partition("instantGridPowerW")
                instantGridPowerW = instantGridPowerW_tuple[2]
                LOGGER.debug("\n\t\t1st level Parsed instantGridPowerW:\t" + instantGridPowerW + "\n")
                instantGridPowerW_tuple = instantGridPowerW.partition(",")
                instantGridPowerW = instantGridPowerW_tuple[0]
                LOGGER.debug("\n\t\t2nd level Parsed instantGridPowerW:\t" + instantGridPowerW + "\n")
                instantGridPowerW_tuple = instantGridPowerW.partition(":")
                instantGridPowerW = instantGridPowerW_tuple[2]
                LOGGER.debug("\n\t\t3rd level Parsed instantGridPowerW:\t" + instantGridPowerW + "\n")                
                instantGridPowerW = math.ceil(float(instantGridPowerW)*100)/100
                LOGGER.info("\n\t\tFinal Level Parsed and rounded instantGridPowerW:\t" + str(instantGridPowerW) + "\n")
                LOGGER.info("\n\t\tFinal Level Parsed and rounded feedthroughPowerW:\t" + str(feedthroughPowerW) + "\n")
                self.setDriver('TPW', (instantGridPowerW-abs(feedthroughPowerW)), True, True)
                if len(str(instantGridPowerW)) > 0:
                    self.setDriver('TIME', int(time.time()), True, True)
                    self.setDriver('ST', datetime.datetime.fromtimestamp(int(time.time())), True, True)
            else:
                tokenLastTen = self.token[-10:]
                LOGGER.info('\n\t\tSkipping query of Panel node {}, using token {}'.format(self.ipAddress,tkenLastToken))
                self.setDriver('ST', "Not Actively Querying" , True, True)
            
    def toggle_monitoring(self,val):
        # On startup this will always go back to true which is the default, but how do we restore the previous user value?
        LOGGER.debug(f'{self.address} val={val}')
        self.setDriver('AWAKE', val, True, True)

    def cmd_toggle_monitoring(self,val):
        val = self.getDriver('AWAKE')
        LOGGER.debug(f'{self.address} val={val}')
        if val == 1:
            val = 0
        else:
            val = 1
        self.toggle_monitoring(val)

    commands = {
        "TOGGLE_MONITORING": cmd_toggle_monitoring,
    }
