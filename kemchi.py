from tqdm import tqdm
import serial
import time
import math
import warnings
import pandas as pd
import numpy as np

from datetime import datetime, timedelta
import yaml

import logging

from constants import *

import re

#from sampler import *

verbose = True

time_stamp = datetime.now().strftime('%Y-%m-%d-%H-%M')

logging.basicConfig(filename=f'logs/{time_stamp}.log',
                    format='%(asctime)s - %(name)s - %(levelname)s: %(message)s',
                    # encoding='utf-8',
                    level=logging.DEBUG)
logger = logging.getLogger(__name__)

def read_yaml_dict(file_path):
    with open(file_path, 'r') as file:
        yaml_dict = yaml.safe_load(file)
    return yaml_dict

# map of chemical names that are connected to different liquid port on the daisy chain
port_map = read_yaml_dict("config_files/port_map.yaml")

config = pd.read_excel('config_files/lab_config.xlsx', converters={'address':str, })

COM_config = dict(zip(config.valve, config.COM_port))


#eLAB CONFIG 
# first valve/pump in the daisy chain
v0 = serial.Serial(COM_config['v0'], 9600, timeout=0.1)
# second valve in the tree
v1 = serial.Serial(COM_config['v1'], 9600, timeout=0.1)
# third valve in the tree
#v2 = serial.Serial(COM_config['v2'], 9600, timeout=0.1)

# combined list of liquid handling nodes
vtree = [v0, 
         v1, 
         #v2
        ]

# a variable to track the vavle positions for choosing clockwise or counter-clockwise rotation
vstate = [0, 
          0, 
          #0
         ]

vtypes = [6, 
         8,
        ]

speed_setting = [DEFAULT_SPEED]

def tstamp():
    '''
    returns current time as a string HH:MM:SS
    '''
    return datetime.now().strftime('%H:%M:%S')


def set_pump_speed(speed_ml_per_min): # minimum setting is 40 steps/s (hz), factory default 5000 hz
    # pump speed configuration
    speed_setting[0] = speed_ml_per_min
    speed_hz = int(speed_setting[0]/SYRINGE_VOL * MAX_STEPS/60)
    packet = f'/1V{speed_hz}R\r'
    vtree[0].write(bytes(packet, 'utf-8'))
    time.sleep(0.1)
    return

# TODO: add a check for busy status

def is_counter(curr_pos, next_pos, vtype): #returns True for counterclockwise
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


def actuate_valves(port_address):
    for x, y in enumerate(port_address):
        ccw = is_counter(vstate[x], int(y), vtypes[x])
        ccws = '-'
        packet = f'/1o{ccws*ccw}{y}R\r'## TODO: test this code for c-wise or cc-wise rotation
        #logger.debug(packet)
        vtree[x].write(bytes(packet, 'utf-8'))
        vstate[x] = int(y)
        #response = vtree[x].readline()
        #logger.debug(response)
        # delay between actuating valves to decrease simultaneous power draw spike
        time.sleep(0.5) # problem persists on 3rd valve with 0.5.
    time.sleep(1)

    # Check for and log errors, raise warnings
    for x, y in enumerate(port_address):
        interrogate_state(x, 'valve actuation')
    return
    
def aspirate_pump(abs_steps):
    # pump sleep is experimentaly determined
    speed_hz = int(speed_setting[0]/SYRINGE_VOL * MAX_STEPS/60)
    pump_sleep_duration =  (abs_steps/speed_hz) + 3
    # print(speed_hz, pump_sleep_duration)
    packet = f'/1A{abs_steps}R\r'
    # logger.debug(packet)
    vtree[0].write(bytes(packet, 'utf-8'))
    # response = vtree[0].readline()
    # logger.debug(response)
    time.sleep(pump_sleep_duration)
    interrogate_state(0, 'aspirate pump')
    return
    
def dispense_pump(abs_steps):
    #always  dispenses to zero, but needs the number of steps to calculate sleep duration    
    speed_hz = int(speed_setting[0]/SYRINGE_VOL * MAX_STEPS/60)
    pump_sleep_duration =  (abs_steps/speed_hz) + 3
    #print(speed_hz, pump_sleep_duration)
    packet = f'/1A0R\r'
    #logger.debug(packet)
    vtree[0].write(bytes(packet, 'utf-8'))
    #response = vtree[0].readline()
    #logger.debug(response)
    time.sleep(pump_sleep_duration)
    interrogate_state(0, 'dispense pump')
    return
    
