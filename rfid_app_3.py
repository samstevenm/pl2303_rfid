#!/usr/bin/env python
#
# File: rfid_app.py
# Version: 1.0
# Author: Damien Bobillot (damien.bobillot.2002+rfid_app@m4x.org)
# Licence: GNU GPL version 3
# Compatibility: tested with python 2.7 on Mac OS X, should work with any python installations.
#
# Driver for a chinese RFID 125Khz reader/writer for EM4100 tags
# by sending AADD0003010203 (hex) at speed 38400bds, device answers "ID card reader & writer"
# Windows application provided is named RFID-APP-E-E.exe
#
# may 2016 - 1.0 - First version
#

import time
import serial
import sys
from functools import reduce

LED_NONE  = "\x00"
LED_RED   = "\x01"
LED_GREEN = "\x02"
ERR_NONE  = "\x00"

# defining the core object
class rfid_app(serial.Serial):
    def __init__(self, dev_path, bauds=38400, debug=0):
        if dev_path.find("/") == -1: dev_path = "/dev/" + dev_path
        serial.Serial.__init__(self,dev_path,bauds,8,serial.PARITY_NONE,timeout=0)
        self._debug = debug
    
    @staticmethod
    def _checksum(s):
         # xor of all characters
        return chr( reduce(lambda r,c:r^ord(c), s, 0) )
    
    @staticmethod
    def _strtohex(s, sep=" "):
        return sep.join(["%02x"%(ord(c),) for c in s])
    
    @staticmethod
    def _hextostr(s):
        hex = ""
        tmp = None
        for c in s:
            # convert hex character to num value
            if c == ' ': continue
            elif '0' <= c and c <= '9': c = ord(c) - ord('0') 
            elif 'a' <= c and c <= 'f': c = ord(c) - ord('a') + 10
            elif 'A' <= c and c <= 'F': c = ord(c) - ord('A') + 10
            else: raise ValueError("not an hexadecimal character: %c" % c)
            
            # compute string
            if tmp == None:
                tmp = c
            else:
                hex = hex + chr((tmp<<4)|c)
                tmp = None
        if tmp != None: raise ValueError("even number of hexadecimal characters")
        return hex
    
    @staticmethod
    def _strtonum(s):
        return reduce(lambda r,c:(r<<8)|ord(c), s, 0)
    
    @staticmethod
    def _numtostr(n,l=5):
        d = ""
        for i in range(0,l):
            d = chr(n & 0xFF) + d
            n >>= 8
        return d
    
    def _execute_waitresult(self, opcode, data="", timeout=10, check_result=None):
        # execute
        # AA DD 00 ll o1 o2 d1 d2 d3 d4 cs
        assert(len(opcode) == 2 and len(data) <= 252)
        opcode_data = opcode + data
        cmd = "\xAA\xDD\x00" + chr(len(opcode_data)+1) + opcode_data + self._checksum(opcode_data)

        if self._debug: print("send %s" % (self._strtohex(cmd),), file=sys.stderr)
        self.write(cmd)
        time.sleep(0.1)
        
        # get result
        self.timeout=timeout
        result = self.read()
        self.timeout=0
        time.sleep(0.1)
        if result == "": raise IOError("operation timed out")
        result += self.read(1000)

        if self._debug: print("recv %s" % (self._strtohex(result),), file=sys.stderr)
        
        # parse result : status, data
        # AA DD 00 ll o1 o2 sc d1 d2 d3 d4 cs
        if len(result) < 4 or ord(result[3]) != len(result)-4:
            raise IOError("answer bad length: %s" % (self._strtohex(result),))
        if result[0:3] != "\xAA\xDD\x00" or result[4:6] != opcode:
            raise IOError("answer bad format: %s" % (self._strtohex(result),))
        if self._checksum(result[4:]) != "\x00":
            raise IOError("answer bad checksum: %s" % (self._strtohex(result),))
        
        status = result[6]
        if check_result and status != check_result:
            raise IOError("rfid command error #%d" % (ord(status),))
        
        data = result[7:-1]
        return status, data
    
    def get_info(self):
        return self._execute_waitresult("\x01\x02", check_result=ERR_NONE)[1]
        
    def beep(self, duration = 10):
        # duration must be between 1 and 255 (0 = forever !!!)
        self._execute_waitresult("\x01\x03", chr(duration), check_result=ERR_NONE)
    
    def set_led(self, code):
        self._execute_waitresult("\x01\x04", code, check_result=ERR_NONE)
    
    def read_token_raw(self):
        s, d = self._execute_waitresult("\x01\x0C")
        if s == ERR_NONE:   return d
        if s == "\x01":     return None
        raise IOError("rfid command error #%d" % (ord(s),))
    
    def read_token(self):
        d = self.read_token_raw()
        return self._strtonum(d) if d != None else None
    
    def write_token_raw(self, data, lock=False):
        lock = "\x01" if lock else "\x00"
        self._execute_waitresult("\x02\x0C", lock+data, check_result=ERR_NONE)
        if self.read_token_raw() == data:
            return
        self._execute_waitresult("\x03\x0C", lock+data, check_result=ERR_NONE)
        if self.read_token_raw() == data:
            return
        raise IOError("rfid write failed")

    def write_token(self, num):
        self.write_token_raw(self._numtostr(num))

if __name__ == "__main__":
    # parse arguments
    import argparse
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument ('-r', '--read', action="store_true", help="read token")
    group.add_argument ('-w', '--write', action="store_true", help="write token")
    group.add_argument ('-i', '--info', action="store_true", help="reader information")
    parser.add_argument('-d', '--device', required=True, help="path to serial communication device")
    parser.add_argument('-v', '--verbose', action="store_true", help="trace serial commands")
    parser.add_argument('-t', '--type', choices=["hex","dec"], default="hex", help="input/output type (hex, dec)")
    #parser.add_argument('-T', '--timeout', help="timeout of operations")
    parser.add_argument('data', nargs="?", help="(write only) data")
    args = parser.parse_args();
    
    if not args.write and args.data != None or args.write and args.data == None:
        parser.print_help()
        exit(1)
    
    dev = rfid_app(args.device, debug=1 if args.verbose else 0)
    
    if args.info:
        print(dev.get_info())
        
    elif args.read and args.type == "hex":
        d = dev.read_token_raw()
        if d == None:
            print("No card present")
        else:
            print(rfid_app._strtohex(d))
        
    elif args.read and args.type == "dec":
        d = dev.read_token()
        if d == None:
            print("No card present")
        else:
            print(d)
        
    elif args.write and args.type == "hex":
        dev.write_token_raw(rfid_app._hextostr(args.data))
        
    elif args.write and args.type == "dec":
        dev.write_token(int(args.data))
        
    else:
        parser.print_help()
        exit(1)
