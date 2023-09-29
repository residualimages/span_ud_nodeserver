#!/usr/bin/env python3
"""
Polyglot v3 node server SPAN Smart Panels
Copyright (C) 2023 Matt Burke

MIT License
"""
import udi_interface
import sys
import http.client

from nodes import SPAN_panel

# Standard Library
from typing import Optional, Any, TYPE_CHECKING

import math,time,datetime
import xml.etree.ElementTree as ET

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom

'''
This is our Circuit device node. 
'''
class CircuitNode(udi_interface.Node):
    id = 'circuit'
    drivers = [
            {'driver': 'TPW', 'value': 0, 'uom': 73},
            {'driver': 'PULSCNT', 'value': 0, 'uom': 56},
            {'driver': 'CLIEMD', 'value': 0, 'uom': 25},
            {'driver': 'TIME', 'value': 0, 'uom': 151},
            {'driver': 'ST', 'value': 'Initializing...', 'uom': 145},
            {'driver': 'AWAKE', 'value': 1, 'uom': 2},
            {'driver': 'GV1', 'value': 'N/A', 'uom': 56},
            {'driver': 'GV2', 'value': 'N/A', 'uom': 56},
            {'driver': 'GV3', 'value': 'N/A', 'uom': 56},
            {'driver': 'GV4', 'value': 'N/A', 'uom': 56}
            ]

    def __init__(self, polyglot, parent, address, name, spanIPAddress, bearerToken, spanCircuitID):
        super(CircuitNode, self).__init__(polyglot, parent, address, name)

        # set a flag to short circuit setDriver() until the node has been fully
        # setup in the Polyglot DB and the ISY (as indicated by START event)
        self._initialized: bool = False
        
        self.poly = polyglot
        self.n_queue = []

        self.Parameters = Custom(polyglot, 'customparams')
        self.ipAddress = spanIPAddress
        self.token = bearerToken
        self.circuitID = spanCircuitID
        tokenLastTen = self.token[-10:]
        LOGGER.debug("IP Address for circuit:" + self.ipAddress + "; Bearer Token (last 10 characters): " + tokenLastTen + "; Circuit ID: " + self.circuitID)

        spanConnection = http.client.HTTPConnection(self.ipAddress)
        payload = ''
        headers = {
            "Authorization": "Bearer " + self.token
        }
     
        LOGGER.debug("\nAbout to query " + self.ipAddress + "/api/v1/circuits/" + self.circuitID + "\n")
        spanConnection.request("GET", "/api/v1/circuits/" + self.circuitID, payload, headers)

        designatedCircuitResponse = spanConnection.getresponse()
        designatedCircuitData = designatedCircuitResponse.read()
        designatedCircuitData = designatedCircuitData.decode("utf-8")

        if "name" in designatedCircuitData:
            designatedCircuitTabs_tuple = designatedCircuitData.partition(chr(34) + "tabs" + chr(34) + ":")
            designatedCircuitTabs = designatedCircuitTabs_tuple[2]
            designatedCircuitTabs_tuple = designatedCircuitTabs.partition("],")
            designatedCircuitTabs = designatedCircuitTabs_tuple[0]
          
            LOGGER.info("\nDesignated Circuit Data: \n\t\t" + designatedCircuitData + "\n\t\tCount of Circuit Breakers In Circuit: " + str(designatedCircuitTabs.count(',')+1) + "\n")
            self.setDriver('PULSCNT', (designatedCircuitTabs.count(',')+1), True, True)
    
            LOGGER.debug("\nTabs data:\n\t\t" + designatedCircuitTabs + "\n")
        else:
            LOGGER.warning("\nINIT Issue getting data for circuit '" + self.circuitID + "'.\n")
          
        # subscribe to the events we want
        #polyglot.subscribe(polyglot.CUSTOMPARAMS, self.parameterHandler)
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
                LOGGER.info('About to query {} Circuit node of {}, using token ending in {}'.format(self.circuitID,self.ipAddress,tokenLastTen))
        
                spanConnection = http.client.HTTPConnection(self.ipAddress)
                payload = ''
                headers = {
                    "Authorization": "Bearer " + self.token
                }
                spanConnection.request("GET", "/api/v1/circuit/" + self.circuitID, payload, headers)
        
                designatedCircuitResponse = spanConnection.getresponse()
                designatedCircuitData = designatedCircuitResponse.read()
                designatedCircuitData = designatedCircuitData.decode("utf-8")
                LOGGER.info("\nCircuit Data: \n\t\t" + designatedCircuitData + "\n")

                if "name" in designatedCircuitData:
                    designatedCircuitStatus_tuple = designatedCircuitData.partition(chr(34) + "relayState" + chr(34) + ":")
                    designatedCircuitStatus = designatedCircuitStatus_tuple[2]
                    designatedCircuitStatus_tuple = designatedCircuitStatus.partition(',')
                    designatedCircuitStatus = designatedCircuitStatus_tuple[0]
    
                    designatedCircuitInstantPowerW_tuple = designatedCircuitData.partition(chr(34) + "instantPowerW" + chr(34) + ":")
                    designatedCircuitInstantPowerW = designatedCircuitInstantPowerW_tuple[2]
                    designatedCircuitInstantPowerW_tuple = designatedCircuitInstantPowerW.partition(',')
                    designatedCircuitInstantPowerW = designatedCircuitInstantPowerW_tuple[0]
                    designatedCircuitInstantPowerW = math.ceil(float(designatedCircuitInstantPowerW)*100)/100
                  
                    if designatedCircuitStatus == "CLOSED":
                      self.setDriver('CLIEMD', 2, True, True)
                    elif designatedCircuitStatus == "OPEN":
                      self.setDriver('CLIEMD', 1, True, True)
                    else:
                      self.setDriver('CLIEMD', 0, True, True)
                    
                    self.setDriver('TPW', abs(designatedCircuitInstantPowerW), True, True)
                else:
                    LOGGER.warning("\nPOLL Issue getting data for circuit '" + self.circuitID + "'.\n")
            else:
                LOGGER.debug("\n\t\tSkipping POLL query of Circuit node '" + self.circuitID + "' due to AWAKE=0.\n")
                self.setDriver('ST', "Not Actively Querying" , True, True)

    def toggle_circuit_monitoring(self,val):
        # On startup this will always go back to true which is the default, but how do we restore the previous user value?
        LOGGER.debug(f'{self.address} val={val}')
        self.setDriver('AWAKE', val, True, True)

    def cmd_toggle_circuit_monitoring(self,val):
        val = self.getDriver('AWAKE')
        LOGGER.debug(f'{self.address} val={val}')
        if val == 1:
            val = 0
        else:
            val = 1
        self.toggle_circuit_monitoring(val)

    commands = {
        "TOGGLE_CIRCUIT_MONITORING": cmd_toggle_circuit_monitoring,
    }