def initialize_daisy_chain(home_pos='11'):
    #initialize pump-valve v0
    #actuate_valves('111')
    # TODO add a node count and send nodes * '1' <<<< TODO
    actuate_valves(home_pos)
    message = f'/1W4R\r'
    logger.debug(message)
    vtree[0].write(bytes(message, 'utf-8'))
    time.sleep(5)
    vtree[0].write(b'/1Q\r')
    response = vtree[0].readlines()
    logger.debug(response)
    set_pump_speed(DEFAULT_SPEED)
    dispense_pump(0)
    time.sleep(5)
    return
    
# MAIN FUNCTION
def move_liquid(source, sink, volume, times=1):
    ''' 
        liquid is moved by actuating valves to source node, aspirating a specific volume,
        actuating the valves to destination node and dispensing the volume
        if volume is greater than the syring size, it is split up in equal parts and moved.
        in case of several repeat moves the *times* variable is useful for purging and priming 
        with small (smaller than syringe size) volumes multiple times
    '''
    logger.info(f'moving {volume} ml liquid from {source} to {sink} {times} times')
    if verbose: print(f'{tstamp()} moving {volume} ml liquid from {source} to {sink} {times} times')
    
    # retrieve port adresses from port map
    from_port = port_map[source]
    to_port = port_map[sink]
    
    # CALCULATE NUMBER OF PUMP MOVES AND CONVERT VOLUME TO TOTAL MOTOR STEPS
    total_steps = int(MAX_STEPS*volume/SYRINGE_VOL)
    
    # if volume is greater than the syring size, it is split up in equal parts and moved or several repeat moves
    repeats = math.ceil(total_steps/MAX_STEPS)
    
    if repeats > 1:
        vol_steps = int(total_steps/repeats)
    else:
        vol_steps = total_steps
    
    # times variable is useful for purging and priming with small volumes
    for _ in range(times):

        if verbose == True and times > 1:
            print(f'{tstamp()}    move {_ + 1} of {times}')
        
        for repeat in range(repeats):
            if verbose == True and repeats > 1:
                print(f'{tstamp()}        divided move {repeat+1}/{repeats}: {round(vol_steps*SYRINGE_VOL/MAX_STEPS, 1)}ml ({round((repeat+1)*vol_steps*SYRINGE_VOL/MAX_STEPS, 1)}/{round(SYRINGE_VOL*total_steps/MAX_STEPS, 1)}ml)')
            
            # ACTUATE VALVES TO INPUT
            actuate_valves(from_port)
            
            # ASPIRATE
            aspirate_pump(vol_steps)
            
            # ACTUATE VALVES TO OUTPUT
            actuate_valves(to_port)
            
            # DISPENSE
            dispense_pump(vol_steps)
            
    return



def slow_dispense(source, sink, volume, dispense_speed, times=1):
    ''' 
        liquid is moved by actuating valves to source node, aspirating a specific volume,
        actuating the valves to destination node and dispensing the volume
        if volume is greater than the syring size, it is split up in equal parts and moved.
        in case of several repeat moves the *times* variable is useful for purging and priming 
        with small (smaller than syringe size) volumes multiple times
    '''
    logger.info(f'slow dispense: {volume} ml liquid from {source} to {sink} at {dispense_speed} ml/min, {times} times')
    if verbose: print(f'{tstamp()} slow dispense: {volume} ml liquid from {source} to {sink} at {dispense_speed} ml/min, {times} times')
    
    # retrieve port adresses from port map
    from_port = port_map[source]
    to_port = port_map[sink]
    
    # CALCULATE NUMBER OF PUMP MOVES AND CONVERT VOLUME TO TOTAL MOTOR STEPS
    total_steps = int(MAX_STEPS*volume/SYRINGE_VOL)
    
    # if volume is greater than the syring size, it is split up in equal parts and moved or several repeat moves
    repeats = math.ceil(total_steps/MAX_STEPS)
    
    if repeats > 1:
        vol_steps = int(total_steps/repeats)
    else:
        vol_steps = total_steps
    
    # times variable is useful for purging and priming with small volumes
    for _ in range(times):

        if verbose == True and times > 1:
            print(f'{tstamp()}    move {_ + 1} of {times}')
        
        for repeat in range(repeats):
            if verbose == True and repeats > 1:
                print(f'{tstamp()}        divided move {repeat+1}/{repeats}: {round(vol_steps*SYRINGE_VOL/MAX_STEPS, 1)}ml ({round((repeat+1)*vol_steps*SYRINGE_VOL/MAX_STEPS, 1)}/{round(SYRINGE_VOL*total_steps/MAX_STEPS, 1)}ml)')
            # ACTUATE VALVES TO INPUT
            actuate_valves(from_port)
            
            # ASPIRATE
            
            aspirate_pump(vol_steps)
            
            # ACTUATE VALVES TO OUTPUT
            actuate_valves(to_port)
            
            # DISPENSE
            set_pump_speed(dispense_speed)
            dispense_pump(vol_steps)
            set_pump_speed(DEFAULT_SPEED)
    return

