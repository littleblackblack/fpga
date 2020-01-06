#!/usr/bin/env python
"""
Copyright 2016-2017 Ettus Research
Copyright 2019 Ettus Research, A National Instrument Brand

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from __future__ import print_function
import argparse
import os
import re
import glob

HEADER_TMPL = """/////////////////////////////////////////////////////////
// Auto-generated by uhd_image_builder.py! Any changes
// in this file will be overwritten the next time
// this script is run.
/////////////////////////////////////////////////////////
localparam NUM_CE = {num_ce};
wire [NUM_CE*64-1:0] ce_flat_o_tdata, ce_flat_i_tdata;
wire [63:0]          ce_o_tdata[0:NUM_CE-1], ce_i_tdata[0:NUM_CE-1];
wire [NUM_CE-1:0]    ce_o_tlast, ce_o_tvalid, ce_o_tready, ce_i_tlast, ce_i_tvalid, ce_i_tready;
wire [63:0]          ce_debug[0:NUM_CE-1];
// Flattern CE tdata arrays
genvar k;
generate
  for (k = 0; k < NUM_CE; k = k + 1) begin
    assign ce_o_tdata[k] = ce_flat_o_tdata[k*64+63:k*64];
    assign ce_flat_i_tdata[k*64+63:k*64] = ce_i_tdata[k];
  end
endgenerate
"""

BLOCK_TMPL = """
noc_block_{blockname} {blockparameters} {instname} (
  .bus_clk(bus_clk), .bus_rst(bus_rst),
  .ce_clk({clock}_clk), .ce_rst({clock}_rst),
  .i_tdata(ce_o_tdata[{n}]), .i_tlast(ce_o_tlast[{n}]), .i_tvalid(ce_o_tvalid[{n}]), .i_tready(ce_o_tready[{n}]),
  .o_tdata(ce_i_tdata[{n}]), .o_tlast(ce_i_tlast[{n}]), .o_tvalid(ce_i_tvalid[{n}]), .o_tready(ce_i_tready[{n}]),
  .debug(ce_debug[{n}]){extraports}
);
"""

FILL_FIFO_TMPL = """
// Fill remaining crossbar ports with loopback FIFOs
genvar n;
generate
  for (n = {fifo_start}; n < NUM_CE; n = n + 1) begin
    noc_block_axi_fifo_loopback inst_noc_block_axi_fifo_loopback (
      .bus_clk(bus_clk), .bus_rst(bus_rst),
      .ce_clk(ce_clk), .ce_rst(ce_rst),
      .i_tdata(ce_o_tdata[n]), .i_tlast(ce_o_tlast[n]), .i_tvalid(ce_o_tvalid[n]), .i_tready(ce_o_tready[n]),
      .o_tdata(ce_i_tdata[n]), .o_tlast(ce_i_tlast[n]), .o_tvalid(ce_i_tvalid[n]), .o_tready(ce_i_tready[n]),
      .debug(ce_debug[n])
    );
  end
endgenerate
"""

# List of blocks that are part of our library but that do not take part
# in the process this tool provides
BLACKLIST = {'radio_core', 'axi_dma_fifo'}

OOT_DIR_TMPL = """\nOOT_DIR = {oot_dir}\n"""
OOT_INC_TMPL = """include $(OOT_DIR)/Makefile.inc\n"""
OOT_SRCS_TMPL = """RFNOC_OOT_SRCS += {sources}\n"""
OOT_SRCS_FILE_HDR = """##################################################
# Include OOT makefiles
##################################################\n"""


