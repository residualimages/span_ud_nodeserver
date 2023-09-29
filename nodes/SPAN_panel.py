#!/usr/bin/env python3
"""
Polyglot v3 node server SPAN Smart Panels
Copyright (C) 2023 Matt Burke

MIT License
"""
import udi_interface
import sys
import http.client
import re

from nodes import SPAN_circuit

# Standard Library
from typing import Optional, Any, TYPE_CHECKING

import math,time,datetime

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom

### Generic Nodeserver Helper Functions ###
### copied from Goose66 ###

# Removes invalid characters and converts to lowercase ISY Node address
def getValidNodeAddress(s: str) -> str:

    # NOTE: From docs: "A node address is made up of any combination of lowercase letters, numbers, and
    # '_' character. The maximum node address length (including the [5 character] prefix) is 19 characters."

    # remove any invalid URL characters since address may be in the path
    addr = re.sub(r"[^A-Za-z0-9_]", "", s)

    # convert to lowercase and trim to 14 characters
    return addr[:14].lower()

# Removes invalid charaters for ISY Node description
def getValidNodeName(s: str) -> str:

    # first convert unicode quotes to ascii quotes (single and double) and
    # then drop all other non-ascii characters
    # looks like the Admin Console limits to 29 characters, while the node's name can actually be longer and viewed in PG3
    # TODO: Test ".", "~", and other "special" characters to see if they cause problems
    # TODO: Test Kanji and other international characters with and without ascii converstion
    name = s.translate({ 0x2018:0x27, 0x2019:0x27, 0x201C:0x22, 0x201D:0x22 }).encode("ascii", "ignore").decode("ascii")

    return name

