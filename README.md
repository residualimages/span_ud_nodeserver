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

## NodeServer Drivers / Status Types (for Variable Substitution etc)
    • Root NodeServer Controller ('SPAN Smart Panel NodeServer Controller'):
      º ST = If NodeServer is Active (boolean)
      º GV0 = Number of SPAN Panels being monitored by the NodeServer
      º GPV = Message from NodeServer - value will be between -1 (Initializing) and then flip between 0/1 (no meaning)
              The 'text' subattribute is what is shown in IoX (and why the required version of IoX is 5.6.4+)
      º RESET Command / Button = Delete And Reset All Panel, Circuit, and Breaker Nodes (WARNING: NO Confirmation)

    • SPAN Panel - CIRCUITS Controller
      º ST = Total Power Currently Being Used by Panel (Watts)
      º FREQ = IP Address of Panel
      º PULSCNT = Circuit Count
      º CLIEMD = Grid / Connection Status:
                  Right now, only "Panel on Grid" is defined; all others show as 'Unknown'. 
                  Visit the UDI forums to help the developer add others.
      º TIME = Last Successful Query
      º GPV = Message from NodeServer - value will be between -1 (Initializing) and then flip between 0/1 (no meaning)
              The 'text' subattribute is what is shown in IoX (and why the required version of IoX is 5.6.4+)

    • SPAN Panel - BREAKERS Controller
      º ST = Total Power Currently Being Used by Panel (Watts)
      º FREQ = IP Address of Panel
      º PULSCNT = Closed (Power FLOWING) Breaker Count
      º GV0 = Open / Tripped (Power INTERRUPTED) Breaker Count
      º TIME = Last Successful Query
      º GPV = Message from NodeServer - value will be between -1 (Initializing) and then flip between 0/1 (no meaning)
              The 'text' subattribute is what is shown in IoX (and why the required version of IoX is 5.6.4+)

    • SPAN Circuit
      º ST = Total Power Currently Being Used by Circuit (Watts)
      º PULSCNT = Number of Breakers in this SPAN Circuit:
                  (single = 1, duplex = 2, triplex = 3, quadplex = 4)
      º CLIEMD = Circuit Status:
                 Circuit Open (Power INTERRUPTED)
                 Circuit Closed (Power FLOWING)
                 Unknown
      º TIME = Last Successful Query
      º AWAKE = Circuit Priority as defined in SPAN:
                Non-Essential
                Nice to Have
                Must Have      
                Unknown
      º GV0 = Circuit ID in SPAN
      º GV1 = Physical Breaker #1 Location
      º GV2 = Physical Breaker #2 Location (for du, tri, or quad plex)
      º GV3 = Physical Breaker #3 Location (for tri or quad plex)
      º GV4 = Physical Breaker #4 Location (for quad plex)
      º GPV = Message from NodeServer - value will be between -1 (Initializing) and then flip between 0/1 (no meaning)
              The 'text' subattribute is what is shown in IoX (and why the required version of IoX is 5.6.4+)      
      
      UPDATE_CIRCUIT_STATUS Command / Button = Change Circuit Status
      UPDATE_CIRCUIT_PRIORITY Command / Button = Change Circuit Priority

    • SPAN Breaker
      º ST = Total Power Currently Being Used by Breaker (Watts)
      º PULSCNT = Physical Breaker Location
      º CLIEMD = Breaker Status:
                 Breaker Open / Tripped (Power INTERRUPTED)
                 Breaker Closed (Power FLOWING)      
                 Unknown
      º TIME = Last Successful Query
      º GPV = Message from NodeServer - value will be between -1 (Initializing) and then flip between 0/1 (no meaning)
              The 'text' subattribute is what is shown in IoX (and why the required version of IoX is 5.6.4+) 

# Release Notes
- 1.0.5 10/06/2023

  º Initial non-production store release candidate
  
- 1.0.0 09/16/2023

  º Initial version copied from Example 3 Node Server (https://github.com/UniversalDevicesInc/udi-example3-poly)

  º Assistance from Goose66 / iopool NodeServer