def setup_parser():
    """
    Create argument parser
    """
    parser = argparse.ArgumentParser(
        description="Generate the NoC block instantiation file",
    )
    parser.add_argument(
        "-I", "--include-dir",
        help="Path directory of the RFNoC Out-of-Tree module",
        nargs='+',
        default=None)
    parser.add_argument(
        "-y", "--yml",
        help="YML file definition of onboard blocks\
              (overrides the 'block' positional arguments)",
        default=None)
    parser.add_argument(
        "-m", "--max-num-blocks", type=int,
        help="Maximum number of blocks (Max. Allowed for x310|x300: 10,\
                for e300: 14, for e320: 12, for n300: 11, \
                for n310/n320: 10)",
        default=10)
    parser.add_argument(
        "--fill-with-fifos",
        help="If the number of blocks provided was smaller than the max\
                number, fill the rest with FIFOs",
        action="store_true")
    parser.add_argument(
        "-o", "--outfile",
        help="Output /path/filename - By running this directive,\
                you won't build your IP",
        default=None)
    parser.add_argument(
        "--auto-inst-src",
        help="Advanced Usage: The Verilog source for the auto_inst file that "
             "will be used instead of generating one automatically",
        default=None)
    parser.add_argument(
        "-d", "--device",
        help="Device to be programmed [x300, x310, e310, e320, n300, n310, n320]",
        default="x310")
    parser.add_argument(
        "-t", "--target",
        help="Build target - image type [X3X0_RFNOC_HG, X3X0_RFNOC_XG,\
                E310_RFNOC_sg3, E320_RFNOC_1G, N310_RFNOC_HG, ...]",
        default=None)
    parser.add_argument(
        "-g", "--GUI",
        help="Open Vivado GUI during the FPGA building process",
        action="store_true")
    parser.add_argument(
        "-c", "--clean-all",
        help="Cleans the IP before a new build",
        action="store_true")
    parser.add_argument(
        "blocks",
        help="List block names to instantiate.",
        default="",
        nargs='*',
    )
    return parser

def get_default_parameters():
    default = {"clock" : "ce",
               "parameters" : None,
               "extraports" : None}
    return default


def parse_yml(ymlfile):
    """
    Parse an input yaml file with a list of blocks and parameters!
    """
    try:
        import yaml
    except ImportError:
        print('[ERROR] Could not import yaml module')
        exit(1)

    with open(ymlfile, 'r') as input_file:
        data = yaml.load(input_file)
    blocks = []
    params = []
    for val in data:
        print(val['block'])
        blocks.append(val['block'])
        blockparams = get_default_parameters()
        if "clock" in val:
            blockparams["clock"] = val["clock"]
        if "parameters" in val:
            blockparams["parameters"] = val["parameters"]
        if "extraports" in val:
            blockparams["extraports"] = val["extraports"]
        print(blockparams)
        params.append(blockparams)
    print(data)
    return blocks, params

def format_param_str(parameters):
    """
    Take a single block parameter dictionary and format as a verilog string
    """
    paramstr = ""
    if parameters:
        paramstrlist = []
        for key in parameters.keys():
            value = ""
            if parameters[key] is not None:
                value = parameters[key]
            currstr = ".%s(%s)" % (str.upper(key), value)
            paramstrlist.append(currstr)
        paramstr = "#(%s)" % (", ".join(paramstrlist))
    return paramstr

def format_port_str(extraports):
    """
    Take a single dictionary and format as a verilog string representing extra block ports
    """
    portstr = ""
    if extraports:
        portstrlist = []
        for key in extraports.keys():
            value = ""
            if extraports[key] is not None:
                value = extraports[key]
            currstr = ".%s(%s)" % (key, value)
            portstrlist.append(currstr)
        portstr = ",\n  %s" % (",\n  ".join(portstrlist))
    return portstr

