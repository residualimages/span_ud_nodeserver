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

from nodes import SPAN_circuit,SPAN_breaker

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
This is our PanelForCircuits device node. 
Previously held Circuits in additional Status Parameters like so:
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
'''
class PanelNodeForCircuits(udi_interface.Node):
    id = 'panelForCircuits'
    drivers = [
            {'driver': 'ST', 'value': 0, 'uom': 73},
            {'driver': 'FREQ', 'value': -1, 'uom': 56},
            {'driver': 'PULSCNT', 'value': 0, 'uom': 56},
            {'driver': 'CLIEMD', 'value': 0, 'uom': 25},
            {'driver': 'TIME', 'value': 0, 'uom': 151},
            {'driver': 'MOON', 'value': -1, 'uom': 56},
            {'driver': 'TIMEREM', 'value': -1, 'uom': 56},
            {'driver': 'AWAKE', 'value': 1, 'uom': 2}
            ]

    def __init__(self, polyglot, parent, address, name, spanIPAddress, bearerToken):
        super(PanelNodeForCircuits, self).__init__(polyglot, parent, address, name)

        # set a flag to short circuit setDriver() until the node has been fully
        # setup in the Polyglot DB and the ISY (as indicated by START event)
        self._initialized: bool = False
        
        self.poly = polyglot
        self.n_queue = []

        LOGGER.debug("\n\tINIT Panel Circuit Controller " + address + "'s parent is '" + parent + "' when INIT'ing.\n")

        self.Parameters = Custom(polyglot, 'customparams')
        self.ipAddress = spanIPAddress
        self.token = bearerToken

        tokenLastTen = self.token[-10:]
        LOGGER.debug("\n\tINIT Panel Circuit Controller's IP Address:" + self.ipAddress + "; Bearer Token (last 10 characters): " + tokenLastTen)

        spanConnection = http.client.HTTPConnection(self.ipAddress)
        payload = ''
        headers = {
            "Authorization": "Bearer " + self.token
        }
        try:
            spanConnection.request("GET", "/api/v1/status", payload, headers)
    
            statusResponse = spanConnection.getresponse()
            statusData = statusResponse.read()
            statusData = statusData.decode("utf-8")
        except Exception as e:
            LOGGER.warning('\n\t\tINIT ERROR: SPAN API GET request failed in Panel Circuit Controller due to error:\t{}.\n'.format(e))
            statusData = ''
        
        self.allCircuitsData = ''

        if "system" in statusData:
            LOGGER.debug("\n\tINIT Panel Circuit Controller's Status Data: \n\t\t" + statusData + "\n")

            spanConnection.request("GET", "/api/v1/circuits", payload, headers)
    
            circuitsResponse = spanConnection.getresponse()
            self.allCircuitsData = circuitsResponse.read()
            self.allCircuitsData = self.allCircuitsData.decode("utf-8")
        else:
            LOGGER.warning("\n\tINIT Issue getting Status Data for Panel Circuit Controller @ " + self.ipAddress + ".\n")
        
        # subscribe to the events we want
        #polyglot.subscribe(polyglot.CUSTOMPARAMS, self.parameterHandler)
        polyglot.subscribe(polyglot.POLL, self.poll)
        polyglot.subscribe(polyglot.STOP, self.stop)
        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.ADDNODEDONE, self.node_queue_panelCircuitsFinished)

    '''
    node_queue() and wait_for_node_event() create a simple way to wait
    for a node to be created.  The nodeAdd() API call is asynchronous and
    will return before the node is fully created. Using this, we can wait
    until it is fully created before we try to use it.
    '''
    def node_queue_panelCircuitsFinished(self, data):
        self.n_queue.append(data['address'])
        #LOGGER.debug("\n\t\tSUBSCRIBED AddNodeDone under Panel Circuits Controller: Node Creation Complete for " + data['address'] + ".\n")
        if self.address == data['address']:
            LOGGER.debug("\n\t\t\tPanelForCircuits Controller Creation Completed; Queue Circuit child node(s) creation.\n")
            #self.setDriver('AWAKE', 1, True, True)
            lastOctet_array = self.ipAddress.split('.')
            lastOctet = lastOctet_array[len(lastOctet_array)-1]
            self.setDriver('FREQ', lastOctet, True, True, None, self.ipAddress)
        
            if "circuits" in self.allCircuitsData:
                spanConnection = http.client.HTTPConnection(self.ipAddress)
                payload = ''
                headers = {
                    "Authorization": "Bearer " + self.token
                }
                try:
                    spanConnection.request("GET", "/api/v1/panel", payload, headers)
                    panelResponse = spanConnection.getresponse()
                    panelData = panelResponse.read()
                    panelData = panelData.decode("utf-8")
                    LOGGER.debug("\n\tINIT Panel Circuit Controller's Panel Data: \n\t\t" + panelData + "\n")
                except Exception as e:
                    LOGGER.warning('\n\t\tINIT ERROR: SPAN API GET request for Panel Circuits Controller failed due to error:\t{}.\n'.format(e))
                    panelData = ''
                    
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
                    self.setDriver('ST', round((instantGridPowerW-abs(feedthroughPowerW)),2), True, True)
                
                LOGGER.debug("\n\tINIT Panel Circuit Controller's Circuits Data: \n\t\t" + self.allCircuitsData + "\n\t\tCount of circuits: " + str(self.allCircuitsData.count(chr(34) + 'id' + chr(34) + ':')) + "\n")
                self.setDriver('PULSCNT', self.allCircuitsData.count(chr(34) + 'id' + chr(34) + ':'), True, True)
                self.setDriver('CLIEMD', 1, True, True)
        
                self.createCircuits()
            else:
                LOGGER.warning("\n\tINIT Issue getting Circuits Data for Panel Circuits Controller @ " + self.ipAddress + ".\n")

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
    def setDriver(self, driver: str, value: Any, report: bool=True, force: bool=False, uom: Optional[int]=None, text: Optional[str]=None):
        if self._initialized:
            super().setDriver(driver, value, report, force, uom, text)

    '''
    Read the user entered custom parameters.
    '''
    def parameterHandler(self, params):
        self.Parameters.load(params)

    def updateNode(self, passedAllCircuitsData):
        self.allCircuitsData = passedAllCircuitsData

    '''
    This is where the real work happens.  When we get a shortPoll, do some work. 
    '''
    def poll(self, polltype):
        if 'shortPoll' in polltype:
            if self.getDriver('AWAKE') == 1:
                tokenLastTen = self.token[-10:]
                LOGGER.debug('\n\tPOLL About to query Panel Circuits Controller of {}, using token ending in {}'.format(self.ipAddress,tokenLastTen))
        
                spanConnection = http.client.HTTPConnection(self.ipAddress)
                payload = ''
                headers = {
                    "Authorization": "Bearer " + self.token
                }

                try:
                    spanConnection.request("GET", "/api/v1/panel", payload, headers)
            
                    panelResponse = spanConnection.getresponse()
                    panelData = panelResponse.read()
                    panelData = panelData.decode("utf-8")
                    LOGGER.debug("\n\tPOLL Panel Circuit Controller's Panel Data: \n\t\t" + panelData + "\n")
                except Exception as e:
                    LOGGER.warning('\n\t\tPOLL ERROR: SPAN API GET request for Panel Circuits Controller failed due to error:\t{}.\n'.format(e))
                    panelData = ''
               
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
                    self.setDriver('ST', round((instantGridPowerW-abs(feedthroughPowerW)),2), True, True)

                    '''
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
                            LOGGER.warning("\n\tPOLL Issue for Panel Circuits controller getting data from Breaker " + str(i) + " on Panel node " + format(self.ipAddress) + ".\n")
                    '''
                    
                    if len(str(instantGridPowerW)) > 0:
                        nowEpoch = int(time.time())
                        nowDT = datetime.datetime.fromtimestamp(nowEpoch)
                        
                        self.setDriver('TIME', nowEpoch, True, True)
                        self.setDriver('MOON', nowDT.strftime("%H.%M"), True, True, None, nowDT.strftime("%m/%d/%Y %H:%M:%S"))
                        self.setDriver('TIMEREM', nowDT.strftime("%S"), True, True, None, nowDT.strftime("%m/%d/%Y %H:%M:%S"))
    
                    try:
                        spanConnection.request("GET", "/api/v1/circuits", payload, headers)
                        circuitsResponse = spanConnection.getresponse()
                        self.allCircuitsData = circuitsResponse.read()
                        self.allCircuitsData = self.allCircuitsData.decode("utf-8")
                    except Exception as e:
                        LOGGER.warning('\n\t\tPOLL ERROR: SPAN API GET request for Panel Circuits Controller failed due to error:\t{}.\n'.format(e))
                        #self.allCircuitsData = ''
                    
                    nodes = self.poly.getNodes()
                    currentPanelCircuitPrefix = "s" + self.address.replace('panelcircuit_','') + "_circuit_"
                    LOGGER.debug("\n\tWill be looking for Circuit nodes with this as the prefix: '" + currentPanelCircuitPrefix + "'.\n")
                    for node in nodes:
                         if currentPanelCircuitPrefix in node:
                            LOGGER.debug("\n\tUpdating " + node + " (which should be a Circuit node under this Panel controller: " + self.address + ").\n")
                            try:
                                nodes[node].updateNode(self.allCircuitsData)
                            except Exception as e:
                                LOGGER.warning('\n\t\tPOLL ERROR in Panel Circuits: Cannot seem to update node needed in for-loop due to error:\t{}.\n'.format(e))
                else:
                    tokenLastTen = self.token[-10:]
                    LOGGER.warning('\n\tPOLL ERROR when querying Panel Circuit Controller at IP address {}, using token {}'.format(self.ipAddress,tokenLastTen))
            else:
                tokenLastTen = self.token[-10:]
                LOGGER.debug('\n\tSkipping POLL query of Panel Circuit Controller at IP address {}, using token {}'.format(self.ipAddress,tokenLastTen))
                self.setDriver('MOON', -1, True, True, None, "Not Actively Querying due to 'AWAKE' being set to 0.")
                self.setDriver('TIMEREM', -1, True, True, None, "Not Actively Querying due to 'AWAKE' being set to 0.")
            
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
    def createCircuits(self):
        '''
        # delete any existing nodes but only under this panel
        currentPanelCircuitPrefix = "s" + self.address.replace('panelcircuit_','') + "_circuit_"
        nodes = self.poly.getNodes()
        for node in nodes:
             if currentPanelCircuitPrefix in node:
                LOGGER.debug("\n\tDeleting " + node + " when creating child Circuit nodes for Panel Circuits controller at " + self.address + ".\n")
                self.poly.delNode(node)
        '''

        how_many = self.getDriver('PULSCNT')
        
        allCircuitsArray = self.allCircuitsData.split(chr(34) + 'id' + chr(34) + ':')
        panelNumberPrefix = self.address
        panelNumberPrefix = panelNumberPrefix.replace('panelcircuit_','')

        LOGGER.debug("\n\tHere is where we'll be creating Circuit children nodes for Panel Circuits controller " + self.address + ". It should be a total of " + str(how_many) + " child nodes, each with an address starting with s" + panelNumberPrefix + "_circuit_...\n")

        for i in range(1, how_many+1):
            LOGGER.debug("\n\tHere is the currentCircuitData:\n\t\t" + allCircuitsArray[i] + "\n")
            
            current_IPaddress = self.ipAddress
            #LOGGER.debug("\n\t\t'current_IPaddress':\t" + current_IPaddress + "\n")
            current_BearerToken = self.token
            #LOGGER.debug("\n\t\t'current_BearerToken':\t" + current_BearerToken + "\n")
            
            address = 'S' + panelNumberPrefix + '_Circuit_' + str(i)
            address = getValidNodeAddress(address)
            #LOGGER.debug("\n\t\tCalculated 'address':\t" + address + "\n")
            
            current_circuitID_tuple = allCircuitsArray[i].partition(',')
            current_circuitID = current_circuitID_tuple[0]
            #LOGGER.debug("\n\t\tCalculated 'current_CircuitID':\t" + current_circuitID + "\n")
            current_circuitID = current_circuitID.replace(chr(34),'')
            #LOGGER.debug("\n\t\tCalculated 'current_CircuitID':\t" + current_circuitID + "\n")
            
            current_circuitName_tuple = allCircuitsArray[i].partition(chr(34) + 'name' + chr(34) + ':')
            current_circuitName = current_circuitName_tuple[2]
            #LOGGER.debug("\n\t\tCalculated 'current_CircuitName':\t" + current_circuitName + "\n")
            current_circuitName_tuple = current_circuitName.partition(',')
            current_circuitName = current_circuitName_tuple[0]
            #LOGGER.debug("\n\t\tCalculated 'current_CircuitName':\t" + current_circuitName + "\n")
            current_circuitName = current_circuitName.replace(chr(34),'')
            #LOGGER.debug("\n\t\tCalculated 'current_CircuitName':\t" + current_circuitName + "\n")
            
            title = current_circuitName
            #if len(title)<25:
            #    title = title + ' (' + current_circuitID[-(26-len(title)):] + ')'
            title = getValidNodeName(title)
            try:
                node = SPAN_circuit.CircuitNode(self.poly, self.address, address, title, current_IPaddress, current_BearerToken, current_circuitID, i)
                self.poly.addNode(node)
                self.wait_for_node_done()
                LOGGER.debug('\n\tCreated a Circuit child node {} under Panel Circuit Controller {}\n'.format(title, panelNumberPrefix))
            except Exception as e:
                LOGGER.warning('\n\tFailed to create Circuit child node {} under Panel Circuit Controller {} due to error: {}.\n'.format(title, panelNumberPrefix, e))

    '''
    Change all the child node active status drivers to 0 W and disable 'AWAKE'
    '''
    def stop(self):
        currentPanelCircuitPrefix = "s" + self.address.replace('panelcircuit_','') + "_circuit_"
        nodes = self.poly.getNodes()
        self.setDriver('ST', 0, True, True)
        for node in nodes:
            if currentPanelCircuitPrefix in node:
                nodes[node].setDriver('AWAKE', 0, True, True)
                nodes[node].setDriver('ST', 0, True, True)
                LOGGER.debug("\n\tSTOP RECEIVED: Panel Circuit Controller Setting child " + node + "'s properties AWAKE = 0 and ST = 0 W.\n")
        self.setDriver('AWAKE', 0, True, True)

'''
This is our PanelForBreakers device node. 
'''
class PanelNodeForBreakers(udi_interface.Node):
    id = 'panelForBreakers'
    drivers = [
            {'driver': 'ST', 'value': 0, 'uom': 73},
            {'driver': 'FREQ', 'value': -1, 'uom': 56},
            {'driver': 'PULSCNT', 'value': 0, 'uom': 56},
            {'driver': 'GPV', 'value': 0, 'uom': 56},
            {'driver': 'TIME', 'value': 0, 'uom': 151},
            {'driver': 'MOON', 'value': -1, 'uom': 56},
            {'driver': 'TIMEREM', 'value': -1, 'uom': 56}
            ]

    def __init__(self, polyglot, parent, address, name, spanIPAddress, bearerToken):
        super(PanelNodeForBreakers, self).__init__(polyglot, parent, address, name)

        # set a flag to short circuit setDriver() until the node has been fully
        # setup in the Polyglot DB and the ISY (as indicated by START event)
        self._initialized: bool = False
        
        self.poly = polyglot
        self.n_queue = []

        LOGGER.debug("\n\tINIT Panel Breaker Controller " + address + "'s parent is '" + parent + "' when INIT'ing.\n")

        self.Parameters = Custom(polyglot, 'customparams')
        self.ipAddress = spanIPAddress
        self.token = bearerToken

        tokenLastTen = self.token[-10:]
        LOGGER.debug("\n\tINIT Panel Breaker Controller's IP Address:" + self.ipAddress + "; Bearer Token (last 10 characters): " + tokenLastTen)

        spanConnection = http.client.HTTPConnection(self.ipAddress)
        payload = ''
        headers = {
            "Authorization": "Bearer " + self.token
        }

        try:
            spanConnection.request("GET", "/api/v1/panel", payload, headers)

            panelResponse = spanConnection.getresponse()
            self.allBreakersData = panelResponse.read()
            self.allBreakersData = self.allBreakersData.decode("utf-8")
        except Exception as e:
            LOGGER.warning('\n\t\tINIT ERROR: SPAN API GET request for Panel Breakers Controller failed due to error:\t{}.\n'.format(e))
            self.allBreakersData = ''
        
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
        #LOGGER.debug("\n\t\tSUBSCRIBED AddNodeDone under Panel Breaker Controller: Node Creation Complete for " + data['address'] + ".\n")
        if self.address == data['address']:
            LOGGER.debug("\n\t\t\tPanelForBreakers Controller Creation Completed; Queue Breaker child node(s) creation.\n")
            #self.setDriver('AWAKE', 1, True, True)
            
            lastOctet_array = self.ipAddress.split('.')
            lastOctet = lastOctet_array[len(lastOctet_array)-1]
            self.setDriver('FREQ', lastOctet, True, True, None, self.ipAddress)
        
            if "branches" in self.allBreakersData:
                feedthroughPowerW_tuple = self.allBreakersData.partition(chr(34) + "feedthroughPowerW" + chr(34) + ":")
                feedthroughPowerW = feedthroughPowerW_tuple[2]
                #LOGGER.debug("\n\t\t1st level Parsed feedthroughPowerW:\t" + feedthroughPowerW + "\n")
                feedthroughPowerW_tuple = feedthroughPowerW.partition(",")
                feedthroughPowerW = feedthroughPowerW_tuple[0]
                #LOGGER.debug("\n\t\t2nd level Parsed feedthroughPowerW:\t" + feedthroughPowerW + "\n")
                #feedthroughPowerW_tuple = feedthroughPowerW.partition(":")
                #feedthroughPowerW = feedthroughPowerW_tuple[2]
                #LOGGER.debug("\n\t\t3rd level Parsed feedthroughPowerW:\t" + feedthroughPowerW + "\n")                
                feedthroughPowerW = math.ceil(float(feedthroughPowerW)*100)/100

                instantGridPowerW_tuple = self.allBreakersData.partition(chr(34) + "instantGridPowerW" + chr(34) + ":")
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
                self.setDriver('ST', round((instantGridPowerW-abs(feedthroughPowerW)),2), True, True)

                allBranchesData_tuple = self.allBreakersData.partition(chr(34) + "branches" + chr(34) + ":")
                allBranchesData = allBranchesData_tuple[2]
                LOGGER.debug("\n\tINIT Panel Breaker Controller's Branches Data: \n\t\t" + allBranchesData + "\n\t\tCount of OPEN Breakers: " + str(allBranchesData.count(chr(34) + 'OPEN' + chr(34) + ',')) + "\n\t\tCount of CLOSED Breakers: " + str(allBranchesData.count(chr(34) + 'CLOSED' + chr(34) + ',')) + "\n")
                self.setDriver('PULSCNT', allBranchesData.count(chr(34) + 'CLOSED' + chr(34) + ','), True, True)
                self.setDriver('GPV', allBranchesData.count(chr(34) + 'OPEN' + chr(34) + ','), True, True)
        
                self.createBreakers()
            else:
                LOGGER.warning("\n\tINIT Issue getting Breakers Data for Panel Breaker Controller @ " + self.ipAddress + ".\n")

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
    def setDriver(self, driver: str, value: Any, report: bool=True, force: bool=False, uom: Optional[int]=None, text: Optional[str]=None):
        if self._initialized:
            super().setDriver(driver, value, report, force, uom, text)

    '''
    Read the user entered custom parameters.
    '''
    def parameterHandler(self, params):
        self.Parameters.load(params)

    def updateNode(self, passedAllBreakersData):
        self.allBreakersData = passedAllBreakersData

    '''
    This is where the real work happens.  When we get a shortPoll, do some work. 
    '''
    def poll(self, polltype):
        if 'shortPoll' in polltype:
            tokenLastTen = self.token[-10:]
            LOGGER.debug('\n\tPOLL About to query Panel Breaker controller of {}, using token ending in {}'.format(self.ipAddress,tokenLastTen))
    
            spanConnection = http.client.HTTPConnection(self.ipAddress)
            payload = ''
            headers = {
                "Authorization": "Bearer " + self.token
            }

            try:
                spanConnection.request("GET", "/api/v1/panel", payload, headers)
        
                panelResponse = spanConnection.getresponse()
                self.allBreakersData = panelResponse.read()
                self.allBreakersData = self.allBreakersData.decode("utf-8")
            except Exception as e:
                LOGGER.warning('\n\t\tPOLL ERROR: SPAN API GET request for Panel Breaker Controller failed due to error:\t{}.\n'.format(e))
                #self.allBreakersData = ''

            LOGGER.debug("\n\tPOLL Panel Breaker Controller's allBreakersData: \n\t\t" + self.allBreakersData + "\n")
           
            if "branches" in self.allBreakersData:
                feedthroughPowerW_tuple = self.allBreakersData.partition(chr(34) + "feedthroughPowerW" + chr(34) + ":")
                feedthroughPowerW = feedthroughPowerW_tuple[2]
                #LOGGER.debug("\n\t\t1st level Parsed feedthroughPowerW:\t" + feedthroughPowerW + "\n")
                feedthroughPowerW_tuple = feedthroughPowerW.partition(",")
                feedthroughPowerW = feedthroughPowerW_tuple[0]
                #LOGGER.debug("\n\t\t2nd level Parsed feedthroughPowerW:\t" + feedthroughPowerW + "\n")
                #feedthroughPowerW_tuple = feedthroughPowerW.partition(":")
                #feedthroughPowerW = feedthroughPowerW_tuple[2]
                #LOGGER.debug("\n\t\t3rd level Parsed feedthroughPowerW:\t" + feedthroughPowerW + "\n")                
                feedthroughPowerW = math.ceil(float(feedthroughPowerW)*100)/100

                instantGridPowerW_tuple = self.allBreakersData.partition(chr(34) + "instantGridPowerW" + chr(34) + ":")
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
                self.setDriver('ST', round((instantGridPowerW-abs(feedthroughPowerW)),2), True, True)

                allBranchesData_tuple = self.allBreakersData.partition(chr(34) + "branches" + chr(34) + ":")
                allBranchesData = allBranchesData_tuple[2]
                LOGGER.debug("\n\tSHORT POLL Panel Breaker Controller's Branches Data: \n\t\t" + allBranchesData + "\n\t\tCount of OPEN Breakers: " + str(allBranchesData.count(chr(34) + 'OPEN' + chr(34) + ',')) + "\n\t\tCount of CLOSED Breakers: " + str(allBranchesData.count(chr(34) + 'CLOSED' + chr(34) + ',')) + "\n")
                self.setDriver('PULSCNT', allBranchesData.count(chr(34) + 'CLOSED' + chr(34) + ','), True, True)
                self.setDriver('GPV', allBranchesData.count(chr(34) + 'OPEN' + chr(34) + ','), True, True)
                
                if len(str(instantGridPowerW)) > 0:
                    nowEpoch = int(time.time())
                    nowDT = datetime.datetime.fromtimestamp(nowEpoch)
                    
                    self.setDriver('TIME', nowEpoch, True, True)
                    self.setDriver('MOON', nowDT.strftime("%H.%M"), True, True, None, nowDT.strftime("%m/%d/%Y %H:%M:%S"))
                    self.setDriver('TIMEREM', nowDT.strftime("%S"), True, True, None, nowDT.strftime("%m/%d/%Y %H:%M:%S"))

                '''
                for i in range(1,33):
                    try:
                        currentBreaker_tuple = self.allBreakersData.partition(chr(34) + 'id' + chr(34) + ':' + str(i))
                        currentBreakerW = currentBreaker_tuple[2]
                        currentBreakerID_tuple = currentBreakerW.partition(',')
                        currentBreakerID = currentBreakerID_tuple[0]
                        LOGGER.debug("\n\t\tfor-loop 'i' should be equal to currentBreakerID:\ti=" + str(i) + " ?=? currentBreakerID=" + currentBreakerID + ".\n")
                        #LOGGER.debug("\n\t\t1st level Parsed for Breaker " + str(i) + ":\t" + currentBreakerW + "\n")
                        currentBreaker_tuple = currentBreakerW.partition(chr(34) + 'instantPowerW' + chr(34) + ':')
                        currentBreakerW = currentBreaker_tuple[2]
                        #LOGGER.debug("\n\t\t2nd level Parsed for Breaker " + str(i) + ":\t" + currentBreakerW + "\n")
                        currentBreaker_tuple = currentBreakerW.partition(',')
                        currentBreakerW = currentBreaker_tuple[0]
                        #LOGGER.debug("\n\t\t3rd level Parsed for Breaker " + str(i) + ":\t" + currentBreakerW + "\n")
                        currentBreakerW = abs(math.ceil(float(currentBreakerW)*100)/100)
                        #LOGGER.debug("\n\t\tFinal Level Parsed for Breaker " + str(i) + ":\t" + str(currentBreakerW) + "\n")
                        #currentBreaker
                    except:
                        LOGGER.warning("\n\tPOLL Issue getting data from Breaker " + str(i) + " on Panel Breaker Controller " + format(self.ipAddress) + ".\n")
                '''
                nodes = self.poly.getNodes()
                currentPanelBreakerPrefix = "s" + self.address.replace('panelbreaker_','') + "_breaker_"
                LOGGER.debug("\n\tWill be looking for Breaker nodes with this as the prefix: '" + currentPanelBreakerPrefix + "'.\n")
                for node in nodes:
                     if currentPanelBreakerPrefix in node:
                        LOGGER.debug("\n\tUpdating " + node + " (which should be a Breaker node under this Panel controller: " + self.address + ").\n")
                        try:
                            nodes[node].updateNode(self.allBreakersData)
                        except Exception as e:
                            LOGGER.debug('\n\t\tPOLL ERROR: Cannot seem to update node needed in for-loop due to error:\t{}.\n'.format(e))
            else:
                tokenLastTen = self.token[-10:]
                LOGGER.warning('\n\tPOLL ERROR when querying Panel Breaker Controller at IP address {}, using token {}'.format(self.ipAddress,tokenLastTen))
            
    '''
    Create the breaker nodes.
    '''
    def createBreakers(self):
        '''
        # delete any existing nodes but only under this panel
        currentPanelBreakerPrefix = "s" + self.address.replace('panelbreaker_','') + "_breaker_"
        nodes = self.poly.getNodes()
        for node in nodes:
             if currentPanelBreakerPrefix in node:
                LOGGER.debug("\n\tDeleting " + node + " when creating child Breaker nodes for " + self.address + ".\n")
                self.poly.delNode(node)
        '''

        #how_many = self.getDriver('PULSCNT')
        
        allBreakersArray = self.allBreakersData.split(chr(34) + 'id' + chr(34) + ':')
        panelNumberPrefix = self.address
        panelNumberPrefix = panelNumberPrefix.replace('panelbreaker_','')

        LOGGER.debug("\n\tHere is where we'll be creating Breaker children nodes for " + self.address + ". It should be a total of 32 child nodes, each with an address starting with s" + panelNumberPrefix + "_breaker_...\n")

        for i in range(1, 33):
            LOGGER.debug("\n\tHere is the currentBreakersData:\n\t\t" + allBreakersArray[i] + "\n")
            
            current_IPaddress = self.ipAddress
            #LOGGER.debug("\n\t\t'current_IPaddress':\t" + current_IPaddress + "\n")
            current_BearerToken = self.token
            #LOGGER.debug("\n\t\t'current_BearerToken':\t" + current_BearerToken + "\n")
            
            address = 'S' + panelNumberPrefix + '_Breaker_' + str(i)
            address = getValidNodeAddress(address)
            #LOGGER.debug("\n\t\tCalculated 'address':\t" + address + "\n")
            
            title = "Breaker #"
            if i < 10:
                title = title + "0"
            title = title + str(i)
            title = getValidNodeName(title)
            try:
                node = SPAN_breaker.BreakerNode(self.poly, self.address, address, title, current_IPaddress, current_BearerToken, i)
                self.poly.addNode(node)
                self.wait_for_node_done()
                
                LOGGER.debug('\n\tCreated a Breaker child node {} under Panel Breaker controller {}\n'.format(title, panelNumberPrefix))
            except Exception as e:
                LOGGER.warning('\n\tFailed to create Breaker child node {} under Panel Breaker controller {} due to error: {}.\n'.format(title, panelNumberPrefix, e))

    '''
    Change all the child node active status drivers to 0 W
    '''
    def stop(self):
        currentPanelBreakerPrefix = "s" + self.address.replace('panelbreaker_','') + "_breaker_"
        nodes = self.poly.getNodes()
        self.setDriver('ST', 0, True, True)
        for node in nodes:
            if currentPanelBreakerPrefix in node:
                nodes[node].setDriver('ST', 0, True, True)
                LOGGER.debug("\n\tSTOP RECEIVED: Panel Breaker Controller setting " + node + "'s property ST = 0 W.\n")

