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
import xml.etree.ElementTree as ET

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
    # TODO: Test ".", "~", and other "special" characters to see if they cause problems
    # TODO: Test Kanji and other international characters with and without ascii converstion
    name = s.translate({ 0x2018:0x27, 0x2019:0x27, 0x201C:0x22, 0x201D:0x22 }).encode("ascii", "ignore").decode("ascii")

    return name

'''
This is our Panel device node. 
'''
class PanelNode(udi_interface.Node):
    id = 'panel'
    drivers = [
            {'driver': 'TPW', 'value': 0, 'uom': 73},
            {'driver': 'PULSCNT', 'value': 0, 'uom': 56},
            {'driver': 'CLIEMD', 'value': 0, 'uom': 25},
            {'driver': 'TIME', 'value': 0, 'uom': 151},
            {'driver': 'ST', 'value': 'Initializing...', 'uom': 145},
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
        
        LOGGER.info("\nCircuits Data: \n\t\t" + circuitsData + "\n\t\tCount of circuits: " + str(circuitsData.count(chr(34) + 'id' + chr(34) + ':')) + "\n")
        self.setDriver('PULSCNT', circuitsData.count(chr(34) + 'id' + chr(34) + ':'), True, True)
        self.setDriver('CLIEMD', 1, True, True)

        self.createChildren(circuitsData)
        
        # subscribe to the events we want
        #polyglot.subscribe(polyglot.CUSTOMPARAMS, self.parameterHandler)
        polyglot.subscribe(polyglot.POLL, self.poll)
        polyglot.subscribe(polyglot.STOP, self.stop)
        
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
                LOGGER.debug("\n\t\tFinal Level Parsed and rounded instantGridPowerW:\t" + str(instantGridPowerW) + "\n")
                LOGGER.debug("\t\tFinal Level Parsed and rounded feedthroughPowerW:\t" + str(feedthroughPowerW) + "\n")
                self.setDriver('TPW', (instantGridPowerW-abs(feedthroughPowerW)), True, True)

                for i in range(1,33):
                    try:
                        currentCircuit_tuple = panelData.partition(chr(34) + 'id' + chr(34) + ':' + str(i))
                        currentCircuitW = currentCircuit_tuple[2]
                        #LOGGER.debug("\n\t\t1st level Parsed for Circuit " + str(i) + ":\t" + currentCircuitW + "\n")
                        currentCircuit_tuple = currentCircuitW.partition(chr(34) + 'instantPowerW' + chr(34) + ':')
                        currentCircuitW = currentCircuit_tuple[2]
                        #LOGGER.debug("\n\t\t2nd level Parsed for Circuit " + str(i) + ":\t" + currentCircuitW + "\n")
                        currentCircuit_tuple = currentCircuitW.partition(',')
                        currentCircuitW = currentCircuit_tuple[0]
                        #LOGGER.debug("\n\t\t3rd level Parsed for Circuit " + str(i) + ":\t" + currentCircuitW + "\n")
                        currentCircuitW = abs(math.ceil(float(currentCircuitW)*100)/100)
                        LOGGER.debug("\n\t\tFinal Level Parsed for Circuit " + str(i) + ":\t" + str(currentCircuitW) + "\n")
                        if i < 32:
                            self.setDriver('GV' + str(i-1), currentCircuitW, True, True)
                        else:
                            self.setDriver('GPV', currentCircuitW, True, True)
                    except:
                        LOGGER.warning("\n\t\tIssue getting data from Circuit " + str(i) + " on Panel " + format(self.ipAddress) + ".\n")
                
                if len(str(instantGridPowerW)) > 0:
                    self.setDriver('TIME', int(time.time()), True, True)
                    self.setDriver('ST', datetime.datetime.fromtimestamp(int(time.time())), True, True)
            else:
                tokenLastTen = self.token[-10:]
                LOGGER.debug('\n\t\tSkipping query of Panel node {}, using token {}'.format(self.ipAddress,tkenLastToken))
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

    '''
    Create the children nodes.  Since this will be called anytime the
    user changes the number of nodes and the new number may be less
    than the previous number, we need to make sure we create the right
    number of nodes.  Because this is just a simple example, we'll first
    delete any existing nodes then create the number requested.
    '''
    def createChildren(self,circuitDataString):
        # delete any existing nodes
        nodes = self.poly.getNodes()
        for node in nodes:
            if "panel_" not in node and node != 'controller':   # but not the controller or panel nodes
                #self.poly.delNode(node)
                LOGGER.debug("\nWould be deleting " + node + ", but it's commented out.\n")

        how_many = self.getDriver('PULSCNT')
        LOGGER.debug("\nHere is where we'll be creating Circuit children nodes. It should be a total of " + str(how_many) + " child nodes.\n")

        allCircuitsArray = circuitDataString.split(chr(34) + 'id' + chr(34) + ':')
        
        for i in range(1, how_many+1):
            LOGGER.debug("\nHere is the currentCircuitData:\n\t\t" + allCircuitsArray[i] + "\n")
            current_IPaddress = self.ipAddress
            current_BearerToken = self.token
            address = 'Circuit_{}'.format(i)
            address = getValidNodeAddress(address)
            current_circuitID_tuple = allCircuitsArray[i].partition(',')
            current_circuitID = "circuit_" + current_circuitID_tuple[0]
            current_circuitName_tuple = allCircuitsArray[i].partition(chr(34) + 'name' + chr(34) + ':')
            current_circuitName = current_circuitName_tuple[2]
            title = '{}({})'.format(current_circuitName,current_circuitID)
            title = getValidNodeName(title)
            try:
                node = SPAN_circuit.CircuitNode(self.poly, self.address, address, title, current_IPaddress, current_BearerToken,current_circuitID)
                self.poly.addNode(node)
                self.wait_for_node_done()
                node.setDriver('AWAKE', 1, True, True)
            except Exception as e:
                LOGGER.error('Failed to create {}: {}'.format(title, e))

    '''
    Change all the child node active status drivers to false
    TBD: is this needed on Circuit children via Panel parent?
    '''
    def stop(self):
        nodes = self.poly.getNodes()
        for node in nodes:
            if "panel_" not in node and node != 'controller':   # but not the controller or panel nodes
                #nodes[node].setDriver('AWAKE', 0, True, True)
                LOGGER.debug("\nWould be setting " + node + " AWAKE = 0, but it's commented out.\n")

