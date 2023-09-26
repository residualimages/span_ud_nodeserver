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
from nodes import SPAN_panel

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom

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
        self.count = 0
        self.n_queue = []

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
        self.Parameters.load(params)
        validIP_Addresses = False
        validAccess_Tokens = False

        if self.Parameters['IP_Addresses'] is not None:
            if len(self.Parameters['IP_Addresses']) > 6:
                validIP_Addresses = True
            else:
                LOGGER.error('Invalid values for IP_Addresses parameter.')
        else:
            LOGGER.error('Missing IP_Addresses parameter.')

        if self.Parameters['Access_Tokens'] is not None:
            if len(self.Parameters['Access_Tokens']) > 120:
                validAccess_Tokens = True
            else:
                LOGGER.error('Invalid values for Access_Tokens parameter.')
        else:
            LOGGER.error('Missing Access_Tokens parameter.')
        
        if validIP_Addresses and validAccess_Tokens:
            self.createChildren(self,self.Parameters['IP_Addresses'],self.Parameters['Access_Tokens'])
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
    Create the children nodes.  Since this will be called anytime the
    user changes the number of nodes and the new number may be less
    than the previous number, we need to make sure we create the right
    number of nodes.  Because this is just a simple example, we'll first
    delete any existing nodes then create the number requested.
    '''
    def createChildren(self,ipAddresses,accessTokens):
        # delete any existing nodes
        nodes = self.poly.getNodes()
        for node in nodes:
            if node != 'controller':   # but not the controller node
                self.poly.delNode(node)

        listOfIPAddresses = ipAddresses.split(";")
        how_many = len(listOfIPAddresses)

        listOfBearerTokens = accessTokens.split(";")

        LOGGER.info('Creating {} children nodes'.format(how_many))
        for i in range(0, how_many):
            current_IPaddress = listOfIPAddresses[i]
            current_BearerToken = listOfBearerTokens[i]
            address = 'SPAN_Panel_{}'.format(i)
            title = 'SPAN Panel {}'.format(current_IPAddress)
            try:
                node = SPAN_panel.PanelNode(self.poly, self.address, address, title, current_IPaddress, current_BearerToken)
                self.poly.addNode(node)
                self.wait_for_node_done()
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
                nodes[node].setDriver('ST', 0, True, True)

        self.poly.stop()


    '''
    Just to show how commands are implemented. The commands here need to
    match what is in the nodedef profile file. 
    '''
    def noop(self):
        LOGGER.info('Discover not implemented')

    commands = {'DISCOVER': noop}
