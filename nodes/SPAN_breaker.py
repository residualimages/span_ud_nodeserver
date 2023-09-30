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

#import urllib.parse

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom

'''
This is our Breaker device node. 
'''
class BreakerNode(udi_interface.Node):
    id = 'breaker'
    drivers = [
            {'driver': 'ST', 'value': 0, 'uom': 73},
            {'driver': 'PULSCNT', 'value': 0, 'uom': 56},
            {'driver': 'CLIEMD', 'value': 0, 'uom': 25},
            {'driver': 'TIME', 'value': 0, 'uom': 151},
            {'driver': 'TIMEREM', 'value': chr(34) + 'Initializing' + chr(34), 'uom': 145}
            ]

    def __init__(self, polyglot, parent, address, name, spanIPAddress, bearerToken, spanBreakerID):
        super(BreakerNode, self).__init__(polyglot, parent, address, name)

        # set a flag to short circuit setDriver() until the node has been fully
        # setup in the Polyglot DB and the ISY (as indicated by START event)
        self._initialized: bool = False
        
        self.poly = polyglot
        self.n_queue = []

        LOGGER.debug("\n\tINIT Span Breaker's parent is '" + parent + "' when INIT'ing.\n")

        self.Parameters = Custom(polyglot, 'customparams')
        self.ipAddress = spanIPAddress
        self.token = bearerToken
        self.breakerID = spanBreakerID
        self.allBreakersData = ''
        
        tokenLastTen = self.token[-10:]
        LOGGER.debug("\n\tINIT IP Address for breaker:" + self.ipAddress + "; Bearer Token (last 10 characters): " + tokenLastTen + "; Breaker ID: " + str(self.breakerID))

        self.setDriver('PULSCNT', self.breakerID, True, True)

        '''
        spanConnection = http.client.HTTPConnection(self.ipAddress)
        payload = ''
        headers = {
            "Authorization": "Bearer " + self.token
        }
     
        LOGGER.debug("\n\tINIT About to query " + self.ipAddress + "/api/v1/panel/" + self.breakerID + "\n")
        spanConnection.request("GET", "/api/v1/panel/" + self.breakerID, payload, headers)

        designatedBreakerResponse = spanConnection.getresponse()
        designatedBreakerData = designatedBreakerResponse.read()
        designatedBreakerData = designatedBreakerData.decode("utf-8")
        '''

        '''
        parentPrefix_tuple = self.address.partition('_')
        parentPrefix = parentPrefix_tuple[0]
        parentPrefix = parentPrefix.replace('s','panelbreaker_')  
        LOGGER.debug("\n\t\tAbout to try to grab the globals()['" + parentPrefix + "_allBreakersData']\n")
        globals()[parentPrefix + '_allBreakersData']
        allBreakersData = globals()[parentPrefix + '_allBreakersData']
        '''
            
        # subscribe to the events we want
        #polyglot.subscribe(polyglot.CUSTOMPARAMS, self.parameterHandler)
        #polyglot.subscribe(polyglot.POLL, self.poll)
        #polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.STOP, self.stop, address)
        #polyglot.subscribe(polyglot.ADDNODEDONE, self.node_queue)
        
        self.initialized = True
        
    '''
    node_queue() and wait_for_node_event() create a simple way to wait
    for a node to be created.  The nodeAdd() API call is asynchronous and
    will return before the node is fully created. Using this, we can wait
    until it is fully created before we try to use it.
    '''
    def node_queue(self, data):
        self.n_queue.append(data['address'])        
        if self.address == data['address']:
            LOGGER.debug("\n\tWAIT FOR NODE CREATION: Fully Complete for Breaker " + self.address + "\n")
            nowEpoch = int(time.time())
            nowDT = datetime.datetime.fromtimestamp(nowEpoch)
            self.setDriver('TIME', nowEpoch, True, True)            
            timeString = nowDT.strftime("%m/%d/%Y, %H:%M:%S")
            #encoded_timeString = urllib.parse.quote(timeString, safe='')
            self.setDriver('TIMEREM', chr(34) + timeString + chr(34), True, True)

    def wait_for_node_done(self):
        while len(self.n_queue) == 0:
            time.sleep(0.1)
        self.n_queue.pop()
        
    # called by the interface after the node data has been put in the Polyglot DB
    # and the node created/updated in the ISY
    #def start(self):
        # set the initlized flag to allow setDriver to work
        #self._initialized = True
    
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
    This is where the real work happens.  When the parent controller gets a shortPoll, do some work. 
    '''
    def updateNode(self, passedAllBreakersData):
        self.allBreakersData = passedAllBreakersData

        if 'Initializing' in self.getDriver('TIMEREM'):
            designatedBreakerData_tuple = self.allBreakersData.partition(chr(34) + str(self.breakerID) + chr(34) + ':')
            designatedBreakerData = designatedBreakerData_tuple[2]
            designatedBreakerData_tuple = designatedBreakerData.partition('},')
            designatedBreakerData = designatedBreakerData_tuple[0] + '}'

            if self.getDriver('PULSCNT') == 0:
                LOGGER.debug("\n\t\tSETTING PULSCNT because it is currently 0.\n")
                self.setDriver('PULSCNT', self.breakerID, True, True)
                
            nowEpoch = int(time.time())
            nowDT = datetime.datetime.fromtimestamp(nowEpoch)
            
            self.setDriver('TIME', nowEpoch, True, True)
            timeString = nowDT.strftime("%m/%d/%Y, %H:%M:%S")
            #encoded_timeString = urllib.parse.quote(timeString, safe='')
            self.setDriver('TIMEREM', chr(34) + timeString + chr(34), True, True)
            LOGGER.debug("\n\tINIT Final for PULSCNT, TIME, and TIMEREM now complete.\n")
        
        self.poll('shortPoll')
        
    def poll(self, polltype):
        if 'shortPoll' in polltype:
            tokenLastTen = self.token[-10:]
            LOGGER.debug('\n\tPOLL About to parse {} Breaker node of {}, using token ending in {}'.format(self.breakerID,self.ipAddress,tokenLastTen))
            designatedBreakerData_tuple = self.allBreakersData.partition(chr(34) + 'id' + chr(34) + ':' + str(self.breakerID) + ',')
            designatedBreakerData = designatedBreakerData_tuple[2]
            designatedBreakerData_tuple = designatedBreakerData.partition('},')
            designatedBreakerData = designatedBreakerData_tuple[0] + '}'
    
            '''
            spanConnection = http.client.HTTPConnection(self.ipAddress)
            payload = ''
            headers = {
                "Authorization": "Bearer " + self.token
            }
            spanConnection.request("GET", "/api/v1/panel/" + self.breakerID, payload, headers)
    
            designatedBreakerResponse = spanConnection.getresponse()
            designatedBreakerData = designatedBreakerResponse.read()
            designatedBreakerData = designatedBreakerData.decode("utf-8")
            '''
        
            LOGGER.debug("\n\tPOLL Breaker Data: \n\t\t" + designatedBreakerData + "\n")
        
            if "instantPowerW" in designatedBreakerData:
                designatedBreakerStatus_tuple = designatedBreakerData.partition(chr(34) + "relayState" + chr(34) + ":")
                designatedBreakerStatus = designatedBreakerStatus_tuple[2]
                designatedBreakerStatus_tuple = designatedBreakerStatus.partition(',')
                designatedBreakerStatus = designatedBreakerStatus_tuple[0]

                designatedBreakerInstantPowerW_tuple = designatedBreakerData.partition(chr(34) + "instantPowerW" + chr(34) + ":")
                designatedBreakerInstantPowerW = designatedBreakerInstantPowerW_tuple[2]
                designatedBreakerInstantPowerW_tuple = designatedBreakerInstantPowerW.partition(',')
                designatedBreakerInstantPowerW = designatedBreakerInstantPowerW_tuple[0]
                designatedBreakerInstantPowerW = math.ceil(float(designatedBreakerInstantPowerW)*100)/100
              
                LOGGER.debug("\n\tPOLL about to evaluate Breaker Status (" + designatedBreakerStatus + ") and set CLIEMD appropriately.\n")
                if "CLOSED" in designatedBreakerStatus:
                  self.setDriver('CLIEMD', 2, True, True)
                elif "OPEN" in designatedBreakerStatus:
                  self.setDriver('CLIEMD', 1, True, True)
                else:
                  self.setDriver('CLIEMD', 0, True, True)
                
                LOGGER.debug("\n\tPOLL About to set ST to " + str(abs(designatedBreakerInstantPowerW)) + " for Breaker " + str(self.breakerID) + ".\n")
                self.setDriver('ST', abs(designatedBreakerInstantPowerW), True, True)

                if len(str(designatedBreakerInstantPowerW)) > 0:
                    nowEpoch = int(time.time())
                    nowDT = datetime.datetime.fromtimestamp(nowEpoch)
                    LOGGER.debug("\n\tPOLL about to set TIME and ST; TIME = '" + nowDT.strftime("%m/%d/%Y %H:%M:%S") + "'.\n")
                    self.setDriver('TIME', nowEpoch, True, True)                            
                    timeString = nowDT.strftime("%m/%d/%Y, %H:%M:%S")
                    #encoded_timeString = urllib.parse.quote(timeString, safe='')
                    self.setDriver('TIMEREM', chr(34) + timeString + chr(34), True, True)
            else:
                LOGGER.warning("\n\tPOLL ERROR: Unable to get designatedBreakerInstantPowerW from designatedBreakerData:\n\t\t" + designatedBreakerData + "\n")
                self.setDriver('TIMEREM', chr(34) + "POLL_Error_Querying" + chr(34), True, True)
                
    '''
    Change self status driver to 0 W
    '''
    def stop(self):
        self.setDriver('ST', 0, True, True)