'''
This is our Panel device node. 
'''
class PanelNodeForCircuits(udi_interface.Node):
    id = 'panelForCircuits'
    drivers = [
            {'driver': 'ST', 'value': 0, 'uom': 73},
            {'driver': 'FREQ', 'value': '???', 'uom': 145},
            {'driver': 'PULSCNT', 'value': 0, 'uom': 56},
            {'driver': 'CLIEMD', 'value': 0, 'uom': 25},
            {'driver': 'TIME', 'value': 0, 'uom': 151},
            {'driver': 'TIMEREM', 'value': 'Initializing...', 'uom': 145},
            {'driver': 'AWAKE', 'value': 1, 'uom': 2},
            {'driver': 'GV0', 'value': 0, 'uom': 73},
            {'driver': 'GV1', 'value': 0, 'uom': 73},
            {'driver': 'GV2', 'value': 0, 'uom': 73},
            {'driver': 'GV3', 'value': 0, 'uom': 73},
            {'driver': 'GV4', 'value': 0, 'uom': 73},
            {'driver': 'GV5', 'value': 0, 'uom': 73},
            {'driver': 'GV6', 'value': 0, 'uom': 73},
            {'driver': 'GV7', 'value': 0, 'uom': 73},
            {'driver': 'GV8', 'value': 0, 'uom': 73},
            {'driver': 'GV9', 'value': 0, 'uom': 73},
            {'driver': 'GV10', 'value': 0, 'uom': 73},
            {'driver': 'GV11', 'value': 0, 'uom': 73},
            {'driver': 'GV12', 'value': 0, 'uom': 73},
            {'driver': 'GV13', 'value': 0, 'uom': 73},
            {'driver': 'GV14', 'value': 0, 'uom': 73},
            {'driver': 'GV15', 'value': 0, 'uom': 73},
            {'driver': 'GV16', 'value': 0, 'uom': 73},
            {'driver': 'GV17', 'value': 0, 'uom': 73},
            {'driver': 'GV18', 'value': 0, 'uom': 73},
            {'driver': 'GV19', 'value': 0, 'uom': 73},
            {'driver': 'GV20', 'value': 0, 'uom': 73},
            {'driver': 'GV21', 'value': 0, 'uom': 73},
            {'driver': 'GV22', 'value': 0, 'uom': 73},
            {'driver': 'GV23', 'value': 0, 'uom': 73},
            {'driver': 'GV24', 'value': 0, 'uom': 73},
            {'driver': 'GV25', 'value': 0, 'uom': 73},
            {'driver': 'GV26', 'value': 0, 'uom': 73},
            {'driver': 'GV27', 'value': 0, 'uom': 73},
            {'driver': 'GV28', 'value': 0, 'uom': 73},
            {'driver': 'GV29', 'value': 0, 'uom': 73},
            {'driver': 'GV30', 'value': 0, 'uom': 73},
            {'driver': 'GPV', 'value': 0, 'uom': 73}
            ]

    def __init__(self, polyglot, parent, address, name, spanIPAddress, bearerToken):
        super(PanelNodeForCircuits, self).__init__(polyglot, parent, address, name)

        # set a flag to short circuit setDriver() until the node has been fully
        # setup in the Polyglot DB and the ISY (as indicated by START event)
        self._initialized: bool = False
        
        self.poly = polyglot
        self.n_queue = []

        LOGGER.debug("\n\tINIT Panel node's parent is '" + parent + "' when INIT'ing.\n")

        self.Parameters = Custom(polyglot, 'customparams')
        self.ipAddress = spanIPAddress
        self.token = bearerToken
        self.circuitsDataCopy = "Not yet queried"
        self.circuitsDataUpdated = 0
        tokenLastTen = self.token[-10:]
        LOGGER.debug("\n\tINIT Panel node's IP Address:" + self.ipAddress + "; Bearer Token (last 10 characters): " + tokenLastTen)

        spanConnection = http.client.HTTPConnection(self.ipAddress)
        payload = ''
        headers = {
            "Authorization": "Bearer " + self.token
        }
        spanConnection.request("GET", "/api/v1/status", payload, headers)

        statusResponse = spanConnection.getresponse()
        statusData = statusResponse.read()
        statusData = statusData.decode("utf-8")

        if "system" in statusData:
            LOGGER.info("\n\tINIT Panel node's Status Data: \n\t\t" + statusData + "\n")

            spanConnection.request("GET", "/api/v1/circuits", payload, headers)
    
            circuitsResponse = spanConnection.getresponse()
            circuitsData = circuitsResponse.read()
            circuitsData = circuitsData.decode("utf-8")
            self.circuitsDataCopy = circuitsData
            self.circuitsDataUpdated = 1
        else:
            LOGGER.warning("\n\tINIT Issue getting Status Data for Panel @ " + self.ipAddress + ".\n")
        
        # subscribe to the events we want
        #polyglot.subscribe(polyglot.CUSTOMPARAMS, self.parameterHandler)
        polyglot.subscribe(polyglot.POLL, self.poll)
        polyglot.subscribe(polyglot.STOP, self.stop)
        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.ADDNODEDONE, self.node_queue_panelFinished)

    '''
    node_queue() and wait_for_node_event() create a simple way to wait
    for a node to be created.  The nodeAdd() API call is asynchronous and
    will return before the node is fully created. Using this, we can wait
    until it is fully created before we try to use it.
    '''
    def node_queue_panelFinished(self, data):
        self.n_queue.append(data['address'])
        
        LOGGER.info("\n\tWAIT FOR NODE CREATION: Fully Complete for Panel " + self.address + "\n")

        self.setDriver('FREQ', self.ipAddress, True, True)
        
        if "circuits" in self.circuitsDataCopy:
            LOGGER.info("\n\tINIT Panel node's Circuits Data: \n\t\t" + self.circuitsDataCopy + "\n\t\tCount of circuits: " + str(self.circuitsDataCopy.count(chr(34) + 'id' + chr(34) + ':')) + "\n")
            self.setDriver('PULSCNT', self.circuitsDataCopy.count(chr(34) + 'id' + chr(34) + ':'), True, True)
            self.setDriver('CLIEMD', 1, True, True)
    
            self.createCircuits(self.circuitsDataCopy)
        else:
            LOGGER.warning("\n\tINIT Issue getting Circuits Data for Panel @ " + self.ipAddress + ".\n")

    def wait_for_node_done(self):
        while len(self.n_queue) == 0:
            time.sleep(0.1)
        self.n_queue.pop()

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
            self.circuitsDataUpdated = 0
            if self.getDriver('AWAKE') == 1:
                tokenLastTen = self.token[-10:]
                LOGGER.info('\n\tPOLL About to query Panel node of {}, using token ending in {}'.format(self.ipAddress,tokenLastTen))
        
                spanConnection = http.client.HTTPConnection(self.ipAddress)
                payload = ''
                headers = {
                    "Authorization": "Bearer " + self.token
                }
                spanConnection.request("GET", "/api/v1/panel", payload, headers)
        
                panelResponse = spanConnection.getresponse()
                panelData = panelResponse.read()
                panelData = panelData.decode("utf-8")
                LOGGER.info("\n\tPOLL Panel node's Panel Data: \n\t\t" + panelData + "\n")
               
                if "branches" in panelData:
                    feedthroughPowerW_tuple = panelData.partition(chr(34) + "feedthroughPowerW" + chr(34) + ":")
                    feedthroughPowerW = feedthroughPowerW_tuple[2]
                    #LOGGER.debug("\n\t\t1st level Parsed feedthroughPowerW:\t" + feedthroughPowerW + "\n")
                    feedthroughPowerW_tuple = feedthroughPowerW.partition(",")
                    feedthroughPowerW = feedthroughPowerW_tuple[0]
                    #LOGGER.debug("\n\t\t2nd level Parsed feedthroughPowerW:\t" + feedthroughPowerW + "\n")
                    #feedthroughPowerW_tuple = feedthroughPowerW.partition(":")
                    #feedthroughPowerW = feedthroughPowerW_tuple[2]
                    #LOGGER.debug("\n\t\t3rd level Parsed feedthroughPowerW:\t" + feedthroughPowerW + "\n")                
                    feedthroughPowerW = math.ceil(float(feedthroughPowerW)*100)/100
    
                    instantGridPowerW_tuple = panelData.partition(chr(34) + "instantGridPowerW" + chr(34) + ":")
                    instantGridPowerW = instantGridPowerW_tuple[2]
                    #LOGGER.debug("\n\t\t1st level Parsed instantGridPowerW:\t" + instantGridPowerW + "\n")
                    instantGridPowerW_tuple = instantGridPowerW.partition(",")
                    instantGridPowerW = instantGridPowerW_tuple[0]
                    #LOGGER.debug("\n\t\t2nd level Parsed instantGridPowerW:\t" + instantGridPowerW + "\n")
                    #instantGridPowerW_tuple = instantGridPowerW.partition(":")
                    #instantGridPowerW = instantGridPowerW_tuple[2]
                    #LOGGER.debug("\n\t\t3rd level Parsed instantGridPowerW:\t" + instantGridPowerW + "\n")                
                    instantGridPowerW = math.ceil(float(instantGridPowerW)*100)/100
                    #LOGGER.debug("\n\t\tFinal Level Parsed and rounded instantGridPowerW:\t" + str(instantGridPowerW) + "\n")
                    #LOGGER.debug("\t\tFinal Level Parsed and rounded feedthroughPowerW:\t" + str(feedthroughPowerW) + "\n")
                    self.setDriver('ST', (instantGridPowerW-abs(feedthroughPowerW)), True, True)
    
                    for i in range(1,33):
                        try:
                            currentBreaker_tuple = panelData.partition(chr(34) + 'id' + chr(34) + ':' + str(i))
                            currentBreakerW = currentBreaker_tuple[2]
                            #LOGGER.debug("\n\t\t1st level Parsed for Breaker " + str(i) + ":\t" + currentBreakerW + "\n")
                            currentBreaker_tuple = currentBreakerW.partition(chr(34) + 'instantPowerW' + chr(34) + ':')
                            currentBreakerW = currentBreaker_tuple[2]
                            #LOGGER.debug("\n\t\t2nd level Parsed for Breaker " + str(i) + ":\t" + currentBreakerW + "\n")
                            currentBreaker_tuple = currentBreakerW.partition(',')
                            currentBreakerW = currentBreaker_tuple[0]
                            #LOGGER.debug("\n\t\t3rd level Parsed for Breaker " + str(i) + ":\t" + currentBreakerW + "\n")
                            currentBreakerW = abs(math.ceil(float(currentBreakerW)*100)/100)
                            #LOGGER.debug("\n\t\tFinal Level Parsed for Breaker " + str(i) + ":\t" + str(currentBreakerW) + "\n")
                            if i < 32:
                                self.setDriver('GV' + str(i-1), currentBreakerW, True, True)
                            else:
                                self.setDriver('GPV', currentBreakerW, True, True)
                        except:
                            LOGGER.warning("\n\tPOLL Issue getting data from Breaker " + str(i) + " on Panel node " + format(self.ipAddress) + ".\n")
                    
                    if len(str(instantGridPowerW)) > 0:
                        nowEpoch = int(time.time())
                        nowDT = datetime.datetime.fromtimestamp(nowEpoch)
                        
                        self.setDriver('TIME', nowEpoch, True, True)
                        self.setDriver('TIMEREM', nowDT.strftime("%m/%d/%Y, %H:%M:%S"), True, True)
    
                spanConnection.request("GET", "/api/v1/circuits", payload, headers)
                circuitsResponse = spanConnection.getresponse()
                circuitsData = circuitsResponse.read()
                circuitsData = circuitsData.decode("utf-8")
                self.circuitsDataCopy = circuitsData
                self.circuitsDataUpdated = 1

                else:
                    tokenLastTen = self.token[-10:]
                    LOGGER.debug('\n\tPOLL ERROR when querying Panel node at IP address {}, using token {}'.format(self.ipAddress,tokenLastTen))
            else:
                tokenLastTen = self.token[-10:]
                LOGGER.debug('\n\tSkipping POLL query of Panel node at IP address {}, using token {}'.format(self.ipAddress,tokenLastTen))
                self.setDriver('TIMEREM', "Not Actively Querying" , True, True)
            
    def toggle_monitoring(self,val):
        # On startup this will always go back to true which is the default, but how do we restore the previous user value?
        LOGGER.debug(f'{self.address} setting AWAKE via toggle_monitoring to val={val}')
        self.setDriver('AWAKE', val, True, True)

    def cmd_toggle_monitoring(self,val):
        val = self.getDriver('AWAKE')
        LOGGER.debug(f'{self.address} setting AWAKE via cmd_toggle_monitoring to val={val}')
        if val == 1:
            val = 0
        else:
            val = 1
        self.toggle_monitoring(val)

    commands = {
        "TOGGLE_MONITORING": cmd_toggle_monitoring,
    }

    '''
    Create the circuit nodes.
    TODO: Handle fewer circuit nodes by deleting (currently commented out)
    '''
    def createCircuits(self,circuitDataString):
        '''
        # delete any existing nodes but only under this panel
        currentPanelCircuitPrefix = "s" + self.address.replace('panel_','') + "_circuit_"
        nodes = self.poly.getNodes()
        for node in nodes:
             if currentPanelCircuitPrefix in node:
                LOGGER.debug("\n\tDeleting " + node + " when creating child Circuit nodes for " + self.address + ".\n")
                self.poly.delNode(node)
        '''

        how_many = self.getDriver('PULSCNT')
        
        allCircuitsArray = circuitDataString.split(chr(34) + 'id' + chr(34) + ':')
        panelNumberPrefix = self.address
        panelNumberPrefix = panelNumberPrefix.replace('panel_','')

        LOGGER.debug("\n\tHere is where we'll be creating Circuit children nodes for " + self.address + ". It should be a total of " + str(how_many) + " child nodes, each with an address starting with S" + panelNumberPrefix + "_...\n")

        for i in range(1, how_many+1):
            LOGGER.debug("\n\tHere is the currentCircuitData:\n\t\t" + allCircuitsArray[i] + "\n")
            current_IPaddress = self.ipAddress
            current_BearerToken = self.token
            address = 'S' + panelNumberPrefix + '_Circuit_' + str(i)
            address = getValidNodeAddress(address)
            current_circuitID_tuple = allCircuitsArray[i].partition(',')
            current_circuitID = current_circuitID_tuple[0].replace(chr(34),'')
            current_circuitName_tuple = allCircuitsArray[i].partition(chr(34) + 'name' + chr(34) + ':')
            current_circuitName = current_circuitName_tuple[2]
            current_circuitName_tuple = current_circuitName.partition(',')
            current_circuitName = current_circuitName_tuple[0].replace(chr(34),'')
            title = current_circuitName
            #if len(title)<25:
            #    title = title + ' (' + current_circuitID[-(26-len(title)):] + ')'
            title = getValidNodeName(title)
            try:
                node = SPAN_circuit.CircuitNode(self.poly, self.address, address, title, current_IPaddress, current_BearerToken,current_circuitID)
                self.poly.addNode(node)
                #self.wait_for_node_done()
                node.setDriver('AWAKE', 1, True, True)
                LOGGER.info('\n\tCreated a Circuit child node {} under Panel {}\n'.format(title, panelNumberPrefix))
            except Exception as e:
                LOGGER.error('\n\tFailed to create Circuit child node {} under Panel {} due to error: {}.\n'.format(title, panelNumberPrefix, e))

    '''
    Change all the child node active status drivers to false
    TBD: is this needed on Circuit children via Panel parent?
    '''
    def stop(self):
        currentPanelCircuitPrefix = "s" + self.address.replace('panel_','') + "_circuit_"
        nodes = self.poly.getNodes()
        for node in nodes:
            if currentPanelCircuitPrefix in node:
                nodes[node].setDriver('AWAKE', 0, True, True)
                LOGGER.debug("\n\tSetting " + node + "'s property AWAKE = 0.\n")

