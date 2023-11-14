#!/usr/bin/env python3
"""
Polyglot v3 NodeServer SPAN Smart Panels - Breakers Controller
Copyright (C) 2023 Matt Burke

MIT License
"""
import udi_interface
import sys
import time
import string
import re

from nodes import SPAN_breaker, SPAN_circuitController

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
just for when nodes get silly
'''
class fakeNode( object ):
    def wait_for_node_done(self):
        return

'''
This is our Panel Breakers controller node. 
'''
class PanelNodeForBreakers(udi_interface.Node):
    id = 'panelForBreakers'
    drivers = [
            {'driver': 'ST', 'value': 0, 'uom': 73},
            {'driver': 'FREQ', 'value': -1, 'uom': 56},
            {'driver': 'PULSCNT', 'value': 0, 'uom': 56},
            {'driver': 'GV0', 'value': 0, 'uom': 56},
            {'driver': 'TIME', 'value': -1, 'uom': 56},
            {'driver': 'GV1', 'value': -1, 'uom': 25},
            {'driver': 'GV2', 'value': -1, 'uom': 25},
            {'driver': 'GV3', 'value': -1, 'uom': 25},
            {'driver': 'GV4', 'value': -1, 'uom': 25},
            {'driver': 'GV5', 'value': -1, 'uom': 25},
            {'driver': 'GPV', 'value': -1, 'uom': 56}
            ]

    def __init__(self, polyglot, parent, address, name, spanIPAddress, bearerToken, sisterCircuitsControllerPassed):
        super(PanelNodeForBreakers, self).__init__(polyglot, parent, address, name)

        # set a flag to short circuit setDriver() until the node has been fully
        # setup in the Polyglot DB and the ISY (as indicated by START event)
        self._initialized: bool = False

        self._fullyCreated: bool = False
        
        self.poly = polyglot
        self.n_queue = []
        self.parent = parent
        self.sisterCircuitsController: SPAN_circuitController.PanelNodeForCircuits = sisterCircuitsControllerPassed

        self.childBreakerNodes: SPAN_breaker.BreakerNode = []
        self.expectedNumberOfChildrenBreakers = 32
        self.allExpectedChildrenCreated: bool = False

        self.ISY = ISY(self.poly)

        LOGGER.debug("\n\tINIT Panel Breaker Controller " + address + "'s parent is '" + parent + "' when INIT'ing.\n")

        self.ipAddress = spanIPAddress
        self.token = bearerToken

        tokenLastTen = self.token[-10:]
        LOGGER.debug("\n\tINIT Panel Breaker Controller's IP Address:" + self.ipAddress + "; Bearer Token (last 10 characters): " + tokenLastTen)

        self.allBreakersData = ''
        self.pollInProgress: bool = False

        self.statusPollInProgress: bool = False
        
        # subscribe to the events we want
        #polyglot.subscribe(polyglot.POLL, self.pollBreakerController)
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
            LOGGER.debug("\n\t\t\tPanelForBreakers Controller Creation Completed; Queue Breaker child node(s) creation.\n")
            
            #lastOctet_array = self.ipAddress.split('.')
            #lastOctet = lastOctet_array[len(lastOctet_array)-1]
            #self.setDriver('FREQ', lastOctet, True, True, None, self.ipAddress)

            self.setDriver('ST', -1, True, True)
            self.setDriver('FREQ', -1, True, True)
            self.setDriver('PULSCNT', 0, True, True)
            self.setDriver('GV0', 0, True, True)
            self.setDriver('TIME', -1, True, True)
            self.setDriver('GV1', -1, True, True)
            self.setDriver('GV2', -1, True, True)

            self.setDriver('GPV', -1, True, True)
            
            self.pushTextToDriver('FREQ', self.ipAddress.replace('.','-'))

            if not(self.pollInProgress):
                self.updateAllBreakersData()
        
            if "branches" in self.allBreakersData:
                feedthroughPowerW_tuple = self.allBreakersData.partition(chr(34) + "feedthroughPowerW" + chr(34) + ":")
                feedthroughPowerW = feedthroughPowerW_tuple[2]
                feedthroughPowerW_tuple = feedthroughPowerW.partition(",")
                feedthroughPowerW = feedthroughPowerW_tuple[0]
                feedthroughPowerW = math.ceil(float(feedthroughPowerW)*100)/100

                instantGridPowerW_tuple = self.allBreakersData.partition(chr(34) + "instantGridPowerW" + chr(34) + ":")
                instantGridPowerW = instantGridPowerW_tuple[2]
                instantGridPowerW_tuple = instantGridPowerW.partition(",")
                instantGridPowerW = instantGridPowerW_tuple[0]
                instantGridPowerW = math.ceil(float(instantGridPowerW)*100)/100

                #if it turns out we need to handle feedthroughPower separately, subtract it from the main
                #tracking from SPAN app generally seems to track more closely with what's show there by doing this subtraction... Shrug?
                self.setDriver('ST', round((instantGridPowerW-abs(feedthroughPowerW)),2), True, True)
                #otherwise, use the main directly
                #self.setDriver('ST', (instantGridPowerW), True, True)

                allBranchesData_tuple = self.allBreakersData.partition(chr(34) + "branches" + chr(34) + ":")
                allBranchesData = allBranchesData_tuple[2]
                LOGGER.debug("\n\tINIT Panel Breaker Controller's Branches Data: \n\t\t" + allBranchesData + "\n\t\tCount of OPEN Breakers: " + str(allBranchesData.count(chr(34) + 'OPEN' + chr(34) + ',')) + "\n\t\tCount of CLOSED Breakers: " + str(allBranchesData.count(chr(34) + 'CLOSED' + chr(34) + ',')) + "\n")
                self.setDriver('PULSCNT', allBranchesData.count(chr(34) + 'CLOSED' + chr(34) + ','), True, True)
                self.setDriver('GV0', allBranchesData.count(chr(34) + 'OPEN' + chr(34) + ','), True, True)

                nowEpoch = int(time.time())
                nowDT = datetime.datetime.fromtimestamp(nowEpoch)
                self.pushTextToDriver('TIME',nowDT.strftime("%m/%d/%Y %I:%M:%S %p"))
                
                self.createBreakers()
            else:
                LOGGER.warning("\n\tINIT Issue getting first-time Breakers Data for Panel Breaker Controller '" + self.address + "' @ " + self.ipAddress + ".\n")

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
        stringToPublish = stringToPublish.replace('.','')
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
                        LOGGER.warning("\n\t\tPUSHING REPORT ERROR on '" + self.address + "' for driver " + driver + ": RESPONSE from report was not '<status>200</status>' as expected:\n\t\t\t" + localResponseData + "\n")
                except:
                    LOGGER.error("\n\t\tPUSHING REPORT ERROR on '" + self.address + "' for " + driver + " had an ERROR.\n")
        else:
            LOGGER.warning("\n\t\PUSHING REPORT ERROR on '" + self.address + "' for driver " + driver + ": looks like this is a PG3 install but the ISY authorization state seems to currently be 'Unauthorized': 'True'.\n")

    #def updateNode(self, passedAllBreakersData, dateTimeString):
    #    self.allBreakersData = passedAllBreakersData

    '''
    This is where the real work happens.  When we get a shortPoll, do some work. 
    '''
    def pollBreakerController(self, polltype):
        if self.pollInProgress:
            return
        LOGGER.debug("\n\tPOLL BREAKER CONTROLLER: " + polltype + " for '" + self.address + "'.\n")
        if 'shortPoll' in polltype:
            
            if "|poll passed from root controller" in polltype:
                LOGGER.debug("\n\tBREAKER CONTROLLER '" + self.address + "' - HANDLING SHORT POLL passed from root controller\n")
                            
            if "-1" in str(self.getDriver('FREQ')):
                self.pushTextToDriver('FREQ',self.ipAddress.replace('.','-'))

            if "-1" in str(self.getDriver('GPV')):
                self.pushTextToDriver('GPV','NodeServer RUNNING')
            
            tokenLastTen = self.token[-10:]
            LOGGER.debug("\n\tPOLL About to query Panel Breaker Controller '" + self.address + "' @ {}, using token ending in {}".format(self.ipAddress,tokenLastTen))

            if not(self.pollInProgress):
                self.updateAllBreakersData()
           
            if "branches" in self.allBreakersData:
                
                feedthroughPowerW_tuple = self.allBreakersData.partition(chr(34) + "feedthroughPowerW" + chr(34) + ":")
                feedthroughPowerW = feedthroughPowerW_tuple[2]
                feedthroughPowerW_tuple = feedthroughPowerW.partition(",")
                feedthroughPowerW = feedthroughPowerW_tuple[0]
                feedthroughPowerW = math.ceil(float(feedthroughPowerW)*100)/100

                instantGridPowerW_tuple = self.allBreakersData.partition(chr(34) + "instantGridPowerW" + chr(34) + ":")
                instantGridPowerW = instantGridPowerW_tuple[2]
                instantGridPowerW_tuple = instantGridPowerW.partition(",")
                instantGridPowerW = instantGridPowerW_tuple[0]
                instantGridPowerW = math.ceil(float(instantGridPowerW)*100)/100

                #if it turns out we need to handle feedthroughPower separately, subtract it from the main
                #tracking from SPAN app generally seems to track more closely with what's show there by doing this subtraction... Shrug?
                self.setDriver('ST', round((instantGridPowerW-abs(feedthroughPowerW)),2), True, True)
                #otherwise, use the main directly
                #self.setDriver('ST', (instantGridPowerW), True, True)

                LOGGER.warning("\n\tNEW POLL OF DATA QUEUED (via '" + polltype + "'); Total Power of Panel #" + self.address.replace('panelbreaker_','') + " @ " + self.ipAddress + " = " + str(round((instantGridPowerW-abs(feedthroughPowerW)),2)) + ", calculated via instantGridPowerW - feedthroughPowerW, where " + chr(34) + "instantGridPowerW" + chr(34) + " = " + str(instantGridPowerW) + " and " + chr(34) + "feedthroughPowerW" + chr(34) + " = " + str(feedthroughPowerW) + ".\n")

                allBranchesData_tuple = self.allBreakersData.partition(chr(34) + "branches" + chr(34) + ":")
                allBranchesData = allBranchesData_tuple[2]
                LOGGER.debug("\n\tSHORT POLL Panel Breaker Controller '" + self.address + "' - Branches Data: \n\t\t" + allBranchesData + "\n\t\tCount of OPEN Breakers: " + str(allBranchesData.count(chr(34) + 'OPEN' + chr(34) + ',')) + "\n\t\tCount of CLOSED Breakers: " + str(allBranchesData.count(chr(34) + 'CLOSED' + chr(34) + ',')) + "\n")
                self.setDriver('PULSCNT', allBranchesData.count(chr(34) + 'CLOSED' + chr(34) + ','), True, True)
                self.setDriver('GV0', allBranchesData.count(chr(34) + 'OPEN' + chr(34) + ','), True, True)
                
                if len(str(instantGridPowerW)) > 0:
                    nowEpoch = int(time.time())
                    nowDT = datetime.datetime.fromtimestamp(nowEpoch)
                    self.pushTextToDriver('TIME',nowDT.strftime("%m/%d/%Y %I:%M:%S %p"))

                nodes = self.poly.getNodes()
                currentPanelBreakerPrefix = "s" + self.address.replace('panelbreaker_','') + "_breaker_"
                LOGGER.debug("\n\tWill be looking for Breaker nodes with this as the prefix: '" + currentPanelBreakerPrefix + "'.\n")
                recreateBreakers = False
                problemChildren = ''

                breakerCount = len(self.childBreakerNodes)
                #we want 32 entities; if we have too many, figure it out.
                if breakerCount != 32 and self._fullyCreated:
                    LOGGER.warning("\n\tBREAKER CHILD NODE TRACKING ERROR: Any Breaker Controller Node should be tracking exactly 32 child Breaker Nodes; as it stands right now, controller '" + self.address + "' is tracking " + str(breakerCount-1) + " child Breaker Nodes.\n")

                if breakerCount == self.expectedNumberOfChildrenBreakers and self._initialized:
                    self._fullyCreated = True
                    self.allExpectedChildrenCreated = True
                
                for i in range(0,32):
                    node = currentPanelBreakerPrefix + str(i+1)
                    LOGGER.debug("\n\tUpdating " + node + " (which should be a Breaker node under this Breakers controller: " + self.address + ").\n")
                    nowEpoch = int(time.time())
                    nowDT = datetime.datetime.fromtimestamp(nowEpoch)
                    try:
                        #nodes[node].updateBreakerNode(self.allBreakersData, nowDT.strftime("%m/%d/%Y %I:%M:%S %p"))
                        self.childBreakerNodes[i].updateBreakerNode(self.allBreakersData, nowDT.strftime("%m/%d/%Y %I:%M:%S %p"))
                    except:
                        LOGGER.warning("\n\tERROR When Attempting to Update " + node + " (which should be a Breaker node under this Breakers controller: " + self.address + ").\n")
                        try:
                            nodes = self.poly.getNodes()
                            for node in nodes:
                                if currentPanelBreakerPrefix in node:
                                    self.childBreakerNodes.append(node)
                            breakerCount = len(self.childBreakerNodes)
                            LOGGER.warning("\n\t\tInitially there was an error handling the childBreakerNodes, but now we have " + breakerCount.string + " childBreakerNodes.\n")
                        except:
                            LOGGER.warning("\n\t\tERROR When Attempting to Set self.childBreakerNodes[" + i.string + "] to " + node + ".\n") 
                            if len(problemChildren) > 0:
                                problemChildren = problemChildren + ", "
                            problemChildren = problemChildren + "'" + node + "'"
                            recreateBreakers = True
                            
                if recreateBreakers and self.allExpectedChildrenCreated:
                    LOGGER.warning("\n\tUnable to execute updateBreakerNode on (" + problemChildren + ") Breaker node(s) [" + nowDT.strftime("%m/%d/%Y %I:%M:%S %p") + "].\n\t\tIf this persists repeatedly across multiple shortPolls with the same node ID(s) and/or the list is not getting shorter each time, contact developer.")
                    self.pushTextToDriver('GPV',"Unexpected Child Breaker Node Update error " + str(breakerCount) + " != 32; attempting recovery")
                    #self.createBreakers()
                elif recreateBreakers and not(self.allExpectedChildrenCreated) and (not(self._fullyCreated) or not(self._initialized)):
                    LOGGER.warning("\n\tStill awaiting fully ready controller '" + self.address + "' before querying child Breaker nodes...\n")
                elif recreateBreakers and not(self.allExpectedChildrenCreated):
                    LOGGER.warning("\n\tController '" + self.address + "' is fully ready, but upon getting ready to query child Breaker nodes, it was noticed that there are NOT 32 child Breaker nodes as expected...\n\t\tbreakerCount (expecting 32): " + str(breakerCount) + "|self._initialized: " + str(self._initialized) + "|self._fullyCreated: " + str(self._fullyCreated) + ".\n\t\tProblem children: " + problemChildren + "\n")
                else:
                    self.pushTextToDriver('GPV',"NodeServer RUNNING")

            else:
                tokenLastTen = self.token[-10:]
                LOGGER.warning("\n\tPOLL ERROR when querying Breakers Controller '" + self.address + "' @ IP address {}, using token {}.\n".format(self.ipAddress,tokenLastTen))
            
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
        
        allBreakersArray = self.allBreakersData.split(chr(34) + 'id' + chr(34) + ':')
        panelNumberPrefix = self.address
        panelNumberPrefix = panelNumberPrefix.replace('panelbreaker_','')

        LOGGER.debug("\n\tHere is where we'll be creating Breaker children nodes for " + self.address + ". It should be a total of 32 child nodes, each with an address starting with s" + panelNumberPrefix + "_breaker_...\n")

        for i in range(1, 33):
            LOGGER.debug("\n\tHere is the currentBreakersData:\n\t\t" + allBreakersArray[i] + "\n")
            
            current_IPaddress = self.ipAddress
            current_BearerToken = self.token
            
            address = 'S' + panelNumberPrefix + '_Breaker_' + str(i)
            address = getValidNodeAddress(address)
            
            title = "Breaker #"
            if i < 10:
                title = title + "0"
            title = title + str(i)
            title = getValidNodeName(title)

            checkNodes = self.poly.getNodes()
            if address not in checkNodes:
                node = SPAN_breaker.BreakerNode(self.poly, self.address, address, title, current_IPaddress, current_BearerToken, i)                
                self.childBreakerNodes.append(node)

                node.setDriver('GPV', -1, True, True)
            else:
                try:
                    node = self.childBreakerNodes[self.childBreakerNodes.index(address)]
                except:
                    #self.childBreakerNodes.append(checkNodes[address])
                    #Documentation says: address, name, [node_def_]id, primary, and drivers are required 
                    #  In reality, it looks like hint and private are also required
                    node = fakeNode()
                    node.address = address
                    node.name = title
                    node.id = self.poly.profileNum
                    node.primary = self.address
                    node.hint = ''
                    node.private = ''
                    node.drivers = [
                                {'driver': 'ST', 'value': -1, 'uom': 73},
                                {'driver': 'PULSCNT', 'value': -1, 'uom': 56},
                                {'driver': 'CLIEMD', 'value': 0, 'uom': 25},
                                {'driver': 'AWAKE', 'value': 0, 'uom': 25},
                                {'driver': 'TIME', 'value': -1, 'uom': 56},
                                {'driver': 'GV0', 'value': -1, 'uom': 56},
                                {'driver': 'GV1', 'value': -1, 'uom': 56},
                                {'driver': 'GV2', 'value': -1, 'uom': 56},
                                {'driver': 'GV3', 'value': -1, 'uom': 56},
                                {'driver': 'GV4', 'value': -1, 'uom': 56},
                                {'driver': 'GPV', 'value': -1, 'uom': 56}
                                ]
            
            try:
                self.poly.addNode(node)
                #node.wait_for_node_done()
                node.setDriver('GPV', -1, True, True)
            except:
                LOGGER.warning("\n\tUnable to create child Breaker node '" + node + "' for '" + self.address + "' at this time.\n")
            
            LOGGER.debug('\n\tCreated a Breaker child node {} under Panel Breaker controller {}\n'.format(title, panelNumberPrefix))

    '''
    This is how we update the allBreakersData variable
    '''
    def updateAllBreakersData(self):
        self.pollInProgress = True
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
            LOGGER.debug("\n\tUPDATE ALLBREAKERSDATA Panel Breaker Controller '" + self.address + "' Panel Data: \n\t\t" + self.allBreakersData + "\n")
        except:
            LOGGER.error("\n\tUPDATE ALLBREAKERSDATA Panel Breaker Controller '" + self.address + "' Panel Data had an ERROR.\n")
            
        if "branches" in self.allBreakersData:
            feedthroughPowerW_tuple = self.allBreakersData.partition(chr(34) + "feedthroughPowerW" + chr(34) + ":")
            feedthroughPowerW = feedthroughPowerW_tuple[2]
            feedthroughPowerW_tuple = feedthroughPowerW.partition(",")
            feedthroughPowerW = feedthroughPowerW_tuple[0]           
            feedthroughPowerW = math.ceil(float(feedthroughPowerW)*100)/100

            instantGridPowerW_tuple = self.allBreakersData.partition(chr(34) + "instantGridPowerW" + chr(34) + ":")
            instantGridPowerW = instantGridPowerW_tuple[2]
            instantGridPowerW_tuple = instantGridPowerW.partition(",")
            instantGridPowerW = instantGridPowerW_tuple[0]             
            instantGridPowerW = math.ceil(float(instantGridPowerW)*100)/100

            epoch = int(time.time())
            nowDT = datetime.datetime.fromtimestamp(epoch)

            #if it turns out we need to handle feedthroughPower separately, subtract it from the main
            #tracking from SPAN app generally seems to track more closely with what's show there by doing this subtraction... Shrug?            
            totalPower = round((instantGridPowerW-abs(feedthroughPowerW)),2)
            #otherwise, use the main directly
            #totalPower = (instantGridPowerW)

            self.sisterCircuitsController.updateCircuitControllerStatusValuesFromPanelQueryInBreakerController(totalPower, nowDT.strftime("%m/%d/%Y %I:%M:%S %p"), self.allBreakersData)
            LOGGER.info("\n\tUPDATE ALLBREAKERSDATA under '" + self.address + "' successfully found its sisterCircuitsController, and tried to update its allBreakersData as well as its total power ('ST') and 'TIME' Status elements.\n")

        self.pollInProgress = False
        
        if not(self.statusPollInProgress):
                self.updateDoorStatusEtc()

    def updateDoorStatusEtc(self):
        self.statusPollInProgress = True
        
        doorStatus = 0
        unlockButtonPressesRemaining = -1
        serialString = 'Unknown'
        firmwareVersionString = 'Unknown'
        uptimeString = 'Unknown'
  
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
            LOGGER.debug("\n\tUPDATING PANEL STATUS for Panel Breaker Controller '" + self.address + "' (and its sister). Status Data: \n\t\t" + statusData + "\n")
            
            if "doorState" in statusData:
                doorState_tuple = statusData.partition(chr(34) + "doorState" + chr(34) + ":")
                doorState = doorState_tuple[2]
                doorState_tuple = doorState.partition(",")
                doorState = doorState_tuple[0]
                if "CLOSED" in doorState:
                    doorStatus = 1
                elif "OPEN" in doorState:
                    doorStatus = 2
            
            if "AuthUnlock" in statusData:
                authRemaining_tuple = statusData.partition(chr(34) + "remainingAuthUnlockButtonPresses" + chr(34) + ":")
                authRemaining = authRemaining_tuple[2]
                authRemaining_tuple = authRemaining.partition(",")
                authRemaining = authRemaining_tuple[0]
                if "3" in str(authRemaining):
                    unlockButtonPressesRemaining = 3
                elif "2" in str(authRemaining):
                    unlockButtonPressesRemaining = 2
                elif "1" in str(authRemaining):
                    unlockButtonPressesRemaining = 1
            
            if "serial" in statusData:
                serial_tuple = statusData.partition(chr(34) + "serial" + chr(34) + ":")
                serial = serial_tuple[2]
                serial_tuple = serial.partition(",")
                serialString = serial_tuple[0].replace(chr(34),'')
                
            if "firmwareVersion" in statusData:
                firmwareVersion_tuple = statusData.partition(chr(34) + "firmwareVersion" + chr(34) + ":")
                firmwareVersion = firmwareVersion_tuple[2]
                firmwareVersion_tuple = firmwareVersion.partition(",")
                firmwareVersionString = firmwareVersion_tuple[0].replace(chr(34),'')
            
            if "uptime" in statusData:
                uptime_tuple = statusData.partition(chr(34) + "uptime" + chr(34) + ":")
                uptime = uptime_tuple[2]
                uptime_tuple = uptime.partition(",")
                uptime = int(uptime_tuple[0].replace('}',''))
                (days, remainder) = divmod(uptime, 86400)
                (hours, remainder) = divmod(remainder, 3600)
                (minutes, seconds) = divmod(remainder, 60)
                uptimeString = str(days) + " Days, " + str(hours) + " Hours, " + str(minutes) + " Minutes, " + str(seconds) + " Seconds"
    
            LOGGER.warning("\n\tDOOR STATUS, ETC UPDATE for '" + self.address + "': doorStatus = " + str(doorStatus) + "; unlockButtonPressesRemaining = " + str(unlockButtonPressesRemaining) + "; serialString = " + serialString + "; firmwareVersionString = " + firmwareVersionString + "; uptimeString = " + uptimeString + ".\n")
            self.setDriver('GV1', doorStatus, True, True)
            self.setDriver('GV2', unlockButtonPressesRemaining, True, True)
            self.pushTextToDriver('GV3', serialString)
            self.pushTextToDriver('GV4', firmwareVersionString)
            self.pushTextToDriver('GV5', uptimeString)
            
            self.sisterCircuitsController.updateDoorStatusEtc(doorStatus, unlockButtonPressesRemaining, serialString, firmwareVersionString, uptimeString)
            
        except:
            LOGGER.error("\n\tUPDATING PANEL STATUS for Panel Breaker Controller '" + self.address + "' (and its sister) had an ERROR.\n")
          
        self.statusPollInProgress = False
    
    '''
    STOP Received
    '''
    def stop(self):
        LOGGER.debug("\n\tSTOP RECEIVED: Panel Breaker Controller handler '" + self.address + "'.\n")
        self.setDriver('ST', -1, True, True)
        self.setDriver('FREQ', -1, True, True)
        self.setDriver('PULSCNT', 0, True, True)
        self.setDriver('GV0', 0, True, True)
        self.setDriver('TIME', -1, True, True)
        self.setDriver('GV1', -1, True, True)
        self.setDriver('GV2', -1, True, True)
        self.pushTextToDriver('GV5','--')
        self.pushTextToDriver('GPV','NodeServer STOPPED')
        self.setDriver('GPV', -1, True, True)
