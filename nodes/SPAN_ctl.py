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
from nodes import SPAN_panel

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
Controller is interfacing with both Polyglot and the device.
'''
class Controller(udi_interface.Node):
    id = 'ctl'
    drivers = [
            {'driver': 'ST', 'value': 1, 'uom': 2},
            {'driver': 'GV0', 'value': 0, 'uom': 56},
            ]

    def __init__(self, polyglot, parent, address, name):
        super(Controller, self).__init__(polyglot, parent, address, name)

        self.poly = polyglot
        self.n_queue = []

        LOGGER.debug("\n\tController's parent is '" + parent + "' when INIT'ing.\n")

        self.Parameters = Custom(polyglot, 'customparams')

        # subscribe to the events we want
        polyglot.subscribe(polyglot.CUSTOMPARAMS, self.parameterHandler)
        polyglot.subscribe(polyglot.STOP, self.stop)
        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.ADDNODEDONE, self.node_queue)

        # start processing events and create add our controller node
        polyglot.ready()
        self.poly.addNode(self)

    '''
    node_queue() and wait_for_node_event() create a simple way to wait
    for a node to be created.  The nodeAdd() API call is asynchronous and
    will return before the node is fully created. Using this, we can wait
    until it is fully created before we try to use it.
    '''
    def node_queue(self, data):
        self.n_queue.append(data['address'])

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

        if self.Parameters['IP_Addresses'] is not None:
            if len(self.Parameters['IP_Addresses']) > 6:
                validIP_Addresses = True
            else:
                LOGGER.error('\n\tCONFIGURATION INCOMPLETE OR INVALID: Invalid values for IP_Addresses parameter.')
        else:
            LOGGER.error('\n\tCONFIGURATION MISSING: Missing IP_Addresses parameter.')

        if self.Parameters['Access_Tokens'] is not None:
            if len(self.Parameters['Access_Tokens']) > 120:
                validAccess_Tokens = True
            else:
                LOGGER.error('\n\tCONFIGURATION INCOMPLETE OR INVALID: Invalid values for Access_Tokens parameter.')
        else:
            LOGGER.error('\n\tCONFIGURATION MISSING: Missing Access_Tokens parameter.')
        
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
    Create the controller nodes. 
    '''
    def createPanelControllers(self):
        
        # delete any existing nodes
        nodes = self.poly.getNodes()
        for node in nodes:
            if node != 'controller':   # but not the controller node
                LOGGER.debug("\n\tINIT Controller - deleting " + node + " when creating base NodeServer controller.\n")
                self.poly.delNode(node)

        ipAddresses = self.Parameters['IP_Addresses']
        accessTokens = self.Parameters['Access_Tokens']

        listOfIPAddresses = ipAddresses.split(";")
        listOfBearerTokens = accessTokens.split(";")
        how_many = len(listOfIPAddresses)

        LOGGER.info('\n\tCreating {} Panel nodes (which will be controllers for Circuit nodes)'.format(how_many))
        for i in range(0, how_many):
            current_IPaddress = listOfIPAddresses[i]
            current_BearerToken = listOfBearerTokens[i]
            address = 'Panel_{}'.format(i+1)
            address = getValidNodeAddress(address)
            title = 'SPAN Panel #{} - Circuits'.format(i+1)
            title = getValidNodeName(title)
            try:
                node = SPAN_panel.PanelNodeForCircuits(self.poly, address, address, title, current_IPaddress, current_BearerToken)
                self.poly.addNode(node)
                self.wait_for_node_done()
                node.setDriver('AWAKE', 1, True, True)
            except Exception as e:
                LOGGER.error('Failed to create {}: {}'.format(title, e))

        self.setDriver('GV0', how_many, True, True)

    '''
    Change all the child node active status drivers to false
    '''
    def stop(self):

        nodes = self.poly.getNodes()
        for node in nodes:
            if node != 'controller':   # but not the controller node
                nodes[node].setDriver('AWAKE', 0, True, True)

        self.poly.stop()


    '''
    Just to show how commands are implemented. The commands here need to
    match what is in the nodedef profile file. 
    '''
    def noop(self):
        LOGGER.info('\n\tNOTE: Discover not implemented')

    commands = {'DISCOVER': noop}
