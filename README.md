# Integration for SPAN Smart Panels - Polyglot v3 NodeServer for Universal Devices Controllers
#             (c) 2023 Matt Burke
# Copied from Example 3 Node Server (c) 2021 Robert Paauwe

A simple node server that polls SPAN Smart Panels for circuit loads.  
This node server simply updates the values at every poll() interval.

## Installation


### Node Settings
The settings for this node are:

#### Short Poll
   * How often to begin the SPAN circuit value query
#### Long Poll
   * Not used

#### IP Address(es)
   * ;-delimited list of IP address(es) of the SPAN Panel(s)

#### Access Token(s)
   * ;-delimited list of Access Token(s) for the corresponding SPAN Panel IP Address(es) 


## Requirements

1. Polyglot V3.
2. ISY firmware 5.6.4 or later (due to String and Unix timestamp type UOMs)

# Release Notes

- 1.0.0 09/16/2023
   - Initial version copied from Example 3 Node Server (https://github.com/UniversalDevicesInc/udi-example3-poly)
