#!/usr/bin/env python3
"""
Polyglot v3 node server SPAN Smart Panels
Copyright (C) 2023 Matt Burke

MIT License
"""
import udi_interface
import sys
import time
import string
import re

# Standard Library
from typing import Optional, Any, TYPE_CHECKING

import math,datetime,urllib.parse,http.client,base64

LOGGER = udi_interface.LOGGER
ISY = udi_interface.ISY

'''
This is our Breaker device node. 
'''
class BreakerNode(udi_interface.Node):
    id = 'breaker'
    drivers = [
            {'driver': 'ST', 'value': -1, 'uom': 73},
            {'driver': 'PULSCNT', 'value': -1, 'uom': 56},
            {'driver': 'CLIEMD', 'value': -1, 'uom': 25},
            {'driver': 'TIME', 'value': -1, 'uom': 56},
            {'driver': 'GPV', 'value': -1, 'uom': 56}
            ]

    def __init__(self, polyglot, parent, address, name, spanIPAddress, bearerToken, spanBreakerID):
        super(BreakerNode, self).__init__(polyglot, parent, address, name)

        # set a flag to short circuit setDriver() until the node has been fully
        # setup in the Polyglot DB and the ISY (as indicated by START event)
        self._initialized: bool = False
        
        self._fullyCreated: bool = False
        
        self.poly = polyglot
        self.n_queue = []
        self.parent = parent
        
        self.ISY = ISY(self.poly)

        LOGGER.debug("\n\tINIT Span Breaker's parent is '" + parent + "' when INIT'ing.\n")

        self.ipAddress = spanIPAddress
        self.token = bearerToken
        self.breakerID = spanBreakerID
        self.allBreakersData = ''
        
        tokenLastTen = self.token[-10:]
        LOGGER.debug("\n\tINIT IP Address for breaker:" + self.ipAddress + "; Bearer Token (last 10 characters): " + tokenLastTen + "; Breaker ID: " + str(self.breakerID))

        self.setDriver('PULSCNT', self.breakerID, True, True)
            
        # subscribe to the events we want
        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.STOP, self.stop, address)
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
            LOGGER.debug("\n\tWAIT FOR NODE CREATION: Fully Complete for Breaker " + self.address + "\n")
            nowEpoch = int(time.time())
            nowDT = datetime.datetime.fromtimestamp(nowEpoch)
            
            self.setDriver('ST', -1, True, True)
            self.setDriver('PULSCNT', -1, True, True)
            self.setDriver('CLIEMD', -1, True, True)
            self.setDriver('TIME', -1, True, True)

            self.setDriver('GPV', -1, True, True)
            
            self.pushTextToDriver('TIME',nowDT.strftime("%m/%d/%Y %I:%M:%S %p"))

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
        self.setDriver('ST', -1, True, True)
        self.setDriver('PULSCNT', -1, True, True)
        self.setDriver('CLIEMD', -1, True, True)
        self.setDriver('TIME', -1, True, True)
        
    # overload the setDriver() of the parent class to short circuit if 
    # node not initialized
    def setDriver(self, driver: str, value: Any, report: bool=True, force: bool=False, uom: Optional[int]=None, text: Optional[str]=None):
        if self._initialized and self._fullyCreated:
            super().setDriver(driver, value, report, force, uom, text)

    def delete(self, address):
        if address == self.address:
            LOGGER.warning("\n\tDELETE COMMAND RECEIVED for self ('" + self.address + "')\n")
        else:
            LOGGER.debug("\n\tDELETE COMMAND RECEIVED for '" + address + "'\n")
        
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
            
        else:
            newValue = 0

        self.setDriver(driver, newValue, False)

        if 'isPG3x' in self.poly.pg3init and self.poly.pg3init['isPG3x'] is True:
            #PG3x can use this, but PG3 doesn't have the necessary 'text' handling within message, set above, so we have the 'else' below
            message = {
                'set': [{
                    'address': self.address,
                    'driver': driver,
                    'value': newValue,
                    'uom': 56,
                    'text': stringToPublish
                }]
            }
            LOGGER.debug("\n\tPUSHING REPORT TO '" + self.address + "' for driver " + driver + ", with PG3x via self.poly.send('" + stringToPublish + "','status') with a value of '" + str(newValue) + "'.\n")
            self.poly.send(message, 'status')
        elif not(self.ISY.unauthorized):
            message = {
                'set': [{
                    'address': self.address,
                    'driver': driver,
                    'value': newValue,
                    'uom': 56,
                    'text': encodedStringToPublish
                }]
            }

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
                
                LOGGER.debug("n\tPUSHING REPORT TO '" + self.address + "' for driver " + driver + ", with PG3 via " + self.ISY._isy_ip + ":" + str(self.ISY._isy_port) + ", with a value of " + str(newValue) + ", and a text attribute (encoded) of '" + encodedStringToPublish + "'.\n")
        
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
                except http.client.HTTPException:
                    LOGGER.error("\n\t\tPUSHING REPORT ERROR on '" + self.address + "' for driver " + driver + " had an error.\n")
                except:
                    LOGGER.error("\n\t\tPUSHING REPORT ERROR on '" + self.address + "' for driver " + driver + " had an error.\n")
                finally:
                    localConnection.close()  
        else:
            LOGGER.warning("\n\t\PUSHING REPORT ERROR on '" + self.address + "' for driver " + driver + ": looks like this is a PG3 install but the ISY authorization state seems to currently be 'Unauthorized': 'True'.\n")

    '''
    This is where the real work happens.  When the parent controller gets a shortPoll, do some work with the passed data. 
    '''
    def updateBreakerNode(self, passedAllBreakersData, dateTimeString):
        self.allBreakersData = passedAllBreakersData

        if int(self.getDriver('PULSCNT')) <= 0:
            LOGGER.debug("\n\tFor updateNode under '" + self.address + "', setting Breaker ID (PULSCNT) because it is currently 0.\n")
            self.setDriver('PULSCNT', self.breakerID, True, True)
        
        self.poll('shortPoll')

        if "-1" in str(self.getDriver('GPV')):
            self.pushTextToDriver('GPV','NodeServer RUNNING')
        
        if "instantPowerW" in self.allBreakersData:
            self.pushTextToDriver('TIME', dateTimeString)
        
    def poll(self, polltype):
        if 'shortPoll' in polltype:
            tokenLastTen = self.token[-10:]
            LOGGER.debug('\n\tPOLL About to parse {} Breaker node of {}, using token ending in {}'.format(self.breakerID,self.ipAddress,tokenLastTen))
            designatedBreakerData_tuple = self.allBreakersData.partition(chr(34) + 'id' + chr(34) + ':' + str(self.breakerID) + ',')
            designatedBreakerData = designatedBreakerData_tuple[2]
            designatedBreakerData_tuple = designatedBreakerData.partition('},')
            designatedBreakerData = designatedBreakerData_tuple[0] + '}'
        
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
                self.setDriver('ST', round(abs(designatedBreakerInstantPowerW),2), True, True)

            else:
                LOGGER.warning("\n\tPOLL ERROR: Unable to get designatedBreakerInstantPowerW from designatedBreakerData:\n\t\t" + designatedBreakerData + "\n")
                self.setDriver('TIME', -1, True, True)
                self.pushTextToDriver('GPV',"POLL ERROR DESIGNATEDBREAKER")
                
    '''
    Change reported power draw 'ST' driver to 0 W
    '''
    def stop(self):
        LOGGER.warning("\n\tSTOP COMMAND received: Breaker Node '" + self.address + "'.\n")
        self.setDriver('ST', -1, True, True)
        self.setDriver('PULSCNT', -1, True, True)
        self.setDriver('CLIEMD', -1, True, True)
        self.setDriver('TIME', -1, True, True)
        self.pushTextToDriver('GPV',"NodeServer STOPPED")
        self.setDriver('GPV', -1, True, True)
