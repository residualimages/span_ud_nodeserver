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

import math,time,datetime,urllib.parse,http.client

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
    
class PanelNodeForCircuits(udi_interface.Node):
    id = 'panelForCircuits'
    drivers = [
            {'driver': 'ST', 'value': 0, 'uom': 73},
            {'driver': 'FREQ', 'value': -1, 'uom': 56},
            {'driver': 'PULSCNT', 'value': 0, 'uom': 56},
            {'driver': 'CLIEMD', 'value': 0, 'uom': 25},
            {'driver': 'TIME', 'value': 0, 'uom': 151},
            {'driver': 'HR', 'value': -1, 'uom': 56},
            {'driver': 'MOON', 'value': -1, 'uom': 56},
            {'driver': 'TIMEREM', 'value': -1, 'uom': 56},
            {'driver': 'GPV', 'value': -1, 'uom': 56}
            ]

    def __init__(self, polyglot, parent, address, name, spanIPAddress, bearerToken):
        super(PanelNodeForCircuits, self).__init__(polyglot, parent, address, name)

        # set a flag to short circuit setDriver() until the node has been fully
        # setup in the Polyglot DB and the ISY (as indicated by START event)
        self._initialized: bool = False
        
        self.poly = polyglot
        self.n_queue = []
        self.parent = parent

        LOGGER.debug("\n\tINIT Panel Circuit Controller " + address + "'s parent is '" + parent + "' when INIT'ing.\n")

        #self.Parameters = Custom(polyglot, 'customparams')
        self.ipAddress = spanIPAddress
        self.token = bearerToken

        tokenLastTen = self.token[-10:]
        LOGGER.debug("\n\tINIT Panel Circuit Controller's IP Address:" + self.ipAddress + "; Bearer Token (last 10 characters): " + tokenLastTen)

        self.allCircuitsData = ''
        
        # subscribe to the events we want
        polyglot.subscribe(polyglot.POLL, self.poll)
        polyglot.subscribe(polyglot.STOP, self.stop)
        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.ADDNODEDONE, self.node_queue)

    '''
    node_queue() and wait_for_node_event() create a simple way to wait
    for a node to be created.  The nodeAdd() API call is asynchronous and
    will return before the node is fully created. Using this, we can wait
    until it is fully created before we try to use it.
    '''
    def node_queue(self, data):
        if self.address == data['address']:
            LOGGER.debug("\n\t\t\tPanelForCircuits Controller Creation Completed; Queue Circuit child node(s) creation.\n")
            lastOctet_array = self.ipAddress.split('.')
            lastOctet = lastOctet_array[len(lastOctet_array)-1]
            self.setDriver('FREQ', lastOctet, True, True, None, self.ipAddress)

            self.updateAllCircuitsData()
            
            if self.allCircuitsData != '':
                LOGGER.debug("\n\tINIT Panel Circuit Controller's Circuits Data: \n\t\t" + self.allCircuitsData + "\n\t\tCount of circuits: " + str(self.allCircuitsData.count(chr(34) + 'id' + chr(34) + ':')) + "\n")
                self.setDriver('PULSCNT', self.allCircuitsData.count(chr(34) + 'id' + chr(34) + ':'), True, True)
                self.setDriver('CLIEMD', 1, True, True)
                
                self.createCircuits()
            else:
                LOGGER.warning("\n\tINIT Issue getting Circuits Data for Panel Circuits Controller '" + self.address + "' @ " + self.ipAddress + ".\n")
                
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
    
    # overload the setDriver() of the parent class to short circuit if 
    # node not initialized
    def setDriver(self, driver: str, value: Any, report: bool=True, force: bool=False, uom: Optional[int]=None, text: Optional[str]=None):
        if self._initialized:
            super().setDriver(driver, value, report, force, uom, text)

    '''
    Handling for <text /> attribute across PG3 and PG3x.
    Note that to be reported to IoX, the value has to change; this is why we flip from 0 to 1 or 1 to 0.
    -1 is reserved for initializing.
    '''
    def pushTextToDriver(self,driver,stringToPublish):
        if len(str(self.getDriver(driver))) <= 0:
            LOGGER.warning("\n\tPUSHING REPORT ERROR - a (correct) Driver was not passed.\n")
            return
        else:
            LOGGER.debug("\n\tLEN of self.getDriver('" + driver + "') is greater than 0; driver value = " + str(self.getDriver(driver)) + "\n")
        
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
            LOGGER.debug("\n\tPUSHING REPORT TO '" + self.address + "'-owned status variable / driver '" + driver + "' with PG3x via self.poly.send('" + encodedStringToPublish + "','status') with a value of '" + str(newValue) + "'.\n")
            self.poly.send(message, 'status')
        elif not(self.parent.ISY.unauthorized):
            userpassword = self.parent.ISY._isy_user + ":" + self.parent.ISY._isy_pass
            userpasswordAsBytes = userpassword.encode("ascii")
            userpasswordAsBase64Bytes = base64.b64encode(userpasswordAsBytes)
            userpasswordAsBase64String = userpasswordAsBase64Bytes.decode("ascii")
    
            localConnection = http.client.HTTPConnection(self.parent.ISY._isy_ip, self.parent.ISY._isy_port)
            payload = ''
            headers = {
                "Authorization": "Basic " + userpasswordAsBase64String
            }
            
            LOGGER.debug("n\tPUSHING REPORT TO '" + self.address + "'-owned status variable / driver '" + driver + "' with PG3 via " + self.parent.ISY._isy_ip + ":" + str(self.parent.ISY._isy_port) + ", with a value of " + str(newValue) + ", and a text attribute (encoded) of '" + encodedStringToPublish + "'.\n")
    
            prefixN = str(self.poly.profileNum)
            if len(prefixN) < 2:
                prefixN = 'n00' + prefixN + '_'
            elif len(prefixN) < 3:
                prefixN = 'n0' + prefixN + '_'
            
            suffixURL = '/rest/ns/' + str(self.poly.profileNum) + '/nodes/' + prefixN + self.address + '/report/status/GPV/' + str(newValue) + '/56/text/' + encodedStringToPublish
    
            localConnection.request("GET", suffixURL, payload, headers)
            localResponse = localConnection.getresponse()
            localResponseData = localResponse.read()
            localResponseData = localResponseData.decode("utf-8")
            
            if '<status>200</status>' not in localResponseData:
                LOGGER.warning("\n\t\tPUSHING REPORT ERROR - RESPONSE from report was not '<status>200</status>' as expected:\n\t\t\t" + localResponseData + "\n")
        else:
            LOGGER.warning("\n\t\PUSHING REPORT ERROR: looks like this is a PG3 install but the ISY authorization state seems to currently be 'Unauthorized': 'True'.\n")
    
    def updateNode(self, passedAllCircuitsData):
        self.allCircuitsData = passedAllCircuitsData

    '''
    This is where the real work happens.  When we get a shortPoll, do some work.
    Note: the Circuit and Breaker controllers will query and then pass data to the child nodes of Circuits and Breakers, respectively, so that we don't async hammer the http connection of SPAN panels. 
    '''
    def poll(self, polltype):
        if 'shortPoll' in polltype:

            nowEpoch = int(time.time())
            nowDT = datetime.datetime.fromtimestamp(nowEpoch)
            self.pushTextToDriver('GPV',nowDT.strftime("%m/%d/%Y %H:%M:%S"))
        
            tokenLastTen = self.token[-10:]
            LOGGER.debug("\n\tPOLL About to query Panel Circuits Controller '" + self.address + "' @ {}, using token ending in {}".format(self.ipAddress,tokenLastTen))
            
            self.updateAllCircuitsData()
            
            if self.allCircuitsData != '':
                nodes = self.poly.getNodes()
                currentPanelCircuitPrefix = "s" + self.address.replace('panelcircuit_','') + "_circuit_"
                LOGGER.debug("\n\tWill be looking for Circuit nodes with this as the prefix: '" + currentPanelCircuitPrefix + "'.\n")
                '''
                for i in range(1,33):
                    if i <= int(self.getDriver('PULSCNT')):
                        node = currentPanelCircuitPrefix + str(i)
                        LOGGER.debug("\n\tUpdating '" + node + "' (which should be a Circuit node under this Panel controller: " + self.address + ").\n")
                        
                        try:
                            epoch = self.getDriver('TIME')
                            hour = self.getDriver('HR')
                            minute = self.getDriver('MOON')
                            second = self.getDriver('TIMEREM')
                            nodes[node].updateNode(self.allCircuitsData, epoch, hour, minute, second)
                        except Exception as e:
                            LOGGER.warning('\n\tPOLL ERROR in Panel Circuits: Cannot seem to update node needed in for-loop due to error:\n\t\t{}\n'.format(e))
    
                    elif self.allCircuitsData.count(chr(34) + 'id' + chr(34) + ':') > int(self.getDriver('PULSCNT')):
                        LOGGER.warning("\n\tCIRCUIT COUNT INCREASED - upon short poll with Panel Circuit Controller '" + self.address + "' @ " + self.ipAddress + ", it seems like there are now MORE distinct circuits in SPAN, for a total of " + str(self.allCircuitsData.count(chr(34) + 'id' + chr(34) + ':')) + ", but originally this controller only had " + str(self.getDriver('PULSCNT')) + ".\n")
                        
                    else:
                        LOGGER.warning("\n\tCIRCUIT COUNT DECREASED - upon short poll with Panel Circuit Controller '" + self.address + "' @ " + self.ipAddress + ", it seems like there are now FEWER distinct circuits in SPAN, for a total of " + str(self.allCircuitsData.count(chr(34) + 'id' + chr(34) + ':')) + ", but originally this controller had " + str(self.getDriver('PULSCNT')) + ".\n")
                    '''
            else:
                 LOGGER.warning("\n\tUPDATE ALLCIRCUITSDATA failed to populate allCircuitsData.\n")
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
            try:
                node = SPAN_circuit.CircuitNode(self.poly, self.address, address, title, current_IPaddress, current_BearerToken, current_circuitID, i)
                self.poly.addNode(node)
                node.wait_for_node_done()
                LOGGER.debug('\n\tCreated a Circuit child node {} under Panel Circuit Controller {}\n'.format(title, panelNumberPrefix))
            except Exception as e:
                LOGGER.warning('\n\tFailed to create Circuit child node {} under Panel Circuit Controller {} due to error:\n\t\t{}\n'.format(title, panelNumberPrefix, e))

    '''
    This is how we handle whenever our 'sister' Breaker controller updates its allBreakersData variable
    '''
    def updateCircuitControllerStatusValuesFromPanelQueryInBreakerController(self, totalPower, epoch, hour, minute, second):
        LOGGER.debug("\n\t Using Shared Data from Breaker Controller to update 'ST', 'TIME', 'HR', 'MOON', 'TIMEREM'.\n")
        self.setDriver('ST', totalPower, True, True)
        self.setDriver('TIME', epoch, True, True)
        self.setDriver('HR', hour, True, True)
        self.setDriver('MOON', minute, True, True)
        self.setDriver('TIMEREM', second, True, True)

    '''
    This is how we update the allCircuitsData variable
    '''
    def updateAllCircuitsData(self):
        spanConnection = http.client.HTTPConnection(self.ipAddress)
        payload = ''
        headers = {
            "Authorization": "Bearer " + self.token
        }
        try:
            LOGGER.debug("n\tUPDATING ALLCIRCUITSDATA: SPAN API GET request for Panel Circuits Controller '" + self.address + "' being attempted to http://" + self.ipAddress + "/api/v1/circuits\n")
            spanConnection.request("GET", "/api/v1/circuits", payload, headers)
            circuitsResponse = spanConnection.getresponse()
            self.allCircuitsData = circuitsResponse.read()
            self.allCircuitsData = self.allCircuitsData.decode("utf-8")
            
        except Exception as e:
            LOGGER.warning("\n\tUPDATE ALLCIRCUITSDATA ERROR: SPAN API GET request for Panel Circuits Controller '" + self.address + "' failed due to error:\n\t\t{}\n".format(e))
            
    '''
    STOP Called
    '''
    def stop(self):
        LOGGER.debug("\n\tSTOP RECEIVED: Panel Circuit Controller handler '" + self.address + "'.\n")
        self.setDriver('ST', 0, True, True)
        self.setDriver('ST', 0, True, True)
        self.setDriver('TIME', -1, True, True)
        self.setDriver('HR', -1, True, True)
        self.setDriver('MOON', -1, True, True)
        self.setDriver('TIMEREM', -1, True, True)