def create_auto_inst(blocks, blockparams, max_num_blocks, fill_with_fifos=False):
    """
    Returns the Verilog source for the auto_inst file.
    """
    if len(blocks) == 0:
        print("[GEN_RFNOC_INST ERROR] No blocks specified!")
        exit(1)
    if len(blocks) > max_num_blocks:
        print("[GEN_RFNOC_INST ERROR] Trying to connect {} blocks, max is {}"
              .format(len(blocks), max_num_blocks))
        exit(1)
    num_ce = max_num_blocks
    if not fill_with_fifos:
        num_ce = len(blocks)
    vfile = HEADER_TMPL.format(num_ce=num_ce)
    blocks_in_blacklist = [block for block in blocks if block in BLACKLIST]
    if len(blocks_in_blacklist):
        print("[RFNoC ERROR]: The following blocks require special treatment and"\
                " can't be instantiated with this tool:  ")
        for element in blocks_in_blacklist:
            print(" * ", element)
        print("Remove them from the command and run the uhd_image_builder.py again.")
        exit(0)
    print("--Using the following blocks to generate image:")
    block_count = {k: 0 for k in set(blocks)}
    for i, (block, params) in enumerate(zip(blocks, blockparams)):
        block_count[block] += 1
        instname = "inst_{}{}".format(block, "" \
                if block_count[block] == 1 else block_count[block])
        print("    * {}".format(block))
        vfile += BLOCK_TMPL.format(blockname=block,
                                   blockparameters=format_param_str(params["parameters"]),
                                   instname=instname,
                                   n=i,
                                   clock=params["clock"],
                                   extraports=format_port_str(params["extraports"]))
    if fill_with_fifos:
        vfile += FILL_FIFO_TMPL.format(fifo_start=len(blocks))
    return vfile

def file_generator(args, vfile):
    """
    Takes the target device as an argument and, if no '-o' directive is given,
    replaces the auto_ce file in the corresponding top folder. With the
    presence of -o, it just generates a version of the verilog file which
    is  not intended to be build
    """
    fpga_utils_path = get_scriptpath()
    print("Adding CE instantiation file for '%s'" % args.target)
    path_to_file = fpga_utils_path +'/../../top/' + device_dict(args.device.lower()) +\
            '/rfnoc_ce_auto_inst_' + args.device.lower() + '.v'
    if args.outfile is None:
        open(path_to_file, 'w').write(vfile)
    else:
        open(args.outfile, 'w').write(vfile)

def append_re_line_sequence(filename, linepattern, newline):
    """ Detects the re 'linepattern' in the file. After its last occurrence,
    paste 'newline'. If the pattern does not exist, append the new line
    to the file. Then, write. If the newline already exists, leaves the file
    unchanged"""
    oldfile = open(filename, 'r').read()
    lines = re.findall(newline, oldfile, flags=re.MULTILINE)
    if len(lines) != 0:
        pass
    else:
        pattern_lines = re.findall(linepattern, oldfile, flags=re.MULTILINE)
        if len(pattern_lines) == 0:
            open(filename, 'a').write(newline)
            return
        last_line = pattern_lines[-1]
        newfile = oldfile.replace(last_line, last_line + newline + '\n')
        open(filename, 'w').write(newfile)

def create_oot_include(device, include_dirs):
    """
    Create the include file for OOT RFNoC sources
    """
    oot_dir_list = []
    target_dir = device_dict(device.lower())
    dest_srcs_file = os.path.join(get_scriptpath(), '..', '..', 'top',\
            target_dir, 'Makefile.OOT.inc')
    incfile = open(dest_srcs_file, 'w')
    incfile.write(OOT_SRCS_FILE_HDR)
    if include_dirs is not None:
        for dirs in include_dirs:
            currpath = os.path.abspath(str(dirs))
            if os.path.isdir(currpath) & (os.path.basename(currpath) == "rfnoc"):
                # Case 1: Pointed directly to rfnoc directory
                oot_path = currpath
            elif os.path.isdir(os.path.join(currpath, 'rfnoc')):
                # Case 2: Pointed to top level rfnoc module directory
                oot_path = os.path.join(currpath, 'rfnoc')
            elif os.path.isfile(os.path.join(currpath, 'Makefile.inc')):
                # Case 3: Pointed to a random directory with a Makefile.inc
                oot_path = currpath
            else:
                print('No RFNoC module found at ' + os.path.abspath(currpath))
                continue
            if oot_path not in oot_dir_list:
                oot_dir_list.append(oot_path)
                named_path = os.path.join('$(BASE_DIR)', get_relative_path(get_basedir(), oot_path))
                incfile.write(OOT_DIR_TMPL.format(oot_dir=named_path))
                if os.path.isfile(os.path.join(oot_path, 'Makefile.inc')):
                    # Check for Makefile.inc
                    incfile.write(OOT_INC_TMPL)
                elif os.path.isfile(os.path.join(oot_path, 'rfnoc', 'Makefile.inc')):
                    # Check for Makefile.inc
                    incfile.write(OOT_INC_TMPL)
                elif os.path.isfile(os.path.join(oot_path, 'rfnoc', 'fpga-src', 'Makefile.srcs')):
                    # Legacy: Check for fpga-src/Makefile.srcs
                    # Read, then append to file
                    curr_srcs = open(os.path.join(oot_path, 'rfnoc', 'fpga-src', 'Makefile.srcs'), 'r').read()
                    curr_srcs = curr_srcs.replace('SOURCES_PATH', os.path.join(oot_path, 'rfnoc', 'fpga-src', ''))
                    incfile.write(OOT_SRCS_TMPL.format(sources=curr_srcs))
                else:
                    print('No valid makefile found at ' + os.path.abspath(currpath))
                    continue
    incfile.close()

