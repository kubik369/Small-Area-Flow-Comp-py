#!/usr/bin/env python3

import argparse
import math
import re

SCRIPT_VERSION = '0.5.0'
FLOW_MODEL_VERSION = '0.1.1'

MAX_MODIFIED_EXTRUSION_LENGTH = 17
MIN_FLOW_PERCENTAGE = 30
FLOW_DROPOFF = 12

parser = argparse.ArgumentParser(description='Small Area Flow Compensation script')
parser.add_argument('gcode_path')
parser.add_argument("-l", "--max-length", help="Maximum modified extrusion length in milimeters", type=int)
parser.add_argument("-f", "--min-flow", help="Minimum flow percentage, as an integer (30 percent => the argument is 30)", type=int)
parser.add_argument("-d", "--flow-dropoff", help="How exponential the flow drop off is (must be a multiple of 2v)", type=int)

args = parser.parse_args()

if args.max_length is not None:
    MAX_MODIFIED_EXTRUSION_LENGTH = int(args.max_length)
if args.min_flow is not None:
    MIN_FLOW_PERCENTAGE = int(args.min_flow)
if args.flow_dropoff is not None:
    FLOW_DROPOFF = int(args.flow_dropoff)


# Flags that are checked for in slicer gcode
slicer_infill_flags = [ ";TYPE:Solid infill", ";TYPE:Top solid infill", "; FEATURE: Top surface", "; FEATURE: Internal solid infill", "; FEATURE: Bottom surface"]
slicer_generic_flags = [ ";TYPE:" , "; FEATURE:"]


def parse_g1_arguments(g1_command : str) -> list[float]:
    coordinate_regexes = [
        r"^G1.*X([-]?([0-9]*[.])?[0-9]+)",
        r"^G1.*Y([-]?([0-9]*[.])?[0-9]+)",
        r"^G1.*Z([-]?([0-9]*[.])?[0-9]+)",
        r"^G1.*E([-]?([0-9]*[.])?[0-9]+)",
        r"^G1.*F([0-9]+)"
    ]
    return list(map(
        lambda r: float(re.search(r, g1_command).group(1)) if re.match(r, g1_command) else None,
        coordinate_regexes
    ))

def coordinates_to_g1(coordinates):
    gcode_line = ['G1']
    for index, cord_letter in enumerate(['X', 'Y', 'Z', 'E', 'F']):
        if g1_arguments[index] is not None:
            gcode_line.append(cord_letter + g1_arguments[index])
    return ' '.join(gcode_line)


def calculate_compensation_factor(old_flow_value, extrusion_length): 
    if extrusion_length > MAX_MODIFIED_EXTRUSION_LENGTH:
        return 1
    magic_number = (MIN_FLOW_PERCENTAGE - 1) * (MAX_MODIFIED_EXTRUSION_LENGTH ** (-1 * FLOW_DROPOFF))
    return magic_number * ((extrusion_length - MAX_MODIFIED_EXTRUSION_LENGTH) ** FLOW_DROPOFF) + 1


with open(args.gcode_path, 'r') as input_file, open('./out.gcode', 'w') as output_file:
    first_line = input_file.readline()
    if re.match('^; File Parsed By Flow Comp Script', first_line):
        print("File has already been processed by this script")
        exit(0)

    output_file.write(first_line)
    toolhead_position = (0, 0)
    currently_adjusting_flow = False
    for line in input_file:
        if line[:-1] in slicer_infill_flags:
            currently_adjusting_flow = True
        elif currently_adjusting_flow is True:
            for flag in slicer_generic_flags:
                if flag in line:
                    currently_adjusting_flow = False
        
        # Filter out all non-G1 moves
        if re.search('^G1', line) is None:
            output_file.write(line)
            continue

        ## Only G1 moves get to this point
        g1_arguments = parse_g1_arguments(line)
        print(g1_arguments)
        
        # Filter out all moves which are either not in XY plane or do not extrude
        if g1_arguments[0] is None or g1_arguments[1] is None or g1_arguments[4] is None:
            output_file.write(line)
            continue
        
        new_toolhead_position = (g1_arguments[0], g1_arguments[1])
        e_value = g1_arguments[4]
        
        if currently_adjusting_flow: and e_value > 0:
            extrusion_length = math.sqrt(
                (toolhead_position[0] - new_toolhead_position[0])**2
                + (toolhead_position[1] - new_toolhead_position[1])**2
            )
            compensation_factor = calculate_compensation_factor(e_value, extrusion_length)
            new_e_value = e_value * compensation_factor
            output_line_comment = f'; Old Flow Value: {e_value} tool at: X{new_toolhead_position[0]} Y{new_toolhead_position[1]} was at: X{toolhead_position[0]} Y{toolhead_position[1]}'
            output_line = coordinates_to_g1(g1_arguments) + output_line_comment
        else:
            output_line = coordinates_to_g1(g1_arguments)
        
        output_file.write(output_line + '\n')
        toolhead_position = (
            g1_arguments[0] if g1_arguments[0] is not None else toolhead_position[0],
            g1_arguments[1] if g1_arguments[1] is not None else toolhead_position[1],
        )
