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

import urllib.parse,http.client,math,time,datetime,base64

from nodes import SPAN_breakerController,SPAN_circuitController

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom
ISY = udi_interface.ISY

### Note for setDriver from BobP:
### setDriver(driver, value, report=true, forceReport=false, uom=None, text=None)

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
Controller is interfacing with both Polyglot and the device.
'''
class Controller(udi_interface.Node):
    id = 'ctl'
    drivers = [
            {'driver': 'ST', 'value': 1, 'uom': 2},
            {'driver': 'GV0', 'value': 0, 'uom': 56},
            {'driver': 'GPV', 'value': -1, 'uom': 56, 'text': 'NodeServer STARTING'}
            ]

    def __init__(self, polyglot, parent, address, name):
        super(Controller, self).__init__(polyglot, parent, address, name)

        self.poly = polyglot
        self.n_queue = []
        
        self.pg3ParameterErrors = True

        #LOGGER.debug("\n\tController's parent is '" + parent + "' when INIT'ing.\n")

        self.Parameters = Custom(polyglot, 'customparams')

        self.ISY = ISY(self.poly)
        self.parent = parent

        # subscribe to the events we want
        polyglot.subscribe(polyglot.CUSTOMPARAMS, self.parameterHandler)
        polyglot.subscribe(polyglot.STOP, self.stop)
        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.ADDNODEDONE, self.node_queue)
        polyglot.subscribe(polyglot.CUSTOMTYPEDPARAMS, self.manuallyAddedParametersHandler)
        #polyglot.subscribe(polyglot.NSINFO, self.nsInfo)
        polyglot.subscribe(polyglot.POLL, self.poll)

        # start processing events and add our controller node
        polyglot.ready()
        self.poly.addNode(self)

    def manuallyAddedParametersHandler(self, data):
        LOGGER.debug("\n\tHANDLE MANUALLY ADDED PARAMETERS.\n\t\t{}\n".format(data))

    #def nsInfo(self, data):
        #LOGGER.debug("\n\tHANDLE NSINFO.\n\t\t{}\n".format(data))
    
    def poll(self, polltype):
        if 'shortPoll' in polltype and not(self.pg3ParameterErrors):
            nowEpoch = int(time.time())
            nowDT = datetime.datetime.fromtimestamp(nowEpoch)
            nodes = self.poly.getNodes()
            how_many = 0
            for node in nodes.copy():
                if 'panelbreaker_' in node:   # count number of Breaker Controller nodes; 'GV0' should have been set at createPanelControllers but it seems to lose track of itself.
                    how_many += 1
                    nodes[node].pollBreakerController(polltype + "|poll passed from root controller")
                    self.pushTextToDriver('GPV',"Last Short Poll Date / Time: " + nowDT.strftime("%m/%d/%Y %H:%M:%S"))

                    '''
                    try:
                        nodes[node].pollBreakerController(polltype + "|poll passed from root controller")
                        self.pushTextToDriver('GPV',"Last Short Poll Date / Time: " + nowDT.strftime("%m/%d/%Y %H:%M:%S"))
                    except:
                        LOGGER.debug("\n\tPOLL ERROR in Node Server root controller ('" + self.address + "'): Cannot seem to kick off shortPoll in controller node '" + node + "' as necessary, due to error.\n"))
                        self.pushTextToDriver('GPV',"POLL ERROR for '" + node + "'")
                    '''
            
            self.setDriver('GV0', how_many, True, True)

        elif self.pg3ParameterErrors:
            self.pushTextToDriver('GPV',"Please correct the NodeServer parameters in PG3(x)")
            
    '''
    node_queue() and wait_for_node_event() create a simple way to wait
    for a node to be created.  The nodeAdd() API call is asynchronous and
    will return before the node is fully created. Using this, we can wait
    until it is fully created before we try to use it.
    '''
    def node_queue(self, data):
        self.n_queue.append(data['address'])
        if data['address'] == self.address:
            LOGGER.debug("\n\tISY Object created under 'controller':\t" + self.ISY._isy_ip + ":" + str(self.ISY._isy_port) + ", which is itself NS #" + str(self.poly.profileNum) + ", and has self.address of '" + str(self.address) + "'.\n")   
            LOGGER.debug("\n\t\tUNAuthorized (expecting this to be false): " + str(self.ISY.unauthorized) + ".\n")

    def wait_for_node_done(self):
        while len(self.n_queue) == 0:
            time.sleep(0.1)
        self.n_queue.pop()

    '''
    Read the user entered custom parameters.  Here is where the user will
    configure IP_Addresses and Access_Tokens for SPAN Panels.
    '''
    def parameterHandler(self, params):
        self.poly.Notices.clear()
        
        self.Parameters.load(params)
        validIP_Addresses = False
        validAccess_Tokens = False
        ioxErrorMessage = ''

        if self.Parameters['IP_Addresses'] is not None:
            if len(self.Parameters['IP_Addresses']) > 6:
                validIP_Addresses = True
            else:
                LOGGER.warning('\n\tCONFIGURATION INCOMPLETE OR INVALID: Invalid values for IP_Addresses parameter.')
                ioxErrorMessage = 'INVALID IP_Addresses Parameter'
        else:
            LOGGER.warning('\n\tCONFIGURATION MISSING: Missing IP_Addresses parameter.')
            ioxErrorMessage = 'MISSING IP_Addresses Parameter'

        if self.Parameters['Access_Tokens'] is not None:
            if len(self.Parameters['Access_Tokens']) > 120:
                validAccess_Tokens = True
            else:
                LOGGER.warning('\n\tCONFIGURATION INCOMPLETE OR INVALID: Invalid values for Access_Tokens parameter.')
                if len(ioxErrorMessage) > 0:
                    ioxErroMessage = ioxErrorMessage + '; '
                ioxErrorMessage = ioxErrorMessage + 'INVALID Access_Tokens Parameter'
        else:
            LOGGER.warning('\n\tCONFIGURATION MISSING: Missing Access_Tokens parameter.')
            if len(ioxErrorMessage) > 0:
                ioxErroMessage = ioxErrorMessage + '; '
            ioxErrorMessage = ioxErrorMessage + 'MISSING Access_Tokens Parameter'

        
        if validIP_Addresses and validAccess_Tokens:
            self.createPanelControllers()
            self.poly.Notices.clear()
            self.pg3ParameterErrors = False
        else:
            if not(validIP_Addresses):
                self.poly.Notices['IP_Addresses'] = 'Please populate the IP_Addresses parameter.'
            if not(validAccess_Tokens):
                self.poly.Notices['Access_Tokens'] = 'Please populate the Access_Tokens parameter.'
            
            self.pushTextToDriver('GPV',ioxErrorMessage)

    '''
    This is called when the node is added to the interface module. It is
    run in a separate thread.  This is only run once so you should do any
    setup that needs to be run initially.  For example, if you need to
    start a thread to monitor device status, do it here.

    Here we load the custom parameter configuration document and push
    the profiles to the ISY.
    '''
    def start(self):
        self.poly.setCustomParamsDoc()
        # Not necessary to call this since profile_version is used from server.json
        # self.poly.updateProfile()
        
        if self.pg3ParameterErrors:
            self.pushTextToDriver('GPV',"Please correct the NodeServer parameters in PG3(x)")
        
    '''
    Handling for <text /> attribute.
    Note that to be reported to IoX, the value has to change; this is why we flip from 0 to 1 or 1 to 0.
    -1 is reserved for initializing.
    '''
    def pushTextToDriver(self,driver,stringToPublish):
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

            if len(self.ISY._isy_ip) > 0 and len(userpasswordAsBase64String) > 3:
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
                
                LOGGER.debug("\n\t\tPUSHING REPORT Details - this is the 'suffixURL':\n\t\t\t" + suffixURL + "\n")
        
                localConnection.request("GET", suffixURL, payload, headers)
                localResponse = localConnection.getresponse()
                localResponseData = localResponse.read()
                localResponseData = localResponseData.decode("utf-8")
                
                if '<status>200</status>' not in localResponseData:
                    LOGGER.warning("\n\t\tPUSHING REPORT ERROR on '" + self.address + "' for driver " + driver + ": RESPONSE from report was not '<status>200</status>' as expected:\n\t\t\t" + localResponseData + "\n")
                else:
                    LOGGER.debug("\n\t\tPUSHING REPORT on '" + self.address + "' for driver " + driver + ": RESPONSE from report:\n\t\t\t" + localResponseData + "\n")
        else:
            LOGGER.warning("\n\t\PUSHING REPORT ERROR on '" + self.address + "' for driver " + driver + ": looks like this is a PG3 install but the ISY authorization state seems to currently be 'Unauthorized': 'True'.\n")
    
    '''
    Create the controller nodes. 
    '''
    def createPanelControllers(self):
        
        ipAddresses = self.Parameters['IP_Addresses']
        accessTokens = self.Parameters['Access_Tokens']

        listOfIPAddresses = ipAddresses.split(";")
        listOfBearerTokens = accessTokens.split(";")
        how_many = len(listOfIPAddresses)

        LOGGER.debug('\n\tCreating {} Panel nodes (which will be controllers for Circuit nodes)'.format(how_many))
        for i in range(0, how_many):
            self.pg3ParameterErrors = False
            
            current_IPaddress = listOfIPAddresses[i]
            current_BearerToken = listOfBearerTokens[i]
            
            addressCircuits = 'PanelCircuit_{}'.format(i+1)
            addressCircuits = getValidNodeAddress(addressCircuits)
            titleCircuits = 'SPAN Panel #{} - Circuits'.format(i+1)
            titleCircuits = getValidNodeName(titleCircuits)
            
            addressBreakers = 'PanelBreaker_{}'.format(i+1)
            addressBreakers = getValidNodeAddress(addressBreakers)
            titleBreakers = 'SPAN Panel #{} - Breakers'.format(i+1)
            titleBreakers = getValidNodeName(titleBreakers)
            
            self.pushTextToDriver('GPV','Traversing circuits in Circuit Controller #' + str(i+1))
            try:
                LOGGER.debug("\n\t\ADD circuitController = SPAN_circuitController.PanelNodeForCircuits(self.poly, " + addressCircuits + ", " + addressCircuits + ", " + titleCircuits + ", " + current_IPaddress + ", " + current_BearerToken + ")\n")
                panelCircuitController = SPAN_circuitController.PanelNodeForCircuits(self.poly, addressCircuits, addressCircuits, titleCircuits, current_IPaddress, current_BearerToken)
                self.poly.addNode(panelCircuitController)
                panelCircuitController.wait_for_node_done()
                
                self.pushTextToDriver('GPV','Traversing breakers in Breaker Controller #' + str(i+1))
                try:
                    LOGGER.debug("\n\t\ADD breakerController = SPAN_breakerController.PanelNodeForBreakers(self.poly, " + addressBreakers + ", " + addressBreakers + ", " + titleBreakers + ", " + current_IPaddress + ", " + current_BearerToken + ")\n")
                    panelBreakerController = SPAN_breakerController.PanelNodeForBreakers(self.poly, addressBreakers, addressBreakers, titleBreakers, current_IPaddress, current_BearerToken, panelCircuitController)
                    self.poly.addNode(panelBreakerController)
                    panelBreakerController.wait_for_node_done()
                except:
                    LOGGER.warning('Failed to create Panel Breakers Controller {}: {}'.format(titleBreakers))
            except:
                LOGGER.warning('Failed to create Panel Circuits Controller {}: {}'.format(titleCircuits))
        
        self.setDriver('GV0', how_many, True, True)
        self.pushTextToDriver('GPV','NodeServer started; AWAITING first short poll')

    '''
    STOP Command Received
    '''
    def stop(self):
        LOGGER.warning("\n\tSTOP COMMAND Received by '" + self.address + "'.\n")
        self.setDriver('ST', 0, True, True)
        self.pushTextToDriver('GPV','NodeServer STOPPED')
        self.poly.stop()
        
    '''
    Delete and Reset Nodes:
    '''
    def reset(self, commandDetails):
        LOGGER.warning('\n\tRESET COMMAND ISSUED: Will Delete and Recreate All Sub-Nodes.\n\t\t{}'.format(commandDetails))
        self.pushTextToDriver('GPV','Resetting...')
        countOfNodes = 0
        # delete any existing nodes
        nodes = self.poly.getNodes()
        for node in nodes.copy():
            countOfNodes += 1
            if node != 'controller' and 'panel' not in node:   # but not the controller nodes at first
                LOGGER.warning("\n\tRESET NodeServer - deleting node '" + node + "'.\n")
                try:
                    self.poly.delNode(node)
                except:
                    LOGGER.warning('\n\tDELETING FAILED due to: {}\n'.format(e))
            else:
                LOGGER.debug("\n\tRESET NodeServer - SKIP deleting '" + node + "' for now.\n")
        
        LOGGER.warning('\n\t\tRESET FOUND {} nodes, including 1 for the root controller for this NodeServer.\n'.format(countOfNodes))

        if countOfNodes > 1:
            controllers = self.poly.getNodes()
            for controller in controllers.copy():
                if controller != 'controller':   # but not the NS controller node itself
                    LOGGER.warning("\n\tRESET NodeServer - deleting controller '" + controller + "'.\n")
                    try:
                        self.poly.delNode(controller)
                    except:
                        LOGGER.warning('\n\tDELETING FAILED due to: {}\n'.format(e))
                else:
                    LOGGER.debug("\n\tRESET NodeServer - SKIP deleting '" + controller + "'.\n")      
    
            # Iterate over polyglot's internal list of nodes to check for orphaned ones belonging to this NodeServer
            for controllerIndex in range(1,2):
                for entityIndex in range(1,33):
                    address = 's' + str(controllerIndex) + '_breaker_' + str(entityIndex)
                    if address in self.poly.nodes_internal:
                        del self.poly.nodes_internal[address]        
                        LOGGER.warning("\n\tFound an orphaned breaker node (#" + str(entityIndex) + ") under Breaker Controller #" + str(controllerIndex) + ".\n")
                    else:
                        LOGGER.debug("\n\tNo orphaned breaker node with address '{}' found.\n".format(address))
                        
                    address = 's' + str(controllerIndex) + '_circuit_' + str(entityIndex)
                    if address in self.poly.nodes_internal:
                        del self.poly.nodes_internal[address]        
                        LOGGER.warning("\n\tFound an orphaned circuit node (#" + str(entityIndex) + ") under Circuit Controller #" + str(controllerIndex) + ".\n")
                    else:
                        LOGGER.debug("\n\tNo orphaned circuit node with address '{}' found.\n".format(address))
    
                address = 'panelbreaker_' + str(controllerIndex)
                if address in self.poly.nodes_internal:
                    del self.poly.nodes_internal[address]        
                    LOGGER.warning("\n\tFound an orphaned Breaker Controller #" + str(controllerIndex) + "; removing.\n")
                else:
                    LOGGER.debug("\n\tNo orphaned Breaker Controller with address '{}' found.\n".format(address))
                    
                address = 'panelcircuit_' + str(controllerIndex)
                if address in self.poly.nodes_internal:
                    del self.poly.nodes_internal[address]        
                    LOGGER.warning("\n\tFound an orphaned Circuit Controller #" + str(controllerIndex) + "; removing.\n")        
                else:
                    LOGGER.debug("\n\tNo orphaned Circuit Controller with address '{}' found.\n".format(address))
                    
            self.setDriver('GV0', 0, True, True)
            self.pushTextToDriver('GPV','Will restart in 5 seconds...')
            #self.stop()
            time.sleep(5)
            
        self.pushTextToDriver('GPV','NodeServer RESTARTING...')
        self.start()

    commands = {'RESET': reset}
