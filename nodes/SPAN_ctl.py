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

import urllib.parse,http.client

from nodes import SPAN_panel

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
            {'driver': 'GPV', 'value': -1, 'uom': 56},
            ]

    def __init__(self, polyglot, parent, address, name):
        super(Controller, self).__init__(polyglot, parent, address, name)

        self.poly = polyglot
        self.n_queue = []

        #LOGGER.debug("\n\tController's parent is '" + parent + "' when INIT'ing.\n")

        self.Parameters = Custom(polyglot, 'customparams')

        self.ISY = ISY(self.poly)

        # subscribe to the events we want
        polyglot.subscribe(polyglot.CUSTOMPARAMS, self.parameterHandler)
        polyglot.subscribe(polyglot.STOP, self.stop)
        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.ADDNODEDONE, self.node_queue)
        polyglot.subscribe(polyglot.CUSTOMTYPEDPARAMS, self.manuallyAddedParametersHandler)
        polyglot.subscribe(polyglot.NSINFO, self.nsInfo)
        polyglot.subscribe(polyglot.POLL, self.poll)

        # start processing events and create add our controller node
        polyglot.ready()
        self.poly.addNode(self)

    def manuallyAddedParametersHandler(self, data):
        LOGGER.warning("\n\tHANDLE MANUALLY ADDED PARAMETERS.\n\t\t{}\n".format(data))

    def nsInfo(self, data):
        LOGGER.warning("\n\tHANDLE NSINFO.\n\t\t{}\n".format(data))
    
    def poll(self, polltype):
        if 'shortPoll' in polltype:
            nowDT = datetime.datetime.fromtimestamp(nowEpoch)
            self.pushTextToGPV(nowDT.strftime("%m/%d/%Y %H:%M:%S"))
    '''
    node_queue() and wait_for_node_event() create a simple way to wait
    for a node to be created.  The nodeAdd() API call is asynchronous and
    will return before the node is fully created. Using this, we can wait
    until it is fully created before we try to use it.
    '''
    def node_queue(self, data):
        self.n_queue.append(data['address'])
        LOGGER.warning("\n\tISY Object created under 'controller':\t" + self.ISY._isy_ip + ", which is itself NS #" + self.poly.profileNum + ".\n")

    def wait_for_node_done(self):
        self.pushTextToGPV('Waiting for root controller...')
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

        if self.Parameters['IP_Addresses'] is not None:
            if len(self.Parameters['IP_Addresses']) > 6:
                validIP_Addresses = True
            else:
                LOGGER.warning('\n\tCONFIGURATION INCOMPLETE OR INVALID: Invalid values for IP_Addresses parameter.')
        else:
            LOGGER.warning('\n\tCONFIGURATION MISSING: Missing IP_Addresses parameter.')

        if self.Parameters['Access_Tokens'] is not None:
            if len(self.Parameters['Access_Tokens']) > 120:
                validAccess_Tokens = True
            else:
                LOGGER.warning('\n\tCONFIGURATION INCOMPLETE OR INVALID: Invalid values for Access_Tokens parameter.')
        else:
            LOGGER.warning('\n\tCONFIGURATION MISSING: Missing Access_Tokens parameter.')
        
        if validIP_Addresses and validAccess_Tokens:
            self.createPanelControllers()
            self.poly.Notices.clear()
        else:
            if not(validIP_Addresses):
                self.poly.Notices['IP_Addresses'] = 'Please populate the IP_Addresses parameter.'
            if not(validAccess_Tokens):
                self.poly.Notices['Access_Tokens'] = 'Please populate the Access_Tokens parameter.'

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
        self.poly.updateProfile()
        
    '''
    Testing for <text /> attribute.
    Note that to be reported to IoX, the value has to change; this is why we flip from 0 to 1 or 1 to 0.
    -1 is reserved for initializing.
    '''
    def pushTextToGPV(self,stringToPublish):
        currentValue = int(self.getDriver('GPV'))
        encodedStringToPublish = urllib.parse.quote(stringToPublish, safe='')

        if currentValue != 0:
            message = {
                'set': [{
                    'address': self.address,
                    'driver': 'GPV',
                    'value': 0,
                    'uom': 56,
                    'text': encodedStringToPublish
                }]
            }
        else:
             message = {
                'set': [{
                    'address': self.address,
                    'driver': 'GPV',
                    'value': 1,
                    'uom': 56,
                    'text': encodedStringToPublish
                }]
            }    
        LOGGER.warning("\n\tPUSHING REPORT TO 'controller' status variable 'GPV' via self.poly.send('" + encodedStringToPublish + "','status').\n")
        
        self.poly.send(message, 'status')

        '''
        localConnection = http.client.HTTPConnection('127.0.0.1',8080)
        payload = ''
        LOGGER.warning("n\tPUSHING REPORT TO 'controller' status variable 'GPV' via 127.0.0.1:8080.\n")
            
        if currentValue != 0:
            suffixURL = '/rest/ns/25/nodes/n025_controller/report/status/GPV/0/56/text/' + encodedStringToPublish
        else:
            suffixURL = '/rest/ns/25/nodes/n025_controller/report/status/GPV/0/56/text/' + encodedStringToPublish

        localConnection.request("GET", suffixURL, payload)
        localResponse = localConnection.getresponse()
        localResponseData = localResponse.read()
        localResponseData = localResponseData.decode("utf-8")
        
        LOGGER.warning("\n\t\tRESPONSE from report:\n\t\t\t" + localResponseData + "\n")
        '''
    
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
            
            self.pushTextToGPV('Creating Circuit Controller ' + str(i))
            try:
                circuitController = SPAN_panel.PanelNodeForCircuits(self.poly, addressCircuits, addressCircuits, titleCircuits, current_IPaddress, current_BearerToken)
                self.poly.addNode(circuitController)
                circuitController.wait_for_node_done()
            except Exception as e:
                LOGGER.warning('Failed to create Panel Circuits Controller {}: {}'.format(titleCircuits, e))

            self.pushTextToGPV('Creating Panel Controller ' + str(i))
            try:
                LOGGER.debug("\n\t\ADD breakerController = SPAN_panel.PanelNodeForBreakers(self.poly, " + addressBreakers + ", " + addressBreakers + ", " + titleBreakers + ", " + current_IPaddress + ", " + current_BearerToken + ")\n")
                breakerController = SPAN_panel.PanelNodeForBreakers(self.poly, addressBreakers, addressBreakers, titleBreakers, current_IPaddress, current_BearerToken)
                self.poly.addNode(breakerController)
                breakerController.wait_for_node_done()
            except Exception as e:
                LOGGER.warning('Failed to create Panel Breakers Controller {}: {}'.format(titleBreakers, e))
        
        self.setDriver('GV0', how_many, True, True)
        self.pushTextToGPV('Querying ACTIVE')

    '''
    STOP Command Received
    '''
    def stop(self):
        LOGGER.warning("\n\tSTOP COMMAND Received by '" + self.address + "'.\n")
        self.setDriver('ST', 0, True, True)
        self.pushTextToGPV('Querying INACTIVE')
        self.poly.stop()
        
    '''
    Delete and Reset Nodes:
    '''
    def reset(self, comamndDetails):
        LOGGER.warning('\n\t\tRESET COMMAND ISSUED: Will Delete and Recreate All Sub-Nodes.\n')
        self.pushTextToGPV('Resetting...')
        self.n_queue = []
        self.poly.stop()
        
        # delete any existing nodes
        nodes = self.poly.getNodes()
        for node in nodes:
            if node != 'controller' and 'panel' not in node:   # but not the controller nodes at first
                LOGGER.warning("\n\tRESET NodeServer - deleting '" + node + "'.\n")
                self.poly.delNode(node)

        nodes = self.poly.getNodes()
        for node in nodes:
            if node != 'controller':   # but not the NS controller node itself
                LOGGER.warning("\n\tRESET NodeServer - deleting '" + node + "'.\n")
                self.poly.delNode(node)
                
        self.setDriver('GV0', 0, True, True)
        self.pushTextToGPV('Starting...')
        polyglot.ready()
        self.poly.addNode(self)

    commands = {'RESET': reset}
