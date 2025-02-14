import serial
import time
import math
import warnings
import numpy as np
from datetime import datetime #, timedelta
import yaml
import logging
from constants import MAX_STEPS, OK_CODE, WARNING_CODE, CRITICAL_CODE #TODO rewrite to match modules in packages
import re



class DaisyChain:
    
    def read_yaml_dict(self, file_path):
        with open(file_path, 'r') as file:
            yaml_dict = yaml.safe_load(file)
        return yaml_dict

    def __init__(self, 
                 port_map_path, 
                 config_path,
                 verbose = True
                 ):
        self.verbose = verbose
        self.port_map = self.read_yaml_dict(port_map_path)
        self.config = self.read_yaml_dict(config_path)
        time_stamp = datetime.now().strftime('%Y-%m-%d-%H-%M')

        logging.basicConfig(filename=f'logs/{time_stamp}.log',
                            format='%(asctime)s - %(name)s - %(levelname)s: %(message)s',
                            # encoding='utf-8',
                            level=logging.DEBUG)
        
        self.logger = logging.getLogger(__name__)
        self.vtree = [serial.Serial(com_port, 9600, timeout=0.1) for com_port in self.config['com_ports']]
        self.vstate = [0 for v in self.config['valve_types']]
        self.vtypes = [vtype for vtype in self.config['valve_types']]
        self.SYRINGE_VOL = self.config['syringe_volume']
        self.DEFAULT_SPEED = self.config['default_speed']
        self.speed_setting = [self.DEFAULT_SPEED]

    def tstamp(self):
        '''
        returns current time as a string HH:MM:SS
        '''
        return datetime.now().strftime('%H:%M:%S')


    def set_pump_speed(self, speed_ml_per_min): # minimum setting is 40 steps/s (hz), factory default 5000 hz
        # pump speed configuration
        self.speed_setting = speed_ml_per_min
        speed_hz = int(self.speed_setting/self.SYRINGE_VOL * MAX_STEPS/60)
        packet = f'/1V{speed_hz}R\r'
        self.vtree[0].write(bytes(packet, 'utf-8'))
        time.sleep(0.1)
        return


    def is_counter(self, curr_pos, next_pos, vtype): #returns True for counterclockwise
        if curr_pos > next_pos:
            c_wise = next_pos + vtype - curr_pos
            cc_wise = curr_pos - next_pos
        else:
            c_wise = next_pos - curr_pos
            cc_wise = curr_pos + vtype - next_pos
        if c_wise > cc_wise:
            return True
        else:
            return False


    def actuate_valves(self, port_address):
        for x, y in enumerate(port_address):
            ccw = self.is_counter(self.vstate[x], int(y), self.vtypes[x])
            ccws = '-'
            packet = f'/1o{ccws*ccw}{y}R\r'## TODO: test this code for c-wise or cc-wise rotation
            #logger.debug(packet)
            self.vtree[x].write(bytes(packet, 'utf-8'))
            self.vstate[x] = int(y)
            #response = vtree[x].readline()
            #logger.debug(response)
            # delay between actuating valves to decrease simultaneous power draw spike
            time.sleep(0.5) # problem persists on 3rd valve with 0.5.
        time.sleep(1)

        # Check for and log errors, raise warnings
        for x, y in enumerate(port_address):
            self.interrogate_state(x, 'valve actuation')
        return
    
    def aspirate_pump(self, abs_steps):
        # pump sleep is experimentaly determined
        speed_hz = int(self.speed_setting/self.SYRINGE_VOL * MAX_STEPS/60)
        pump_sleep_duration =  (abs_steps/speed_hz) + 3
        # print(speed_hz, pump_sleep_duration)
        packet = f'/1A{abs_steps}R\r'
        # logger.debug(packet)
        self.vtree[0].write(bytes(packet, 'utf-8'))
        # response = vtree[0].readline()
        # logger.debug(response)
        time.sleep(pump_sleep_duration)
        self.interrogate_state(0, 'aspirate pump')
        return
    
    def dispense_pump(self, abs_steps):
        #always  dispenses to zero, but needs the number of steps to calculate sleep duration    
        speed_hz = int(self.speed_setting/self.SYRINGE_VOL * MAX_STEPS/60)
        pump_sleep_duration =  (abs_steps/speed_hz) + 3
        #print(speed_hz, pump_sleep_duration)
        packet = f'/1A0R\r'
        #logger.debug(packet)
        self.vtree[0].write(bytes(packet, 'utf-8'))
        #response = vtree[0].readline()
        #logger.debug(response)
        time.sleep(pump_sleep_duration)
        self.interrogate_state(0, 'dispense pump')
        return
    
    def initialize_daisy_chain(self, home_pos=False):

        if home_pos == False:
            for v in self.vtree:
                v.write(bytes('/1o1R\r', 'utf-8'))
        else:
            self.actuate_valves(home_pos)

            
        #packet = '/1W4R\r'
        #self.logger.debug(packet)
        
        # flush errors
        self.vtree[0].write(b'/1Q\r')
        #response = self.vtree[0].readlines()
        #self.logger.debug(response)
        self.vtree[0].write(b'/1W4R\r')
        response = self.vtree[0].readlines()
        self.logger.debug(f'INITIALIZE COMMAND RESPONSE: {response}')
        if self.verbose: print('initialization response: ', response)
        time.sleep(5)
        self.vtree[0].write(b'/1Q\r')
        response = self.vtree[0].readlines()
        self.logger.debug(response)
        self.set_pump_speed(self.DEFAULT_SPEED)
        self.dispense_pump(0)
        time.sleep(5) # presumably enough time to dispense, TODO: add busy status checks in state interogation
        return
    
    # MAIN FUNCTION
    def move_liquid(self, source, sink, volume, times=1):
        ''' 
            liquid is moved by actuating valves to source node, aspirating a specific volume,
            actuating the valves to destination node and dispensing the volume
            if volume is greater than the syring size, it is split up in equal parts and moved.
            in case of several repeat moves the *times* variable is useful for purging and priming 
            with small (smaller than syringe size) volumes multiple times
        '''
        self.logger.info(f'moving {volume} ml liquid from {source} to {sink} {times} times')
        if self.verbose: print(f'{self.tstamp()} moving {volume} ml liquid from {source} to {sink} {times} times')
        
        # retrieve port adresses from port map
        from_port = self.port_map[source]
        to_port = self.port_map[sink]
        
        # CALCULATE NUMBER OF PUMP MOVES AND CONVERT VOLUME TO TOTAL MOTOR STEPS
        total_steps = int(MAX_STEPS*volume/self.SYRINGE_VOL)
        
        # if volume is greater than the syring size, it is split up in equal parts and moved or several repeat moves
        repeats = math.ceil(total_steps/MAX_STEPS)
        
        if repeats > 1:
            vol_steps = int(total_steps/repeats)
        else:
            vol_steps = total_steps
        
        # times variable is useful for purging and priming with small volumes
        for _ in range(times):

            if self.verbose == True and times > 1:
                print(f'{self.tstamp()}    move {_ + 1} of {times}')
            
            for repeat in range(repeats):
                if self.verbose == True and repeats > 1:
                    print(f'{self.tstamp()}        divided move {repeat+1}/{repeats}: {round(vol_steps*self.SYRINGE_VOL/MAX_STEPS, 1)}ml ({round((repeat+1)*vol_steps*self.SYRINGE_VOL/MAX_STEPS, 1)}/{round(self.SYRINGE_VOL*total_steps/MAX_STEPS, 1)}ml)')
                
                # ACTUATE VALVES TO INPUT
                self.actuate_valves(from_port)
                
                # ASPIRATE
                self.aspirate_pump(vol_steps)
                
                # ACTUATE VALVES TO OUTPUT
                self.actuate_valves(to_port)
                
                # DISPENSE
                self.dispense_pump(vol_steps)
                
        return



    def slow_dispense(self, source, sink, volume, dispense_speed, times=1):
        ''' 
            slow dispence is a modified move_liquid function for when slow additions or semi-continuos flow puming is required

        '''
        self.logger.info(f'slow dispense: {volume} ml liquid from {source} to {sink} at {dispense_speed} ml/min, {times} times')
        if self.verbose: print(f'{self.tstamp()} slow dispense: {volume} ml liquid from {source} to {sink} at {dispense_speed} ml/min, {times} times')
        
        # retrieve port adresses from port map
        from_port = self.port_map[source]
        to_port = self.port_map[sink]
        
        # CALCULATE NUMBER OF PUMP MOVES AND CONVERT VOLUME TO TOTAL MOTOR STEPS
        total_steps = int(MAX_STEPS*volume/self.SYRINGE_VOL)
        
        # if volume is greater than the syring size, it is split up in equal parts and moved or several repeat moves
        repeats = math.ceil(total_steps/MAX_STEPS)
        
        if repeats > 1:
            vol_steps = int(total_steps/repeats)
        else:
            vol_steps = total_steps
        
        # times variable is useful for purging and priming with small volumes
        for _ in range(times):

            if self.verbose == True and times > 1:
                print(f'{self.tstamp()}    move {_ + 1} of {times}')
            
            for repeat in range(repeats):
                if self.verbose == True and repeats > 1:
                    print(f'{self.tstamp()}        divided move {repeat+1}/{repeats}: {round(vol_steps*self.SYRINGE_VOL/MAX_STEPS, 1)}ml ({round((repeat+1)*vol_steps*self.SYRINGE_VOL/MAX_STEPS, 1)}/{round(self.SYRINGE_VOL*total_steps/MAX_STEPS, 1)}ml)')
                # ACTUATE VALVES TO INPUT
                self.actuate_valves(from_port)
                
                # ASPIRATE
                
                self.aspirate_pump(vol_steps)
                
                # ACTUATE VALVES TO OUTPUT
                self.actuate_valves(to_port)
                
                # DISPENSE
                self.set_pump_speed(dispense_speed)
                self.dispense_pump(vol_steps)
                self.set_pump_speed(self.DEFAULT_SPEED)
        return

    def interrogate_state(self, vtree_index, substep_name):
        # Define the regex pattern
        pattern_bytes = rb'/0(.*?)\x03\r\n'
        response_codes = set([])
        self.vtree[vtree_index].write(b'/1Q\r')
        response = self.vtree[vtree_index].readlines()
        for line in response:
            # Find all matches in the input bytes string
            matches = re.findall(pattern_bytes, line)
            # Print the extracted characters
            for match in matches:
                response_codes.add(match)
        #print(response_set)
        if response_codes:
            for code in response_codes.intersection(CRITICAL_CODE.keys()): # if any warning codes matched with warning code dictionary this gets executed
                warning_string = f'v{vtree_index} {substep_name}: {CRITICAL_CODE[code]}'
                self.logger.critical(warning_string)
                warnings.warn(warning_string)
                raise Exception(f'STALL: {warning_string}')
                
            for code in response_codes.intersection(WARNING_CODE.keys()): # if any warning codes matched with warning code dictionary this gets executed
                warning_string = f'v{vtree_index} {substep_name}: {WARNING_CODE[code]}'
                self.logger.warning(warning_string) 
                warnings.warn(warning_string)

            for code in response_codes.intersection(OK_CODE.keys()): # if any warning codes matched with warning code dictionary this gets executed
                ok_string = f'v{vtree_index} {substep_name}: {OK_CODE[code]}'
                self.logger.debug(ok_string)

            # check for and log any unknown responses
            for code in response_codes.difference(WARNING_CODE.keys(), OK_CODE.keys()):
                warning_string = f'v{vtree_index} {substep_name}: unknwon response code - {code}'
                self.logger.warning(warning_string) 
                warnings.warn(warning_string)
                
        else:
            warning_string = f'v{vtree_index} {substep_name}: No response'
            self.logger.warning(warning_string)
            warnings.warn(warning_string)
        time.sleep(0.1)
        return

    def relative_dispense_pump(self, abs_steps, offset_steps):
        '''
            needs the number of both absolute steps and offset steps to calculate the difference for the sleep duration    
        '''
        speed_hz = int(self.speed_setting/self.SYRINGE_VOL * MAX_STEPS/60)
        pump_sleep_duration =  ((abs_steps-offset_steps)/speed_hz) + 3
        #print(speed_hz, pump_sleep_duration)
        packet = f'/1A{offset_steps}R\r'
        #logger.debug(packet)
        self.vtree[0].write(bytes(packet, 'utf-8'))
        #response = vtree[0].readline()
        #logger.debug(response)
        time.sleep(pump_sleep_duration)
        self.interrogate_state(0, 'relative dispense pump')
        return

    def fill_syringe(self, node, offset, speed):
        '''
            offset fill handling
        '''
        self.logger.info(f'fill syringe: {offset} ml liquid from {node} at {speed} ml/min')
        if self.verbose: print(f'{self.tstamp()} fill syringe: {offset} ml liquid from {node} at {speed} ml/min')
        offset_steps = int(MAX_STEPS*offset/self.SYRINGE_VOL)
        port_pos = self.port_map[node]
        self.actuate_valves(port_pos)
        self.set_pump_speed(speed)
        self.aspirate_pump(offset_steps)
        self.set_pump_speed(self.DEFAULT_SPEED)
        return

    def empty_syringe(self, node, offset, speed):
        '''
            offset fill handling
        '''
        self.logger.info(f'empty syringe: {offset} ml liquid to {node} at {speed} ml/min')
        if self.verbose: print(f'{self.tstamp()} empty syringe: {offset} ml liquid to {node} at {speed} ml/min')
        offset_steps = int(MAX_STEPS*offset/self.SYRINGE_VOL)
        port_pos = self.port_map[node]
        self.actuate_valves(port_pos)
        self.set_pump_speed(speed)
        self.dispense_pump(offset_steps)
        self.set_pump_speed(self.DEFAULT_SPEED)
        return

    def relative_aspirate_pump(self, abs_steps, offset_steps):
        '''
            custom step with offset fill handling
        '''
        speed_hz = int(self.speed_setting/self.SYRINGE_VOL * MAX_STEPS/60)
        pump_sleep_duration =  ((abs_steps-offset_steps)/speed_hz) + 3
        #print(speed_hz, pump_sleep_duration)
        packet = f'/1A{abs_steps}R\r'
        #logger.debug(packet)
        self.vtree[0].write(bytes(packet, 'utf-8'))
        #response = vtree[0].readline()
        #logger.debug(response)
        time.sleep(pump_sleep_duration)
        self.interrogate_state(0, 'relative aspirate pump')
        return

    def partial_dispense(self, source, sink, volume, offset, aspirate_speed, dispense_speed, times=1):
        ''' 
            liquid is moved by actuating valves to source node, aspirating a specific volume,
            actuating the valves to destination node and dispensing the volume
            if volume is greater than the syring size, it is split up in equal parts and moved.
            in case of several repeat moves the *times* variable is useful for purging and priming 
            with small (smaller than syringe size) volumes multiple times
        '''
        self.logger.info(f'partial dispense: {volume} ml liquid from {source} to {sink} at {dispense_speed} ml/min, {offset} offset volume, {times} times')
        if self.verbose: print(f'{self.tstamp()} partial dispense: {volume} ml liquid from {source} to {sink} at {dispense_speed} ml/min, {offset} offset volume, {times} times')
        
        # retrieve port adresses from port map
        from_port = self.port_map[source]
        to_port = self.port_map[sink]

        # calculate offset
        offset_steps = int(MAX_STEPS*offset/self.SYRINGE_VOL)
        
        # CALCULATE NUMBER OF PUMP MOVES AND CONVERT VOLUME TO TOTAL MOTOR STEPS
        total_steps = int(MAX_STEPS*volume/self.SYRINGE_VOL)
        # if volume is greater than the syring size, it is split up in equal parts and moved or several repeat moves
        repeats = math.ceil(total_steps/(MAX_STEPS-offset_steps))
        
        if repeats > 1:
            vol_steps = int(total_steps/repeats)
        else:
            vol_steps = total_steps

        # times variable is useful for purging and priming with small volumes
        for _ in range(times):

            if self.verbose == True and times > 1:
                print(f'{self.tstamp()}    move {_ + 1} of {times}')
            
            for repeat in range(repeats):
                
                if self.verbose == True and repeats > 1:
                    print(f'{self.tstamp()}        divided move {repeat+1}/{repeats}: {round(vol_steps*self.SYRINGE_VOL/MAX_STEPS, 1)}ml ({round((repeat+1)*vol_steps*self.SYRINGE_VOL/MAX_STEPS, 1)}/{round(self.SYRINGE_VOL*total_steps/MAX_STEPS, 1)}ml)')
                # ACTUATE VALVES TO INPUT
                self.actuate_valves(from_port)
                
                # ASPIRATE
                self.set_pump_speed(aspirate_speed)
                self.relative_aspirate_pump(vol_steps + offset_steps, offset_steps)
                
                # ACTUATE VALVES TO OUTPUT
                self.actuate_valves(to_port)
                
                # DISPENSE
                self.set_pump_speed(dispense_speed)
                #dispense to offset
                self.relative_dispense_pump(vol_steps + offset_steps, offset_steps)
        
        self.set_pump_speed(self.DEFAULT_SPEED)
        return



    # TODO: do a self test, to run at the least when initiating    
    def self_check():
        pass


