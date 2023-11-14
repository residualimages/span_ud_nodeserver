#!/usr/bin/env python3
"""
Polyglot v3 NodeServer SPAN Smart Panels - Circuits Controller
Copyright (C) 2023 Matt Burke

MIT License
"""
import udi_interface
import sys
import time
import string
import re

from nodes import SPAN_circuit, SPAN_breakerController

# Standard Library
from typing import Optional, Any, TYPE_CHECKING

import math,datetime,urllib.parse,http.client,base64

LOGGER = udi_interface.LOGGER
ISY = udi_interface.ISY

'''
Notes from https://github.com/UniversalDevicesInc/udi_python_interface/blob/d620824c14a917add0b471295984da1d323a12a3/udi_interface/interface.py#L1140
db_getNodeDrivers(self, addr = None, init = False):
    Returns a list of nodes or a list of drivers that were saved in the
    database.
     If an address is specified, return the drivers for that node.
     If an array of addresses is specified, return the matching array of
       nodes.
     If addr == None, return the entire list of nodes.
    
    document what is returned here and in the API doc!
    
    driver array [
       {id, uuid, profileNum, address, driver, value, uom, timeAdded,
        timeModified, dbVersion},
    ]
    
    node array [
       {id, uuid, profileNum, address, name, nodeDefId, nls, hint,
        controller, primaryNode, private, isPrimary, enabled, timeAdded,
        timeModified, dbVersion [drivers]},
    ]
'''

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
This is our Panel Circuits controller node. 
'''   
class PanelNodeForCircuits(udi_interface.Node):
    id = 'panelForCircuits'
    drivers = [
            {'driver': 'ST', 'value': -1, 'uom': 73},
            {'driver': 'FREQ', 'value': -1, 'uom': 56},
            {'driver': 'PULSCNT', 'value': -1, 'uom': 56},
            {'driver': 'CLIEMD', 'value': -1, 'uom': 25},
            {'driver': 'TIME', 'value': -1, 'uom': 56},
            {'driver': 'GV1', 'value': -1, 'uom': 25},
            {'driver': 'GV2', 'value': -1, 'uom': 25},
            {'driver': 'GV3', 'value': -1, 'uom': 25},
            {'driver': 'GV4', 'value': -1, 'uom': 25},
            {'driver': 'GV5', 'value': -1, 'uom': 25},
            {'driver': 'GPV', 'value': -1, 'uom': 56}
            ]

    def __init__(self, polyglot, parent, address, name, spanIPAddress, bearerToken):
        super(PanelNodeForCircuits, self).__init__(polyglot, parent, address, name)

        # set a flag to short circuit setDriver() until the node has been fully
        # setup in the Polyglot DB and the ISY (as indicated by START event)
        self._initialized: bool = False

        self._fullyCreated: bool = False
        
        self.poly = polyglot
        self.n_queue = []
        self.parent = parent

        self.childCircuitNodes: SPAN_circuit.CircuitNode = []
        self.expectedNumberOfChildrenCircuits = 0
        self.allExpectedChildrenCreated: bool = False
        
        self.ISY = ISY(self.poly)

        LOGGER.debug("\n\tINIT Panel Circuit Controller " + address + "'s parent is '" + parent + "' when INIT'ing.\n")

        #self.Parameters = Custom(polyglot, 'customparams')
        self.ipAddress = spanIPAddress
        self.token = bearerToken

        tokenLastTen = self.token[-10:]
        LOGGER.debug("\n\tINIT Panel Circuit Controller's IP Address:" + self.ipAddress + "; Bearer Token (last 10 characters): " + tokenLastTen)

        self.allBreakersData = ''
        self.allCircuitsData = ''
        self.pollInProgress: bool = False
        
        # subscribe to the events we want
        #polyglot.subscribe(polyglot.POLL, self.pollCircuitController)
        polyglot.subscribe(polyglot.STOP, self.stop)
        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.ADDNODEDONE, self.node_queue)
        polyglot.subscribe(polyglot.DELETE, self.delete)

    '''
    node_queue() and wait_for_node_event() create a simple way to wait
    for a node to be created.  The nodeAdd() API call is asynchronous and
    will return before the node is fully created. Using this, we can wait
    until it is fully created before we try to use it.
    '''
    def node_queue(self, data):
        if self.address == data['address']:
            LOGGER.debug("\n\t\t\tPanelForCircuits Controller Creation Completed; Queue Circuit child node(s) creation.\n")
            #lastOctet_array = self.ipAddress.split('.')
            #lastOctet = lastOctet_array[len(lastOctet_array)-1]
            #self.setDriver('FREQ', lastOctet, True, True, None, self.ipAddress)
        
            self.setDriver('ST', -1, True, True)
            self.setDriver('FREQ', -1, True, True)
            self.setDriver('PULSCNT', -1, True, True)
            self.setDriver('CLIEMD', -1, True, True)
            self.setDriver('TIME', -1, True, True)
            self.setDriver('GV1', -1, True, True)
            self.setDriver('GV2', -1, True, True)            

            self.setDriver('GPV', -1, True, True)
            
            self.pushTextToDriver('FREQ',self.ipAddress.replace('.','-'))

            if not(self.pollInProgress): 
                self.updateAllCircuitsData()
            
            if "circuits" in self.allCircuitsData:
                LOGGER.debug("\n\tINIT Panel Circuit Controller's Circuits Data: \n\t\t" + self.allCircuitsData + "\n\t\tCount of circuits: " + str(self.allCircuitsData.count(chr(34) + 'id' + chr(34) + ':')) + "\n")
                self.expectedNumberOfChildrenCircuits = self.allCircuitsData.count(chr(34) + 'id' + chr(34) + ':')
                self.setDriver('PULSCNT', self.expectedNumberOfChildrenCircuits, True, True)
                self.setDriver('CLIEMD', 1, True, True)
                
                self.createCircuits()
            else:
                LOGGER.warning("\n\tINIT Issue getting Circuits Data for Panel Circuits Controller '" + self.address + "' @ " + self.ipAddress + ".\n")
                
            self._fullyCreated = True
            self.n_queue.append(data['address'])
    

    def wait_for_node_done(self):
        while len(self.n_queue) == 0:
            time.sleep(0.1)
        self.n_queue.pop()

    # called by the interface after the node data has been put in the Polyglot DB
    # and the node created/updated in the ISY
    def start(self):
        # set the initlized flag to allow setDriver to work
        self._initialized = True
        self.setDriver('GPV', -1, True, True)
        
    def delete(self, address):
        if address == self.address:
            LOGGER.warning("\n\tDELETE COMMAND RECEIVED for self ('" + self.address + "')\n")
        else:
            LOGGER.debug("\n\tDELETE COMMAND RECEIVED for '" + address + "'\n")
    
    # overload the setDriver() of the parent class to short circuit if 
    # node not initialized
    def setDriver(self, driver: str, value: Any, report: bool=True, force: bool=False, uom: Optional[int]=None, text: Optional[str]=None):
        if self._initialized and self._fullyCreated:
            super().setDriver(driver, value, report, force, uom, text)

    '''
    Handling for <text /> attribute across PG3 and PG3x.
    Note that to be reported to IoX, the value has to change; this is why we flip from 0 to 1 or 1 to 0.
    -1 is reserved for initializing.
    '''
    def pushTextToDriver(self,driver,stringToPublish):
        if not(self._fullyCreated) or not(self._initialized):
            return
        stringToPublish = stringToPublish.replace('.',' ')
        if len(str(self.getDriver(driver))) <= 0:
            LOGGER.warning("\n\tPUSHING REPORT ERROR - a (correct) Driver was not passed for '" + self.address + "' trying to update driver " + driver + ".\n")
            return
        
        currentValue = int(self.getDriver(driver))
        newValue = -1
        encodedStringToPublish = urllib.parse.quote(stringToPublish, safe='')

        if currentValue != 1:
            newValue = 1
            message = {
                'set': [{
                    'address': self.address,
                    'driver': driver,
                    'value': 1,
                    'uom': 56,
                    'text': encodedStringToPublish
                }]
            }
            
        else:
            newValue = 0
            message = {
                'set': [{
                    'address': self.address,
                    'driver': driver,
                    'value': 0,
                    'uom': 56,
                    'text': encodedStringToPublish
                }]
            }

        self.setDriver(driver, newValue, False)

        if 'isPG3x' in self.poly.pg3init and self.poly.pg3init['isPG3x'] is True:
            #PG3x can use this, but PG3 doesn't have the necessary 'text' handling within message, set above, so we have the 'else' below
            LOGGER.debug("\n\tPUSHING REPORT TO '" + self.address + "' for driver " + driver + ", with PG3x via self.poly.send('" + encodedStringToPublish + "','status') with a value of '" + str(newValue) + "'.\n")
            self.poly.send(message, 'status')
        elif not(self.ISY.unauthorized):
            userpassword = self.ISY._isy_user + ":" + self.ISY._isy_pass
            userpasswordAsBytes = userpassword.encode("ascii")
            userpasswordAsBase64Bytes = base64.b64encode(userpasswordAsBytes)
            userpasswordAsBase64String = userpasswordAsBase64Bytes.decode("ascii")
    
            if len(self.ISY._isy_ip) > 0 and len(userpasswordAsBase64String) > 0:
                localConnection = http.client.HTTPConnection(self.ISY._isy_ip, self.ISY._isy_port)
                payload = ''
                headers = {
                    "Authorization": "Basic " + userpasswordAsBase64String
                }
                
                LOGGER.debug("\n\tPUSHING REPORT TO '" + self.address + "' for driver " + driver + ", with PG3 via " + self.ISY._isy_ip + ":" + str(self.ISY._isy_port) + ", with a value of " + str(newValue) + ", and a text attribute (encoded) of '" + encodedStringToPublish + "'.\n")
        
                prefixN = str(self.poly.profileNum)
                if len(prefixN) < 2:
                    prefixN = 'n00' + prefixN + '_'
                elif len(prefixN) < 3:
                    prefixN = 'n0' + prefixN + '_'
                
                suffixURL = '/rest/ns/' + str(self.poly.profileNum) + '/nodes/' + prefixN + self.address + '/report/status/' + driver + '/' + str(newValue) + '/56/text/' + encodedStringToPublish

                try:
                    localConnection.request("GET", suffixURL, payload, headers)
                    localResponse = localConnection.getresponse()
                    
                    localResponseData = localResponse.read()
                    localResponseData = localResponseData.decode("utf-8")
                    
                    if '<status>200</status>' not in localResponseData:
                        LOGGER.warning("\n\t\tPUSHING REPORT ERROR on '" + self.address + "' for " + driver + ": RESPONSE from report was not '<status>200</status>' as expected:\n\t\t\t" + localResponseData + "\n")
                except:
                    LOGGER.error("\n\t\tPUSHING REPORT ERROR on '" + self.address + "' for " + driver + " had an ERROR.\n")
        else:
            LOGGER.warning("\n\t\PUSHING REPORT ERROR on '" + self.address + "' for " + driver + ": looks like this is a PG3 install but the ISY authorization state seems to currently be 'Unauthorized': 'True'.\n")
    
    #def updateNode(self, passedAllCircuitsData, dateTimeString):
    #    self.allCircuitsData = passedAllCircuitsData

    '''
    This is where the real work happens.  When we get a shortPoll, do some work.
    Note: the Circuit and Breaker controllers will query and then pass data to the child nodes of Circuits and Breakers, respectively, so that we don't async hammer the http connection of SPAN panels. 
    '''
    def pollCircuitController(self, polltype):
        LOGGER.debug("\n\tPOLL CIRCUIT CONTROLLER: " + polltype + " for '" + self.address + "'.\n")
        if 'shortPoll' in polltype:

            if "|poll passed from root controller" in polltype:
                LOGGER.debug("\n\tCIRCUIT CONTROLLER '" + self.address + "' - HANDLING SHORT POLL passed from root controller\n")

            if "|poll passed from sister controller" in polltype:
                LOGGER.debug("\n\tCIRCUIT CONTROLLER '" + self.address + "' - HANDLING SHORT POLL passed from sister controller\n")
            
            if "-1" in str(self.getDriver('FREQ')):
                self.pushTextToDriver('FREQ',self.ipAddress.replace('.','-'))

            if "-1" in str(self.getDriver('GPV')):
                self.pushTextToDriver('GPV','NodeServer RUNNING')

            if "-1" in str(self.getDriver('CLIEMD')):
                self.setDriver('CLIEMD', 1, True, True)

            if "-1" in str(self.getDriver('PULSCNT')):
                self.setDriver('PULSCNT', self.allCircuitsData.count(chr(34) + 'id' + chr(34) + ':'), True, True)
        
            tokenLastTen = self.token[-10:]
            LOGGER.debug("\n\tPOLL About to query Panel Circuits Controller '" + self.address + "' @ {}, using token ending in {}".format(self.ipAddress,tokenLastTen))
            
            if not(self.pollInProgress):
                self.updateAllCircuitsData()
            
            if "circuits" in self.allCircuitsData:
                
                nowEpoch = int(time.time())
                nowDT = datetime.datetime.fromtimestamp(nowEpoch)
                self.pushTextToDriver('TIME',nowDT.strftime("%m/%d/%Y %I:%M:%S %p"))

                circuitCount = len(self.childCircuitNodes)
                currentPanelCircuitPrefix = "s" + self.address.replace('panelcircuit_','') + "_circuit_"

                if circuitCount == self.expectedNumberOfChildrenCircuits and self._initialized and self._fullyCreated:
                    self.allExpectedChildrenCreated = True
                elif circuitCount == 0 and self._initialized and self._fullyCreated:
                    LOGGER.warning("\n\tController '" + self.address + "' is fully ready, but upon getting ready to query child Circuit nodes, it was noticed that there are 0 child Circuit nodes created. Will call createCircuits() now.\n")
                    self.createCircuits()
                elif circuitCount < self.expectedNumberOfChildrenCircuits and self._initialized and self._fullyCreated:
                    LOGGER.warning("\n\tController '" + self.address + "' is fully ready, but upon getting ready to query child Circuit nodes, it was noticed that there are FEWER child Circuit nodes created (" + str(circuitCount) + ") than expected (" + str(self.expectedNumberOfChildrenCircuits) + ").\n")
                elif circuitCount > self.expectedNumberOfChildrenCircuits and self._initialized and self._fullyCreated:
                    LOGGER.warning("\n\tController '" + self.address + "' is fully ready, but upon getting ready to query child Circuit nodes, it was noticed that there are MORE child Circuit nodes created (" + str(circuitCount) + ") than expected (" + str(self.expectedNumberOfChildrenCircuits) + ").\n")
                else:
                    LOGGER.warning("\n\tStill awaiting fully ready controller '" + self.address + "' before querying child Circuit nodes...\n\t\tcircuitCount: " + str(circuitCount) + "|self.expectedNumberOfChildrenCircuits: " + str(self.expectedNumberOfChildrenCircuits) + "|self._initialized: " + str(self._initialized) + "|self._fullyCreated: " + str(self._fullyCreated) + ".\n")
                
                if circuitCount < 1 and self._fullyCreated and self.allExpectedChildrenCreated:
                    LOGGER.warning("\n\tERROR in Circuit Controller Child Count for '" + self.address + "'; attempting to recover by searching for nodes with the name '" + currentPanelCircuitPrefix + "'...\n")
                    nodes = self.poly.getNodes()
                    for node in nodes:
                        if currentPanelCircuitPrefix in node:
                            self.childCircuitNodes.append(node)
                    circuitCount = len(self.childCircuitNodes)
                    if circuitCount < 1:
                        LOGGER.warning("\n\t\tERROR in Circuit Controller Child Count PERSISTS: Even after seeing a 0 count of child circuit nodes, and attempting to update the list of child circuit nodes, under controller '" + self.address + "', the NodeServer is still unable to find any child circuit nodes.\n\t\tIf this persists repeatedly across multiple shortPolls, contact developer.")
                        self.pushTextToDriver('GPV',"Unexpected Child Circuit Node Count error < 1; attempting recovery")
                        #self.createCircuits()
                    else:
                        LOGGER.warning("\n\t\tCORRECTED Circuit Controller Child Count ERROR - the Circuit Controller Child Count was 0, but now it is showing as " + str(circuitCount) + ".\n")
                        self.pushTextToDriver('GPV',"NodeServer RUNNING")
                else:
                    self.pushTextToDriver('GPV',"NodeServer RUNNING")
                    
                for i in range(0, circuitCount):
                    try:
                        self.childCircuitNodes[i].updateCircuitNode(self.allCircuitsData, nowDT.strftime("%m/%d/%Y %I:%M:%S %p"), self.allBreakersData)
                        LOGGER.debug("\n\t\tPOLL SUCCESS in Circuits Controller '" + self.address + "' for '" + self.childCircuitNodes[i].address + "'.\n")
                    except:
                        LOGGER.warning("\n\tUPDATE CIRCUIT NODE error for '" + self.childCircuitNodes[i] + "'.\n")
                            
            else:
                tokenLastTen = self.token[-10:]
                LOGGER.warning("\n\tPOLL ERROR when querying Circuits Controller '" + self.address + "' @ IP address {}, using token {}.\n".format(self.ipAddress,tokenLastTen))
    
    '''
    Create the circuit nodes.
    TODO: Handle fewer circuit nodes by deleting (currently commented out)
    '''
    def createCircuits(self):
        
        # delete any existing nodes but only under this panel
        currentPanelCircuitPrefix = "s" + self.address.replace('panelcircuit_','') + "_circuit_"
        nodes = self.poly.getNodes()
        for node in nodes.copy():
             if currentPanelCircuitPrefix in node:
                LOGGER.warning("\n\tDeleting " + node + " when creating child Circuit nodes for Panel Circuits controller at " + self.address + ".\n")
                self.poly.delNode(node)

        how_many = self.getDriver('PULSCNT')
        
        allCircuitsArray = self.allCircuitsData.split(chr(34) + 'id' + chr(34) + ':')
        panelNumberPrefix = self.address
        panelNumberPrefix = panelNumberPrefix.replace('panelcircuit_','')

        LOGGER.debug("\n\tHere is where we'll be creating Circuit children nodes for Panel Circuits controller " + self.address + ". It should be a total of " + str(how_many) + " child nodes, each with an address starting with s" + panelNumberPrefix + "_circuit_...\n")

        for i in range(1, int(how_many)+1):
            LOGGER.debug("\n\tHere is the currentCircuitData:\n\t\t" + allCircuitsArray[i] + "\n")
            self.pushTextToDriver('GPV',"Initiating Circuit #" + str(i))
            
            current_IPaddress = self.ipAddress
            current_BearerToken = self.token
            
            address = 'S' + panelNumberPrefix + '_Circuit_' + str(i)
            address = getValidNodeAddress(address)
            
            current_circuitID_tuple = allCircuitsArray[i].partition(',')
            current_circuitID = current_circuitID_tuple[0]
            current_circuitID = current_circuitID.replace(chr(34),'')
            
            current_circuitName_tuple = allCircuitsArray[i].partition(chr(34) + 'name' + chr(34) + ':')
            current_circuitName = current_circuitName_tuple[2]
            current_circuitName_tuple = current_circuitName.partition(',')
            current_circuitName = current_circuitName_tuple[0]
            current_circuitName = current_circuitName.replace(chr(34),'')
            
            title = current_circuitName
            title = getValidNodeName(title)

            checkNodes = self.poly.getNodes()
            if address not in checkNodes:
                node = SPAN_circuit.CircuitNode(self.poly, self.address, address, title, current_IPaddress, current_BearerToken, current_circuitID, i)
                self.childCircuitNodes.append(node)
                node.setDriver('GPV', -1, True, True)
            else:
                try:
                    node = self.childCircuitNodes[self.childCircuitNodes.index(address)]
                except:
                    self.childCircuitNodes.append(checkNodes[address])
                    node = self.childCircuitNodes[self.childCircuitNodes.index(address)]
            
            self.poly.addNode(node)
            node.setDriver('GPV', -1, True, True)
            #node.wait_for_node_done()
            
            LOGGER.debug('\n\tCreated a Circuit child node {} under Panel Circuit Controller {}\n'.format(title, panelNumberPrefix))
        
        #self.pushTextToDriver('GPV',"NodeServer RUNNING")

    '''
    This is how we handle whenever our sister Breaker controller updates its allBreakersData variable
    '''
    def updateCircuitControllerStatusValuesFromPanelQueryInBreakerController(self, totalPowerPassed, dateTimeStringPassed, allBreakersDataPassed):
        LOGGER.info("\n\t Using Shared Data from sister Breaker Controller to update 'ST' and 'TIME' on '" + self.address + "'.\n")
        self.setDriver('ST', totalPowerPassed, True, True)
        self.pushTextToDriver('TIME', dateTimeStringPassed)
        
        self.allBreakersData = allBreakersDataPassed
        
        self.pollCircuitController("shortPoll|poll passed from sister controller")

    '''
    This is how we update the allCircuitsData variable
    '''
    def updateAllCircuitsData(self):
        self.pollInProgress = True
        LOGGER.debug("\n\tUPDATING ALLCIRCUITSDATA for '" + self.address + "'...\n")
        
        spanConnection = http.client.HTTPConnection(self.ipAddress)
        payload = ''
        headers = {
            "Authorization": "Bearer " + self.token
        }

        try:
            spanConnection.request("GET", "/api/v1/circuits", payload, headers)
            circuitsResponse = spanConnection.getresponse()

            self.allCircuitsData = circuitsResponse.read()
            self.allCircuitsData = self.allCircuitsData.decode("utf-8")
            
            LOGGER.debug("\n\tUPDATE ALLCIRCUITSDATA: SPAN API GET request for Panel Circuits Controller '" + self.address + "' Circuits Data: \n\t\t " + self.allCircuitsData + "\n")
    
            self.pollInProgress = False
        except:
            LOGGER.error("\n\tUPDATE ALLCIRCUITSDATA: SPAN API GET request for Panel Circuits Controller '" + self.address + "' Circuits Data FAILED.\n")

    def updateDoorStatusEtc(self, doorStatus, unlockButtonPressesRemaining, serialString, firmwareVersionString, uptimeString):
        self.setDriver('GV1', doorStatus, True, True)
        self.setDriver('GV2', unlockButtonPressesRemaining, True, True)
        self.pushTextToDriver('GV3', serialString)
        self.pushTextToDriver('GV4', firmwareVersionString)
        self.pushTextToDriver('GV5', uptimeString)
            
    '''
    STOP Called
    '''
    def stop(self):
        LOGGER.debug("\n\tSTOP RECEIVED: Panel Circuit Controller handler '" + self.address + "'.\n")
        self.setDriver('ST', -1, True, True)
        self.setDriver('FREQ', -1, True, True)
        self.setDriver('PULSCNT', -1, True, True)
        self.setDriver('CLIEMD', -1, True, True)
        self.setDriver('TIME', -1, True, True)
        self.setDriver('GV1', -1, True, True)
        self.setDriver('GV2', -1, True, True)
        #self.setDriver('GV3', -1, True, True)
        #self.setDriver('GV4', -1, True, True)
        self.pushTextToDriver('GV5','--')
        self.pushTextToDriver('GPV',"NodeServer STOPPED")
