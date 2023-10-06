# Integration for SPAN Smart Panels - Polyglot v3 NodeServer for Universal Devices Controllers
#             (c) 2023 Matt Burke

A simple node server that polls SPAN Smart Panels for circuit loads.
It also allows for turning on / off SPAN Circuits. 
(As SPAN and their app already warn you, relying on the software level 'off' for a Circuit before working on electric circuits is not officially appropriate.)
It may allow setting Priority on SPAN Circuits, but this is unverified.

This node server updates the values at every shortPoll() interval.

## Installation


### Node Settings
The settings for this node are:

#### Short Poll
   * How often to begin the SPAN circuit value query; Strongly suggest not any more frequently than 15 seconds, default is 30
#### Long Poll
   * Not used

#### IP Address(es)
   * ;-delimited list of IP address(es) of the SPAN Panel(s)

#### Access Token(s)
   * ;-delimited list of Access Token(s) for the corresponding SPAN Panel IP Address(es) 


## Requirements

1. Polyglot V3.
2. ISY firmware 5.6.4 or later (due to String-type Statuses in IoX)

# Release Notes

- 1.0.0 09/16/2023
   - Initial version copied from Example 3 Node Server (https://github.com/UniversalDevicesInc/udi-example3-poly)
