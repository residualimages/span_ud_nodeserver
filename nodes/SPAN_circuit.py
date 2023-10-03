#!/usr/bin/env python3
"""
Polyglot v3 node server SPAN Smart Panels
Copyright (C) 2023 Matt Burke

MIT License
"""
import udi_interface
import sys

# Standard Library
from typing import Optional, Any, TYPE_CHECKING

import math,time,datetime,urllib.parse,http.client,base64

LOGGER = udi_interface.LOGGER
ISY = udi_interface.ISY

'''
This is our Circuit device node. 

Notes about API:
    Circuit Relay State - POST To ipAddres/circuits/circuitID:
            {"relayStateIn": {"relayState":STATE}}
            STATE options: 'UNKNOWN', 'OPEN', 'CLOSED'

    Circuit Priority State - POST To ipAddres/circuits/circuitID:
            {"priorityIn": {"priority": PRIORITY}}
            PRIORITY options: 'UNKNOWN', 'NON_ESSENTIAL', 'NICE_TO_HAVE', 'MUST_HAVE'
'''
class CircuitNode(udi_interface.Node):
    id = 'circuit'
    drivers = [
            {'driver': 'ST', 'value': 0, 'uom': 73},
            {'driver': 'PULSCNT', 'value': 0, 'uom': 56},
            {'driver': 'CLIEMD', 'value': 0, 'uom': 25},
            {'driver': 'AWAKE', 'value': 0, 'uom': 25},
            {'driver': 'TIME', 'value': 0, 'uom': 151},
            {'driver': 'HR', 'value': -1, 'uom': 56},
            {'driver': 'MOON', 'value': -1, 'uom': 56},
            {'driver': 'TIMEREM', 'value': -1, 'uom': 56},
            {'driver': 'GP0', 'value': 0, 'uom': 145},
            {'driver': 'GV1', 'value': '', 'uom': 56},
            {'driver': 'GV2', 'value': '', 'uom': 56},
            {'driver': 'GV3', 'value': '', 'uom': 56},
            {'driver': 'GV4', 'value': '', 'uom': 56},
            {'driver': 'GPV', 'value': -1, 'uom': 56}
            ]

    def __init__(self, polyglot, parent, address, name, spanIPAddress, bearerToken, spanCircuitID, spanCircuitIndex):
        super(CircuitNode, self).__init__(polyglot, parent, address, name)

        # set a flag to short circuit setDriver() until the node has been fully
        # setup in the Polyglot DB and the ISY (as indicated by START event)
        self._initialized: bool = False
        
        self.poly = polyglot
        self.n_queue = []
        self.parent = parent

        self.ISY = ISY(self.poly)

        LOGGER.debug("\n\tINIT Span Circuit's parent is '" + parent + "' when INIT'ing.\n")

        self.ipAddress = spanIPAddress
        self.token = bearerToken
        self.circuitIndex = spanCircuitIndex
        self.circuitID = spanCircuitID
        self.allCircuitsData = ''
        
        tokenLastTen = self.token[-10:]
        LOGGER.debug("\n\tINIT IP Address for circuit:" + self.ipAddress + "; Bearer Token (last 10 characters): " + tokenLastTen + "; Circuit ID: " + self.circuitID)

        LOGGER.debug("\n\t\tINIT About to call setDriver for '" + self.address + "' with a UOM of 145 and a value of '" + str(self.circuitIndex) + "' and a text attribute of '" + self.circuitID + "'.\n")
        self.setDriver('GPV', self.circuitIndex, True, True, 145, self.circuitID)
            
        # subscribe to the events we want
        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.STOP, self.stop, address)
        polyglot.subscribe(polyglot.ADDNODEDONE, self.node_queue)
        
        self.initialized = True
        
    '''
    node_queue() and wait_for_node_event() create a simple way to wait
    for a node to be created.  The nodeAdd() API call is asynchronous and
    will return before the node is fully created. Using this, we can wait
    until it is fully created before we try to use it.
    '''
    def node_queue(self, data):
        if self.address == data['address']:
            LOGGER.debug("\n\tWAIT FOR NODE CREATION: Fully Complete for Circuit " + self.address + "\n")
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
        elif not(self.ISY.unauthorized):
            userpassword = self.ISY._isy_user + ":" + self.ISY._isy_pass
            userpasswordAsBytes = userpassword.encode("ascii")
            userpasswordAsBase64Bytes = base64.b64encode(userpasswordAsBytes)
            userpasswordAsBase64String = userpasswordAsBase64Bytes.decode("ascii")
    
            localConnection = http.client.HTTPConnection(self.ISY._isy_ip, self.ISY._isy_port)
            payload = ''
            headers = {
                "Authorization": "Basic " + userpasswordAsBase64String
            }
            
            LOGGER.debug("n\tPUSHING REPORT TO '" + self.address + "'-owned status variable / driver '" + driver + "' with PG3 via " + self.ISY._isy_ip + ":" + str(self.ISY._isy_port) + ", with a value of " + str(newValue) + ", and a text attribute (encoded) of '" + encodedStringToPublish + "'.\n")
    
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
    
    '''
    This is where the real work happens.  When the parent controller gets a shortPoll, do some work with the passed data. 
    '''
    def updateNode(self, passedAllCircuitsData, epoch, hour, minute, second):
        self.allCircuitsData = passedAllCircuitsData

        if self.getDriver('TIMEREM') == -1:
            designatedCircuitData_tuple = self.allCircuitsData.partition(chr(34) + self.circuitID + chr(34) + ':')
            designatedCircuitData = designatedCircuitData_tuple[2]
            designatedCircuitData_tuple = designatedCircuitData.partition('},')
            designatedCircuitData = designatedCircuitData_tuple[0] + '}'
    
            LOGGER.debug("\n\tAbout to search for 'name' in:\n\t\t" + designatedCircuitData + "\n")

            if self.getDriver('GPV') == 0:
                LOGGER.debug("\n\tSetting GPV because it is currently ''.\n")
                LOGGER.debug("\n\t\tFIRST UPDATE About to call setDriver for '" + self.address + "' with a UOM of 145 and a value of '" + str(self.circuitIndex) + "' and a text attribute of '" + self.circuitID + "'.\n")
                self.setDriver('GPV', self.circuitIndex, True, True, 145, self.circuitID)
    
            if "name" in designatedCircuitData:
                designatedCircuitTabs_tuple = designatedCircuitData.partition(chr(34) + "tabs" + chr(34) + ":")
                designatedCircuitTabs = designatedCircuitTabs_tuple[2]
                designatedCircuitTabs_tuple = designatedCircuitTabs.partition("],")
                designatedCircuitTabs = designatedCircuitTabs_tuple[0]
              
                LOGGER.debug("\n\tINIT Designated Circuit Data: \n\t\t" + designatedCircuitData + "\n\t\tCount of Circuit Breakers In Circuit: " + str(designatedCircuitTabs.count(',')+1) + "\n")
                self.setDriver('PULSCNT', (designatedCircuitTabs.count(',')+1), True, True)
    
                designatedCircuitTabs = designatedCircuitTabs.replace('[','')
                designatedCircuitTabsArray = designatedCircuitTabs.split(',')
                designatedCircuitTabsCount = len(designatedCircuitTabsArray)
        
                for i in range(0,designatedCircuitTabsCount):
                    LOGGER.debug("\n\tIn Circuit " + self.circuitID + ", Tab # " + str(i) + " corresponds to breaker number:\n\t\t" + designatedCircuitTabsArray[i] + "\n")
                    try:
                        self.setDriver('GV' + str(i+1), designatedCircuitTabsArray[i], True, True)
                    except:
                        LOGGER.warning("\n\t\tERROR Setting Tab (Physical Breaker #" + str(i+1) + ") for " + self.circuitID + ".\n")
                
                self.setDriver('TIME', epoch, True, True)
                self.setDriver('HR', hour, True, True)
                self.setDriver('MOON', minute, True, True)
                self.setDriver('TIMEREM', second, True, True)
            else:
                LOGGER.warning("\n\tINIT Issue getting data for circuit '" + self.circuitID + "'.\n")
                self.setDriver('HR', -1, True, True)
                self.setDriver('MOON', -1, True, True)
                self.setDriver('TIMEREM', -1, True, True)
        
        self.poll('shortPoll')
        
    def poll(self, polltype):
        if 'shortPoll' in polltype:
            tokenLastTen = self.token[-10:]
            LOGGER.debug('\n\tPOLL About to parse {} Circuit node of {}, using token ending in {}'.format(self.circuitID,self.ipAddress,tokenLastTen))
            designatedCircuitData_tuple = self.allCircuitsData.partition(chr(34) + self.circuitID + chr(34) + ':')
            designatedCircuitData = designatedCircuitData_tuple[2]
            designatedCircuitData_tuple = designatedCircuitData.partition('},')
            designatedCircuitData = designatedCircuitData_tuple[0] + '}'
        
            LOGGER.debug("\n\tPOLL Circuit Data: \n\t\t" + designatedCircuitData + "\n")
        
            if "name" in designatedCircuitData:
                designatedCircuitStatus_tuple = designatedCircuitData.partition(chr(34) + "relayState" + chr(34) + ":")
                designatedCircuitStatus = designatedCircuitStatus_tuple[2]
                designatedCircuitStatus_tuple = designatedCircuitStatus.partition(',')
                designatedCircuitStatus = designatedCircuitStatus_tuple[0]

                designatedCircuitPriority_tuple = designatedCircuitData.partition(chr(34) + "priority" + chr(34) + ":")
                designatedCircuitPriority = designatedCircuitPriority_tuple[2]
                designatedCircuitPriority_tuple = designatedCircuitPriority.partition(',')
                designatedCircuitPriority = designatedCircuitPriority_tuple[0]                    

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
                    
                LOGGER.debug("\n\tPOLL about to evaluate Circuit Priority (" + designatedCircuitPriority + ") and set MODE appropriately.\n")
                if "MUST" in designatedCircuitPriority:
                  self.setDriver('AWAKE', 3, True, True)
                elif "NICE" in designatedCircuitPriority:
                  self.setDriver('AWAKE', 2, True, True)
                elif "NON_" in designatedCircuitPriority:
                  self.setDriver('AWAKE', 1, True, True)
                else:
                  self.setDriver('AWAKE', 0, True, True)
                
                LOGGER.debug("\n\tPOLL About to set ST to " + str(designatedCircuitInstantPowerW) + " for Circuit " + self.circuitID + ".\n")
                self.setDriver('ST', round(abs(designatedCircuitInstantPowerW),2), True, True)

            else:
                LOGGER.warning("\n\tPOLL Issue getting data for circuit '" + self.circuitID + "'.\n")
                self.setDriver('HR', -3, True, True)
                self.setDriver('MOON', -3, True, True)
                self.setDriver('TIMEREM', -3, True, True)

    def cmd_update_circuit_status(self,commandDetails):
        LOGGER.debug(f'\n\t{self.address} being set via cmd_update_circuit_status to commandDetails={commandDetails}\n')
        
        #{"relayStateIn": {"relayState":STATE}}
        spanConnection = http.client.HTTPConnection(self.ipAddress)
        payload = "{"+ chr(34) + "relayStateIn" + chr(34) + ":{" + chr(34) + "relayState" + chr(34) + ":" + chr(34) + "STATE" + chr(34) + "}}"
        headers = {
            "Authorization": "Bearer " + self.token
        }
        
        value = commandDetails.get('value')
        
        if '2' in value:
            payload = payload.replace('STATE','CLOSED')
        elif '1' in value:
            payload = payload.replace('STATE','OPEN')
        else:
            LOGGER.error("\n\tCOMMAND was expected to set circuit status, but the value is not 1 or 2; it is: '" + format(value) + "' from:\n\t\t" + format(commandDetails) + "\n")
            return
     
        LOGGER.warning("\n\tCOMMAND About to POST a Circuit Status update of '" + payload + "' to " + self.ipAddress + "/api/v1/circuits/" + self.circuitID + "\n")
        spanConnection.request("POST", "/api/v1/circuits/" + self.circuitID, payload, headers)

        updateCircuitResponse = spanConnection.getresponse()
        updateCircuitData = updateCircuitResponse.read()
        updateCircuitData = updateCircuitData.decode("utf-8")

        LOGGER.debug("\n\tCOMMAND POST Update Circuit Status Data: \n\t\t" + format(updateCircuitData) + "\n")
        self.setDriver('CLIEMD', int(value), True, True)

    def cmd_update_circuit_priority(self,commandDetails):
        LOGGER.debug(f'\n\t{self.address} being set via cmd_update_circuit_priority to commandDetails={commandDetails}\n')
        
        #{"priorityIn": {"priority": PRIORITY}}
        spanConnection = http.client.HTTPConnection(self.ipAddress)
        payload = "{"+ chr(34) + "priorityIn" + chr(34) + ":{" + chr(34) + "priority" + chr(34) + ":" +chr(34) + "PRIORITY" + chr(34) + "}}"
        headers = {
            "Authorization": "Bearer " + self.token
        }

        value = commandDetails.get('value')

        if '3' in value:
            payload = payload.replace('PRIORITY','MUST_HAVE')
        elif '2' in value:
            payload = payload.replace('PRIORITY','NICE_TO_HAVE')
        elif '1' in value:
            payload = payload.replace('PRIORITY','NON_ESSENTIAL')
        else:
            LOGGER.error("\n\tCOMMAND was expected to set circuit priority, but the value is not 1, 2, or 3; it is: '" + format(value) + "' from:\n\t\t" + format(commandDetails) + "\n")
            return
    
        LOGGER.warning("\n\tCOMMAND About to POST a Circuit Status update of '" + payload + "' to " + self.ipAddress + "/api/v1/circuits/" + self.circuitID + "\n")
        spanConnection.request("POST", "/api/v1/circuits/" + self.circuitID, payload, headers)

        updateCircuitResponse = spanConnection.getresponse()
        updateCircuitData = updateCircuitResponse.read()
        updateCircuitData = updateCircuitData.decode("utf-8")

        LOGGER.debug("\n\tCOMMAND POST Update Circuit Priority Data: \n\t\t" + format(updateCircuitData) + "\n")
        self.setDriver('AWAKE', int(value), True, True)

    commands = {
        "UPDATE_CIRCUIT_STATUS": cmd_update_circuit_status,
        "UPDATE_CIRCUIT_PRIORITY": cmd_update_circuit_status,
    }

    '''
    Change self status driver to 0 W
    '''
    def stop(self):
        LOGGER.warning("\n\tSTOP COMMAND received: Circuit Node '" + self.address + "'.\n")
        self.setDriver('ST', 0, True, True)
        self.setDriver('TIME', -1, True, True)
        self.setDriver('HR', -1, True, True)
        self.setDriver('MOON', -1, True, True)
        self.setDriver('TIMEREM', -1, True, True)