def interrogate_state(vtree_index, substep_name):
    # Define the regex pattern
    pattern_bytes = rb'/0(.*?)\x03\r\n'
    response_codes = set([])
    vtree[vtree_index].write(b'/1Q\r')
    response = vtree[vtree_index].readlines()
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
            logger.critical(warning_string)
            warnings.warn(warning_string)
            raise Exception(f'STALL: {warning_string}')
            
        for code in response_codes.intersection(WARNING_CODE.keys()): # if any warning codes matched with warning code dictionary this gets executed
            warning_string = f'v{vtree_index} {substep_name}: {WARNING_CODE[code]}'
            logger.warning(warning_string) 
            warnings.warn(warning_string)

        for code in response_codes.intersection(OK_CODE.keys()): # if any warning codes matched with warning code dictionary this gets executed
            ok_string = f'v{vtree_index} {substep_name}: {OK_CODE[code]}'
            logger.debug(ok_string)

        # check for and log any unknown responses
        for code in response_codes.difference(WARNING_CODE.keys(), OK_CODE.keys()):
            warning_string = f'v{vtree_index} {substep_name}: unknwon response code - {code}'
            logger.warning(warning_string) 
            warnings.warn(warning_string)
            
    else:
        warning_string = f'v{vtree_index} {substep_name}: No response'
        logger.warning(warning_string)
        warnings.warn(warning_string)
    time.sleep(0.1)
    return

def relative_dispense_pump(abs_steps, offset_steps):
    '''
        needs the number of both absolute steps and offset steps to calculate the difference for the sleep duration    
    '''
    speed_hz = int(speed_setting[0]/SYRINGE_VOL * MAX_STEPS/60)
    pump_sleep_duration =  ((abs_steps-offset_steps)/speed_hz) + 3
    #print(speed_hz, pump_sleep_duration)
    packet = f'/1A{offset_steps}R\r'
    #logger.debug(packet)
    vtree[0].write(bytes(packet, 'utf-8'))
    #response = vtree[0].readline()
    #logger.debug(response)
    time.sleep(pump_sleep_duration)
    interrogate_state(0, 'relative dispense pump')
    return

def fill_syringe(node, offset, speed):
    '''
        offset fill handling
    '''
    logger.info(f'fill syringe: {offset} ml liquid from {node} at {speed} ml/min')
    if verbose: print(f'{tstamp()} fill syringe: {offset} ml liquid from {node} at {speed} ml/min')
    offset_steps = int(MAX_STEPS*offset/SYRINGE_VOL)
    port_pos = port_map[node]
    actuate_valves(port_pos)
    set_pump_speed(speed)
    aspirate_pump(offset_steps)
    set_pump_speed(DEFAULT_SPEED)
    return

def empty_syringe(node, offset, speed):
    '''
        offset fill handling
    '''
    logger.info(f'empty syringe: {offset} ml liquid to {node} at {speed} ml/min')
    if verbose: print(f'{tstamp()} empty syringe: {offset} ml liquid to {node} at {speed} ml/min')
    offset_steps = int(MAX_STEPS*offset/SYRINGE_VOL)
    port_pos = port_map[node]
    actuate_valves(port_pos)
    set_pump_speed(speed)
    dispense_pump(offset_steps)
    set_pump_speed(DEFAULT_SPEED)
    return

def relative_aspirate_pump(abs_steps, offset_steps):
    #always  dispenses to zero, but needs the number of steps to calculate sleep duration    
    speed_hz = int(speed_setting[0]/SYRINGE_VOL * MAX_STEPS/60)
    pump_sleep_duration =  ((abs_steps-offset_steps)/speed_hz) + 3
    #print(speed_hz, pump_sleep_duration)
    packet = f'/1A{abs_steps}R\r'
    #logger.debug(packet)
    vtree[0].write(bytes(packet, 'utf-8'))
    #response = vtree[0].readline()
    #logger.debug(response)
    time.sleep(pump_sleep_duration)
    interrogate_state(0, 'relative aspirate pump')
    return