def append_item_into_file(device, include_dir):
    """
    Basically the same as append_re_line_sequence function, but it does not
    append anything when the input is not found
    ---
    Detects the re 'linepattern' in the file. After its last occurrence,
    pastes the input string. If pattern doesn't exist
    notifies and leaves the file unchanged
    """
    def get_oot_srcs_list(include_dir):
        """
        Pull the OOT sources out of the Makefile.srcs
        """
        oot_srcs_file = os.path.join(include_dir, 'Makefile.srcs')
        oot_srcs_list = readfile(oot_srcs_file)
        return [w.replace('SOURCES_PATH', include_dir) for w in oot_srcs_list]
    # Here we go
    target_dir = device_dict(device.lower())
    if include_dir is not None:
        for directory in include_dir:
            dirs = os.path.join(directory, '')
            checkdir_v(dirs)
            dest_srcs_file = os.path.join(get_scriptpath(), '..', '..', 'top',\
                    target_dir, 'Makefile.srcs')
            oot_srcs_list = get_oot_srcs_list(dirs)
            dest_srcs_list = readfile(dest_srcs_file)
            prefixpattern = re.escape('$(addprefix ' + dirs + ', \\\n')
            linepattern = re.escape('RFNOC_OOT_SRCS = \\\n')
            oldfile = open(dest_srcs_file, 'r').read()
            prefixlines = re.findall(prefixpattern, oldfile, flags=re.MULTILINE)
            if len(prefixlines) == 0:
                lines = re.findall(linepattern, oldfile, flags=re.MULTILINE)
                if len(lines) == 0:
                    print("Pattern {} not found. Could not write `{}'"
                          .format(linepattern, oldfile))
                    return
                else:
                    last_line = lines[-1]
                    srcs = "".join(oot_srcs_list)
            else:
                last_line = prefixlines[-1]
                srcs = "".join([
                    item
                    for item in oot_srcs_list
                    if item not in dest_srcs_list
                ])
            newfile = oldfile.replace(last_line, last_line + srcs)
            open(dest_srcs_file, 'w').write(newfile)

def compare(file1, file2):
    """
    compares two files line by line, and returns the lines of first file that
    were not found on the second. The returned is a tuple item that can be
    accessed in the form of a list as tuple[0], where each line takes a
    position on the list or in a string as tuple [1].
    """
    notinside = []
    with open(file1, 'r') as arg1:
        with open(file2, 'r') as arg2:
            text1 = arg1.readlines()
            text2 = arg2.readlines()
            for item in text1:
                if item not in text2:
                    notinside.append(item)
    return notinside

