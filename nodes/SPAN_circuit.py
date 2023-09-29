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
This is our Circuit device node. 
'''
class CircuitNode(udi_interface.Node):
    id = 'circuit'
    drivers = [
            {'driver': 'ST', 'value': 0, 'uom': 73},
            {'driver': 'PULSCNT', 'value': 0, 'uom': 56},
            {'driver': 'CLIEMD', 'value': 0, 'uom': 25},
            {'driver': 'TIME', 'value': 0, 'uom': 151},
            {'driver': 'TIMEREM', 'value': 'Initializing...', 'uom': 145},
            {'driver': 'AWAKE', 'value': 1, 'uom': 2},
            {'driver': 'GPV', 'value': '???', 'uom': 145},
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
        #self.n_queue = []

        LOGGER.debug("\n\tINIT Span Circuit's parent is '" + parent + "' when INIT'ing.\n")

        self.Parameters = Custom(polyglot, 'customparams')
        self.ipAddress = spanIPAddress
        self.token = bearerToken
        self.circuitID = spanCircuitID
        tokenLastTen = self.token[-10:]
        LOGGER.debug("\n\tINIT IP Address for circuit:" + self.ipAddress + "; Bearer Token (last 10 characters): " + tokenLastTen + "; Circuit ID: " + self.circuitID)

        self.setDriver('GPV', self.circuitID, True, True)
        
        spanConnection = http.client.HTTPConnection(self.ipAddress)
        payload = ''
        headers = {
            "Authorization": "Bearer " + self.token
        }
     
        LOGGER.debug("\n\tINIT About to query " + self.ipAddress + "/api/v1/circuits/" + self.circuitID + "\n")
        spanConnection.request("GET", "/api/v1/circuits/" + self.circuitID, payload, headers)

        designatedCircuitResponse = spanConnection.getresponse()
        designatedCircuitData = designatedCircuitResponse.read()
        designatedCircuitData = designatedCircuitData.decode("utf-8")

        if "name" in designatedCircuitData:
            designatedCircuitTabs_tuple = designatedCircuitData.partition(chr(34) + "tabs" + chr(34) + ":")
            designatedCircuitTabs = designatedCircuitTabs_tuple[2]
            designatedCircuitTabs_tuple = designatedCircuitTabs.partition("],")
            designatedCircuitTabs = designatedCircuitTabs_tuple[0]
          
            LOGGER.info("\n\tINIT Designated Circuit Data: \n\t\t" + designatedCircuitData + "\n\t\tCount of Circuit Breakers In Circuit: " + str(designatedCircuitTabs.count(',')+1) + "\n")
            self.setDriver('PULSCNT', (designatedCircuitTabs.count(',')+1), True, True)

            designatedCircuitTabs = designatedCircuitTabs.replace('[','')
            designatedCircuitTabsArray = designatedCircuitTabs.split(',')
            designatedCircuitTabsCount = len(designatedCircuitTabsArray)
    
            for i in range(0,designatedCircuitTabsCount):
                LOGGER.debug("\n\t\tIn Circuit " + self.circuitID + ", Tab # " + str(i) + " corresponds to breaker number:\n\t\t\t" + designatedCircuitTabsArray[i] + "\n")
                try:
                    self.setDriver('GV' + str(i+1), designatedCircuitTabsArray[i], True, True)
                except:
                    LOGGER.warning("\n\t\tERROR Setting Tab (Physical Breaker #" + str(i+1) + ") for " + self.circuitID + ".\n")
            
            nowEpoch = int(time.time())
            nowDT = datetime.datetime.fromtimestamp(nowEpoch)
            
            self.setDriver('TIME', nowEpoch, True, True)
            self.setDriver('TIMEREM', nowDT.strftime("%m/%d/%Y, %H:%M:%S"), True, True)
        else:
            LOGGER.warning("\n\tINIT Issue getting data for circuit '" + self.circuitID + "'.\n")
            self.setDriver('TIMEREM', "INIT Error Querying" , True, True)
            
        # subscribe to the events we want
        #polyglot.subscribe(polyglot.CUSTOMPARAMS, self.parameterHandler)
        polyglot.subscribe(polyglot.POLL, self.poll)
        polyglot.subscribe(polyglot.START, self.start, address)
        #polyglot.subscribe(polyglot.ADDNODEDONE, self.node_queue)
        
    '''
    node_queue() and wait_for_node_event() create a simple way to wait
    for a node to be created.  The nodeAdd() API call is asynchronous and
    will return before the node is fully created. Using this, we can wait
    until it is fully created before we try to use it.
    def node_queue(self, data):
        self.n_queue.append(data['address'])        
        LOGGER.info("\n\tWAIT FOR NODE CREATION: Fully Complete for Circuit " + self.address + "\n")


    def wait_for_node_done(self):
        while len(self.n_queue) == 0:
            time.sleep(0.1)
        self.n_queue.pop()
    '''
        
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
        global allCircuitsData,allCircuitsDataUpdated
        while allCircuitsDataUpdated == 0:
            time.sleep(0.1)
        if 'shortPoll' in polltype:
            if self.getDriver('AWAKE') == 1:
                tokenLastTen = self.token[-10:]
                LOGGER.info('\n\tPOLL About to parse {} Circuit node of {}, using token ending in {}'.format(self.circuitID,self.ipAddress,tokenLastTen))
                designatedCircuitData_tuple = allCircuitsData.partition(chr(34) + self.circuitID + chr(34) + ':')
                designatedCircuitData = designatedCircuitData_tupple[2]
                designatedCircuitData_tuple = designatedCircuitData.partition('},')
                designatedCircuitData = designatedCircuitData_tuple[0] + '}'
        
                '''
                spanConnection = http.client.HTTPConnection(self.ipAddress)
                payload = ''
                headers = {
                    "Authorization": "Bearer " + self.token
                }
                spanConnection.request("GET", "/api/v1/circuits/" + self.circuitID, payload, headers)
        
                designatedCircuitResponse = spanConnection.getresponse()
                designatedCircuitData = designatedCircuitResponse.read()
                designatedCircuitData = designatedCircuitData.decode("utf-8")
                '''
            
                LOGGER.info("\n\tPOLL Circuit Data: \n\t\t" + designatedCircuitData + "\n")
            
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
                  
                    LOGGER.debug("\n\tPOLL about to evaluate Circuit Status (" + designatedCircuitStatus + ") and set CLIEMD appropriately.\n")
                    if "CLOSED" in designatedCircuitStatus:
                      self.setDriver('CLIEMD', 2, True, True)
                    elif "OPEN" in designatedCircuitStatus:
                      self.setDriver('CLIEMD', 1, True, True)
                    else:
                      self.setDriver('CLIEMD', 0, True, True)
                    
                    LOGGER.debug("\n\tPOLL About to set ST to " + str(designatedCircuitInstantPowerW) + " for Circuit " + self.circuitID + ".\n")
                    self.setDriver('ST', abs(designatedCircuitInstantPowerW), True, True)

                    if len(str(designatedCircuitInstantPowerW)) > 0:
                        nowEpoch = int(time.time())
                        nowDT = datetime.datetime.fromtimestamp(nowEpoch)
                        LOGGER.debug("\n\tPOLL about to set TIME and ST; TIME = '" + nowDT.strftime("%m/%d/%Y %H:%M:%S") + "'.\n")
                        self.setDriver('TIME', nowEpoch, True, True)
                        self.setDriver('TIMEREM', nowDT.strftime("%m/%d/%Y %H:%M:%S"), True, True)
                    else:
                        LOGGER.warning("\n\tPOLL ERROR: Unable to get designatedCircuitInstantPowerW from designatedCircuitData:\n\t\t" + designatedCircuitData + "\n")
                        self.setDriver('TIMEREM', "POLL Error Querying" , True, True)
                else:
                    LOGGER.warning("\n\tPOLL Issue getting data for circuit '" + self.circuitID + "'.\n")
                    self.setDriver('TIMEREM', "Error Querying" , True, True)
            else:
                LOGGER.debug("\n\t\tSkipping POLL query of Circuit node '" + self.circuitID + "' due to AWAKE=0.\n")
                self.setDriver('TIMEREM', "Not Actively Querying" , True, True)

    def toggle_circuit_monitoring(self,val):
        # On startup this will always go back to true which is the default, but how do we restore the previous user value?
        LOGGER.debug(f'{self.address} being set via toggle_circuit_monitoring to val={val}')
        self.setDriver('AWAKE', val, True, True)

    def cmd_toggle_circuit_monitoring(self,val):
        val = self.getDriver('AWAKE')
        LOGGER.debug(f'{self.address} being set via cmd_toggle_circuit_monitoring to val={val}')
        if val == 1:
            val = 0
        else:
            val = 1
        self.toggle_circuit_monitoring(val)

    commands = {
        "TOGGLE_CIRCUIT_MONITORING": cmd_toggle_circuit_monitoring,
    }