def partial_dispense(source, sink, volume, offset, aspirate_speed, dispense_speed, times=1):
    ''' 
        liquid is moved by actuating valves to source node, aspirating a specific volume,
        actuating the valves to destination node and dispensing the volume
        if volume is greater than the syring size, it is split up in equal parts and moved.
        in case of several repeat moves the *times* variable is useful for purging and priming 
        with small (smaller than syringe size) volumes multiple times
    '''
    logger.info(f'partial dispense: {volume} ml liquid from {source} to {sink} at {dispense_speed} ml/min, {offset} offset volume, {times} times')
    if verbose: print(f'{tstamp()} partial dispense: {volume} ml liquid from {source} to {sink} at {dispense_speed} ml/min, {offset} offset volume, {times} times')
    
    # retrieve port adresses from port map
    from_port = port_map[source]
    to_port = port_map[sink]

    # calculate offset
    offset_steps = int(MAX_STEPS*offset/SYRINGE_VOL)
    
    # CALCULATE NUMBER OF PUMP MOVES AND CONVERT VOLUME TO TOTAL MOTOR STEPS
    total_steps = int(MAX_STEPS*volume/SYRINGE_VOL)
    # if volume is greater than the syring size, it is split up in equal parts and moved or several repeat moves
    repeats = math.ceil(total_steps/(MAX_STEPS-offset_steps))
    
    if repeats > 1:
        vol_steps = int(total_steps/repeats)
    else:
        vol_steps = total_steps

    # times variable is useful for purging and priming with small volumes
    for _ in range(times):

        if verbose == True and times > 1:
            print(f'{tstamp()}    move {_ + 1} of {times}')
        
        for repeat in range(repeats):
            
            if verbose == True and repeats > 1:
                print(f'{tstamp()}        divided move {repeat+1}/{repeats}: {round(vol_steps*SYRINGE_VOL/MAX_STEPS, 1)}ml ({round((repeat+1)*vol_steps*SYRINGE_VOL/MAX_STEPS, 1)}/{round(SYRINGE_VOL*total_steps/MAX_STEPS, 1)}ml)')
            # ACTUATE VALVES TO INPUT
            actuate_valves(from_port)
            
            # ASPIRATE
            set_pump_speed(aspirate_speed)
            relative_aspirate_pump(vol_steps + offset_steps, offset_steps)
            
            # ACTUATE VALVES TO OUTPUT
            actuate_valves(to_port)
            
            # DISPENSE
            set_pump_speed(dispense_speed)
            #dispense to offset
            relative_dispense_pump(vol_steps + offset_steps, offset_steps)
    
    set_pump_speed(DEFAULT_SPEED)
    return

def load_chemicals_to_reactors(exp_subset, reactors, STEP):
    for chemical_name_step in STEP:
        if np.any(exp_subset[chemical_name_step]):
            chemical_name = chemical_name_step.split('_')[0]
            # PRIME CHEMICAL
            #print(f'priming {chemical_name}')
            move_liquid(chemical_name, 'waste', 0.5, 4)
            chemical_stock = list(exp_subset[chemical_name_step])
            for reactor_index, volume in enumerate(chemical_stock):
                if volume != 0:
                    #print(f'moving {volume} ml from {chemical_name} to {reactors[reactor_index]}')
                    move_liquid(chemical_name, reactors[reactor_index], volume)
    return


def sample_reactors(reactors, count):
    for i in range(count):
        move_liquid(reactors[i], 'waste', 0.5, 2) # TODO: needs to account for the dead volume of tube
        move_liquid(reactors[i], 'sampler', 1)
        move_liquid('air', 'waste', 2)
        move_liquid('air', 'sampler', 1)
        move_liquid('water', 'waste', 2)
        move_liquid('water', 'sampler', 0.5)
        move_liquid('air', 'waste', 2)
        move_liquid('air', 'sampler', 1)
        sampler_next()
        time.sleep(1)
    return

def check_chem_ports(port_map, df, exclude_list):
    ports = port_map.keys()
    chems_steps = df.columns
    for chem_step in chems_steps:
        chem = chem_step.split('_')[0]
        if chem not in ports and chem not in exclude_list:
            raise Exception(f'Chemical {chem} not added to port_map.yaml configuration file!')
        elif chem not in exclude_list:
            print(f'{chem_step}: {chem}: {port_map[chem]} OK')
    print('Chem port check result: appears ok')
    return

# TODO: do a self test, to run at the least when initiating    
def self_check():
    pass