def readfile(files):
    """
    compares two files line by line, and returns the lines of first file that
    were not found on the second. The returned is a tuple item that can be
    accessed in the form of a list as tuple[0], where each line takes a
    position on the list or in a string as tuple [1].
    """
    contents = []
    with open(files, 'r') as arg:
        text = arg.readlines()
        for item in text:
            contents.append(item)
    return contents

def build(args):
    " build "
    cwd = get_scriptpath()
    target_dir = device_dict(args.device.lower())
    build_dir = os.path.join(cwd, '..', '..', 'top', target_dir)
    if os.path.isdir(build_dir):
        print("changing temporarily working directory to {0}".\
                format(build_dir))
        os.chdir(build_dir)
        make_cmd = ". ./setupenv.sh "
        if args.clean_all:
            make_cmd = make_cmd + "&& make cleanall "
        make_cmd = make_cmd + "&& make " + dtarget(args)
        if args.GUI:
            make_cmd = make_cmd + " GUI=1"
        # Wrap it into a bash call:
        make_cmd = '/bin/bash -c "{0}"'.format(make_cmd)
        ret_val = os.system(make_cmd)
        os.chdir(cwd)
    return ret_val

def device_dict(args):
    """
    helps selecting the device building folder based on the targeted device
    """
    build_dir = {
        'x300':'x300',
        'x310':'x300',
        'e300':'e31x',
        'e310':'e31x',
        'e320':'e320',
        'n300':'n3xx',
        'n310':'n3xx',
        'n320':'n3xx'
    }
    return build_dir[args]

def dtarget(args):
    """
    If no target specified,  selects the default building target based on the
    targeted device
    """
    if args.target is None:
        default_trgt = {
            'x300':'X300_RFNOC_HG',
            'x310':'X310_RFNOC_HG',
            'e310':'E310_SG3_RFNOC',
            'e320':'E320_RFNOC_1G',
            'n300':'N300_RFNOC_HG',
            'n310':'N310_RFNOC_HG',
            'n320':'N320_RFNOC_XG',
        }
        return default_trgt[args.device.lower()]
    else:
        return args.target

def checkdir_v(include_dir):
    """
    Checks the existance of verilog files in the given include dir
    """
    nfiles = glob.glob(os.path.join(include_dir,'')+'*.v')
    if len(nfiles) == 0:
        print('[ERROR] No verilog files found in the given directory')
        exit(0)
    else:
        print('Verilog sources found!')
    return

def get_scriptpath():
    """
    returns the absolute path where a script is located
    """
    return os.path.dirname(os.path.realpath(__file__))

def get_basedir():
    """
    returns the base directory (BASE_DIR) used in rfnoc build process
    """
    return os.path.abspath(os.path.join(get_scriptpath(), '..', '..', 'top'))

def get_relative_path(base, target):
    """
    Find the relative path (including going "up" directories) from base to target
    """
    basedir = os.path.abspath(base)
    prefix = os.path.commonprefix([basedir, os.path.abspath(target)])
    path_tail = os.path.relpath(os.path.abspath(target), prefix)
    total_path = path_tail
    if prefix != "":
        while basedir != os.path.abspath(prefix):
            basedir = os.path.dirname(basedir)
            total_path = os.path.join('..', total_path)
        return total_path
    else:
        print("Could not determine relative path")
        return path_tail

def main():
    " Go, go, go! "
    args = setup_parser().parse_args()
    if args.yml:
        print("Using yml file. Ignoring command line blocks arguments")
        blocks, params = parse_yml(args.yml)
    else:
        blocks = args.blocks
        params = [get_default_parameters()]*len(blocks)
    if args.auto_inst_src is None:
        vfile = create_auto_inst(blocks, params, args.max_num_blocks, args.fill_with_fifos)
    else:
        vfile = open(args.auto_inst_src, 'r').read()
    file_generator(args, vfile)
    create_oot_include(args.device, args.include_dir)
    if args.outfile is  None:
        return build(args)
    else:
        print("Instantiation file generated at {}".\
                format(args.outfile))
        return 0

if __name__ == "__main__":
    exit(main())