'''
This is our PanelForBreakers device node. 
'''
class PanelNodeForBreakers(udi_interface.Node):
    id = 'panelForBreakers'
    drivers = [
            {'driver': 'ST', 'value': 0, 'uom': 73},
            {'driver': 'FREQ', 'value': -1, 'uom': 56},
            {'driver': 'PULSCNT', 'value': 0, 'uom': 56},
            {'driver': 'GV0', 'value': 0, 'uom': 56},
            {'driver': 'TIME', 'value': 0, 'uom': 151},
            {'driver': 'HR', 'value': -1, 'uom': 56},
            {'driver': 'MOON', 'value': -1, 'uom': 56},
            {'driver': 'TIMEREM', 'value': -1, 'uom': 56},
            {'driver': 'GPV', 'value': -1, 'uom': 56}
            ]

    def __init__(self, polyglot, parent, address, name, spanIPAddress, bearerToken):
        super(PanelNodeForBreakers, self).__init__(polyglot, parent, address, name)

        # set a flag to short circuit setDriver() until the node has been fully
        # setup in the Polyglot DB and the ISY (as indicated by START event)
        self._initialized: bool = False
        
        self.poly = polyglot
        self.n_queue = []
        self.parent = parent

        LOGGER.debug("\n\tINIT Panel Breaker Controller " + address + "'s parent is '" + parent + "' when INIT'ing.\n")

        self.ipAddress = spanIPAddress
        self.token = bearerToken

        tokenLastTen = self.token[-10:]
        LOGGER.debug("\n\tINIT Panel Breaker Controller's IP Address:" + self.ipAddress + "; Bearer Token (last 10 characters): " + tokenLastTen)

        self.allBreakersData = ''
        
        # subscribe to the events we want
        polyglot.subscribe(polyglot.POLL, self.poll)
        polyglot.subscribe(polyglot.STOP, self.stop)
        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.ADDNODEDONE, self.node_queue)

    '''
    node_queue() and wait_for_node_event() create a simple way to wait
    for a node to be created.  The nodeAdd() API call is asynchronous and
    will return before the node is fully created. Using this, we can wait
    until it is fully created before we try to use it.
    '''
    def node_queue(self, data):
        if self.address == data['address']:
            LOGGER.debug("\n\t\t\tPanelForBreakers Controller Creation Completed; Queue Breaker child node(s) creation.\n")
            
            lastOctet_array = self.ipAddress.split('.')
            lastOctet = lastOctet_array[len(lastOctet_array)-1]
            self.setDriver('FREQ', lastOctet, True, True, None, self.ipAddress)

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
                self.setDriver('ST', round((instantGridPowerW-abs(feedthroughPowerW)),2), True, True)

                allBranchesData_tuple = self.allBreakersData.partition(chr(34) + "branches" + chr(34) + ":")
                allBranchesData = allBranchesData_tuple[2]
                LOGGER.debug("\n\tINIT Panel Breaker Controller's Branches Data: \n\t\t" + allBranchesData + "\n\t\tCount of OPEN Breakers: " + str(allBranchesData.count(chr(34) + 'OPEN' + chr(34) + ',')) + "\n\t\tCount of CLOSED Breakers: " + str(allBranchesData.count(chr(34) + 'CLOSED' + chr(34) + ',')) + "\n")
                self.setDriver('PULSCNT', allBranchesData.count(chr(34) + 'CLOSED' + chr(34) + ','), True, True)
                self.setDriver('GV0', allBranchesData.count(chr(34) + 'OPEN' + chr(34) + ','), True, True)
        
                self.createBreakers()
            else:
                LOGGER.warning("\n\tINIT Issue getting first-time Breakers Data for Panel Breaker Controller '" + self.address + "' @ " + self.ipAddress + ".\n")

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
    
    # overload the setDriver() of the parent class to short circuit if 
    # node not initialized
    def setDriver(self, driver: str, value: Any, report: bool=True, force: bool=False, uom: Optional[int]=None, text: Optional[str]=None):
        if self._initialized:
            super().setDriver(driver, value, report, force, uom, text)

    '''
    Read the user entered custom parameters.
    def parameterHandler(self, params):
        self.Parameters.load(params)
    '''

    '''
    Handling for <text /> attribute across PG3 and PG3x.
    Note that to be reported to IoX, the value has to change; this is why we flip from 0 to 1 or 1 to 0.
    -1 is reserved for initializing.
    '''
    def pushTextToDriver(self,driver,stringToPublish):
        if len(str(self.getDriver(driver))) <= 0:
            LOGGER.warning("\n\tPUSHING REPORT ERROR - a (correct) Driver was not passed.\n")
            return
        else:
            LOGGER.debug("\n\tLEN of self.getDriver('" + driver + "') is greater than 0; driver value = " + str(self.getDriver(driver)) + "\n")
            
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
            LOGGER.debug("\n\tPUSHING REPORT TO '" + self.address + "'-owned status variable / driver '" + driver + "' with PG3x via self.poly.send('" + encodedStringToPublish + "','status') with a value of '" + str(newValue) + "'.\n")
            self.poly.send(message, 'status')
        elif not(self.parent.ISY.unauthorized):
            userpassword = self.parent.ISY._isy_user + ":" + self.parent.ISY._isy_pass
            userpasswordAsBytes = userpassword.encode("ascii")
            userpasswordAsBase64Bytes = base64.b64encode(userpasswordAsBytes)
            userpasswordAsBase64String = userpasswordAsBase64Bytes.decode("ascii")
    
            localConnection = http.client.HTTPConnection(self.parent.ISY._isy_ip, self.parent.ISY._isy_port)
            payload = ''
            headers = {
                "Authorization": "Basic " + userpasswordAsBase64String
            }
            
            LOGGER.debug("n\tPUSHING REPORT TO '" + self.address + "'-owned status variable / driver '" + driver + "' with PG3 via " + self.parent.ISY._isy_ip + ":" + str(self.parent.ISY._isy_port) + ", with a value of " + str(newValue) + ", and a text attribute (encoded) of '" + encodedStringToPublish + "'.\n")
    
            prefixN = str(self.poly.profileNum)
            if len(prefixN) < 2:
                prefixN = 'n00' + prefixN + '_'
            elif len(prefixN) < 3:
                prefixN = 'n0' + prefixN + '_'
            
            suffixURL = '/rest/ns/' + str(self.poly.profileNum) + '/nodes/' + prefixN + self.address + '/report/status/GPV/' + str(newValue) + '/56/text/' + encodedStringToPublish
    
            localConnection.request("GET", suffixURL, payload, headers)
            localResponse = localConnection.getresponse()
            localResponseData = localResponse.read()
            localResponseData = localResponseData.decode("utf-8")
            
            if '<status>200</status>' not in localResponseData:
                LOGGER.warning("\n\t\tPUSHING REPORT ERROR - RESPONSE from report was not '<status>200</status>' as expected:\n\t\t\t" + localResponseData + "\n")
        else:
            LOGGER.warning("\n\t\PUSHING REPORT ERROR: looks like this is a PG3 install but the ISY authorization state seems to currently be 'Unauthorized': 'True'.\n")

    def updateNode(self, passedAllBreakersData):
        self.allBreakersData = passedAllBreakersData

    '''
    This is where the real work happens.  When we get a shortPoll, do some work. 
    '''
    def poll(self, polltype):
        if 'shortPoll' in polltype:
            tokenLastTen = self.token[-10:]
            LOGGER.debug("\n\tPOLL About to query Panel Breaker Controller '" + self.address + "' @ {}, using token ending in {}".format(self.ipAddress,tokenLastTen))

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
                self.setDriver('ST', round((instantGridPowerW-abs(feedthroughPowerW)),2), True, True)

                allBranchesData_tuple = self.allBreakersData.partition(chr(34) + "branches" + chr(34) + ":")
                allBranchesData = allBranchesData_tuple[2]
                LOGGER.debug("\n\tSHORT POLL Panel Breaker Controller's Branches Data: \n\t\t" + allBranchesData + "\n\t\tCount of OPEN Breakers: " + str(allBranchesData.count(chr(34) + 'OPEN' + chr(34) + ',')) + "\n\t\tCount of CLOSED Breakers: " + str(allBranchesData.count(chr(34) + 'CLOSED' + chr(34) + ',')) + "\n")
                self.setDriver('PULSCNT', allBranchesData.count(chr(34) + 'CLOSED' + chr(34) + ','), True, True)
                self.setDriver('GV0', allBranchesData.count(chr(34) + 'OPEN' + chr(34) + ','), True, True)
                
                if len(str(instantGridPowerW)) > 0:
                    nowEpoch = int(time.time())
                    nowDT = datetime.datetime.fromtimestamp(nowEpoch)
                    
                    self.setDriver('TIME', nowEpoch, True, True)
                    #nowDT.strftime("%m/%d/%Y %H:%M:%S")
                    self.setDriver('HR', int(nowDT.strftime("%H")), True, True)
                    self.setDriver('MOON', int(nowDT.strftime("%M")), True, True)
                    self.setDriver('TIMEREM', int(nowDT.strftime("%S")), True, True)

                nodes = self.poly.getNodes()
                currentPanelBreakerPrefix = "s" + self.address.replace('panelbreaker_','') + "_breaker_"
                LOGGER.debug("\n\tWill be looking for Breaker nodes with this as the prefix: '" + currentPanelBreakerPrefix + "'.\n")
                for i in range(1,33):
                    node = currentPanelBreakerPrefix + str(i)
                    LOGGER.debug("\n\tUpdating " + node + " (which should be a Breaker node under this Panel controller: " + self.address + ").\n")
                    try:
                        epoch = self.getDriver('TIME')
                        hour = self.getDriver('HR')
                        minute = self.getDriver('MOON')
                        second = self.getDriver('TIMEREM')
                        nodes[node].updateNode(self.allBreakersData, epoch, hour, minute, second)
                    except Exception as e:
                        LOGGER.debug("\n\t\tPOLL ERROR: Cannot seem to update node '" + node + "' needed in for-loop due to error:\n\t\t{}\n".format(e))
            else:
                tokenLastTen = self.token[-10:]
                LOGGER.warning("\n\tPOLL ERROR when querying Panel Breaker Controller '" + self.address + "' @ IP address {}, using token {}.\n".format(self.ipAddress,tokenLastTen))
            
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
            try:
                node = SPAN_breaker.BreakerNode(self.poly, self.address, address, title, current_IPaddress, current_BearerToken, i)
                self.poly.addNode(node)
                node.wait_for_node_done()
                
                LOGGER.debug('\n\tCreated a Breaker child node {} under Panel Breaker controller {}\n'.format(title, panelNumberPrefix))
            except Exception as e:
                LOGGER.warning('\n\tCHILD NODE CREATION ERROR: Failed to create Breaker child node {} under Panel Breaker controller {} due to error:\n\t\t{}\n'.format(title, panelNumberPrefix, e))

    '''
    This is how we update the allBreakersData variable
    '''
    def updateAllBreakersData(self):
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
        except Exception as e:
            LOGGER.warning("\n\tUPDATE ALLBREAKERSDATA ERROR: SPAN API GET request for Panel Circuits Controller '" + self.address + "' failed due to error:\n\t\t{}\n".format(e))
            self.allBreakersData = ''
            
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
            hour = int(nowDT.strftime("%H"))
            minute = int(nowDT.strftime("%M"))
            second = int(nowDT.strftime("%S"))
            totalPower = round((instantGridPowerW-abs(feedthroughPowerW)),2)
            
            try:
                nodes = self.poly.getNodes()
                sisterCircuitsController = self.address.replace('panelbreaker_','panelcircuit_')
                nodes[sisterCircuitsController].updateCircuitControllerStatusValuesFromPanelQueryInBreakerController(totalPower, epoch, hour, minute, second)
                LOGGER.debug("\n\tUPDATE ALLBREAKERSDATA successfully found its sisterCircuitsController '" + sisterCircuitsController + "', and tried to update its total power 'ST', as well as time-based, Status elements.\n")
            except Exception as e: 
                LOGGER.warning("\n\tUPDATE ALLBREAKERSDATA ERROR: Panel Breaker Controller '" + self.address + "' cannot seem to find its sisterCircuitsController '" + self.address.replace('panelcircuit_','panelbreaker_') + "' to update, due to error:\n\t\t{}\n".format(e))

    '''
    STOP Received
    '''
    def stop(self):
        LOGGER.debug("\n\tSTOP RECEIVED: Panel Breaker Controller handler '" + self.address + "'.\n")
        self.setDriver('ST', 0, True, True)
        self.setDriver('TIME', -1, True, True)
        self.setDriver('HR', -1, True, True)
        self.setDriver('MOON', -1, True, True)
        self.setDriver('TIMEREM', -1, True, True)

