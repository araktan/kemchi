SYRINGE_VOL = 25 # ml
MAX_STEPS = 24000 
DEFAULT_SPEED = 30 # ml min

DEFAULT_SPEED_HZ = int((DEFAULT_SPEED*MAX_STEPS)/(SYRINGE_VOL*60))
# DEFAUL_SPEED_SETTING_STEPS = 5000 # factory default
# DEFAULT_SPEED_START = 743 # factory default
# DEFAULT_SPEED_STOP = 743 # factory default
# DEFAULT_ACCELERATION_SLOPE
# DEFAULT_DECELARATION_SLOPE

OK_CODE = {b"'": 'No error, ready',
           b'@': 'No error, busy',
           b'`01100000 ': 'No error, ready',}

WARNING_CODE = {#b'a': 'Syringe not initialized, ready',
                b'b': 'Invalid command, ready',
                b'c': 'Invalid operand, ready',
                b'd': 'Communication error, ready',
                b'e': 'Invalid R command, ready',
                b'f': 'Low voltage, ready',
                b'g': 'Device not initialized, ready',
                b'h': 'Program in progress, ready',
                b'i': 'Syringe overload, ready',
                b'j': 'Valve overload, ready',
                b'k': 'Syringe move not allowed in valve bypass position, ready',
                b'l': 'No move against limit, ready',
                b'm': 'NVM Memory failure, ready',
                b'n': 'Reserved, ready',
                b'o': 'Command buffer full, ready',
                b'p': 'For 3-way valve only, ready',
                b'q': 'Loops nested too deep, ready',
                b'r': 'Label not found, ready',
                b's': 'No end of program, ready',
                b't': 'Out of program space, ready',
                b'u': 'Home limit not set, ready',
                b'v': 'Call stack overflow, ready',
                b'w': 'Program not present, ready',
                b'x': 'Valve position error, ready',
                b'y': 'Syringe position error, ready',
                #b'z': 'Syringe may crash, ready',
                #b'A': 'Syringe not initialized, busy',
                b'B': 'Invalid command, busy',
                b'C': 'Invalid operand, busy',
                b'D': 'Communication error, busy',
                b'E': 'Invalid R command, busy',
                b'F': 'Low voltage, busy',
                b'G': 'Device not initialized, busy',
                b'H': 'Program in progress, busy',
                b'I': 'Syringe overload, busy',
                b'J': 'Valve overload, busy',
                b'K': 'Syringe move not allowed in valve bypass position, busy',
                b'L': 'No move against limit, busy',
                b'M': 'NVM Memory failure, busy',
                b'N': 'Reserved, busy',
                b'O': 'Command buffer full, busy',
                b'P': 'For 3-way valve only, busy',
                b'Q': 'Loops nested too deep, busy',
                b'R': 'Label not found, busy',
                b'S': 'No end of program, busy',
                b'T': 'Out of program space, busy',
                b'U': 'Home limit not set, busy',
                b'V': 'Call stack overflow, busy',
                b'W': 'Program not present, busy',
                b'X': 'Valve position error, busy',
                b'Y': 'Syringe position error, busy',
                #b'Z': 'Syringe may crash, busy',
               }

CRITICAL_CODE = {b'z': 'Syringe may crash, ready',
                 b'Z': 'Syringe may crash, busy',
                 b'a': 'Syringe not initialized, ready',
                 b'A': 'Syringe not initialized, busy',}