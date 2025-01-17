#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path

class AssemblerConfig:
    def __init__(self, description):
        parser = argparse.ArgumentParser(description=description)

        parser.add_argument("filename",
                            default="",
                            help="input source file")
        parser.add_argument("-o",
                            "--outfile",
                            help="output file, {programName}.OUT is default if -o not specified")
        parser.add_argument("-s",
                            "--symtab",
                            action="store_true",
                            help="save symbol table to file")
        parser.add_argument("-d",
                            "--debug",
                            action="store_true",
                            help="print extra debugging information")
        args = parser.parse_args()

        self.filename: str = args.filename
        self.outfile: str = args.outfile
        self.symtab: bool = args.symtab
        self.debug: bool = args.debug

class Assembler(object):
    line_number, pass_number, address = 0, 1, 0
    output = b""
    debug_mode = False
    ORIGIN = 0x4000

    # the tokens per line
    label, mnemonic, op1, op2, comment = "", "", "", "", ""
    op1_type, op2_type, comment = "", "", ""
    symbol_table = {}

    registers = ("a", "b", "c", "d", "ip", "sp", "bp")
    
    def __init__(self):
        start_time = time.time()
        description = "LLAMA-16 Assembler"
        args = AssemblerConfig(description)
        self.debug_mode = args.debug
        
        self.assemble(line for line in open(Path(args.filename))) # Pass 1
        self.assemble(line for line in open(Path(args.filename))) # Pass 2

        # Process outfile and symfile in one line each
        outfile = Path(args.outfile or args.filename).with_suffix('.OUT')
        symfile = outfile.with_suffix(".SYM") if args.symab else None

        bytes_written = self.write_binary_file(outfile, self.output)
        symbol_count = symfile and self.write_symbol_file(symfile, self.symbol_table)

        if self.debug_mode:
            print(f"Writing {bytes_written} bytes to {Path(outfile)}")
            print(f"Writing {symbol_count} symbols to {Path(symfile)}"*bool(symfile))
            print(f"--- Finished in {(time.time() - start_time):.4f} seconds ---")

    def write_binary_file(self, filename: Path, binary_data: bytearray) -> int:
        with open(filename, "wb") as file:
            if self.debug_mode:
                print(f'DEBUG binary output: {binary_data}')
            file.write(binary_data)
        return len(binary_data)

    def write_symbol_file(self, filename, table):
        symbol_count = len(table)
        if not symbol_count:
            return symbol_count

        with open(filename, "w", encoding="utf-8") as file:
            for symbol in table:
                print(f"{table[symbol]:04X} {symbol[:16].upper()}", file=file)

        return symbol_count

    def assemble(self, lines):
        self.pass_number = 1 if not hasattr(self, 'pass_number') else self.pass_number+1
        
        [
            self._assemble_line(line)
            for line in lines
        ]

        if self.debug_mode:
            print(f'Parsed {self.line_number} lines on pass {self.pass_number}')
        
    def _assemble_line(self, line: str):
        """Assembly function for each line (parse -> process)"""
        self.parse(line)
        self.process()
        self.line_number += 1

    def parse(self, line: str):
        """Parse and tokenize line of source code."""
        # Based on this algorithm from Brian Robert Callahan:
        # https://briancallahan.net/blog/20210410.html
        self.label, self.mnemonic, self.comment = "", "", ""
        self.op1, self.op1_type, self.op2, self.op2_type = "", "", "", ""

        preprocess = line.lstrip()  # remove leading whitespace
        preprocess = preprocess.translate({9: 32})  # replace tabs with spaces

        # Comments
        comment_left, comment_separator, comment_right = preprocess.rpartition(";")
        if comment_separator:
            self.comment = comment_right.strip()
        else:
            # If no comment, then the third argument is the remainder of the line
            # Strip whitespace as before
            comment_left = comment_right.rstrip()

        d_label, directive, d_args = self.parse_directive(comment_left)
        if directive:
            self.label = d_label.lower()
            self.mnemonic = directive.lower()
            self.op1 = d_args.lower()
            self.op1_type = directive.split('.')[0] # drop the .

            if self.debug_mode:
                print(f'Label: {self.label}\nMnemonic: {self.mnemonic}\nOp1: {self.op1}\nOp1 Type: {self.op1_type}\n'
                      f'Op2: {self.op2}\nOp2 Type: {self.op2_type}\nComment: {self.comment}\n')

        # Second operand
        op2_left, op2_separator, op2_right = comment_left.rpartition(",")
        if op2_separator:
            self.op2 = op2_right.strip()
        else:
            op2_left = op2_right.rstrip()

        # First operand
        op1_left, op1_separator, op1_right = op2_left.rpartition("\t")
        if op1_separator == "\t":
            self.op1 = op1_right.strip()
        else:
            op1_left, op1_separator, op1_right = op2_left.rpartition(" ")
            if op1_separator == " ":
                self.op1 = op1_right.strip()
            else:
                op1_left = op1_right.strip()

        # mnemonic from label
        mnemonic_left, mnemonic_separator, mnemonic_right = op1_left.rpartition(":")
        if mnemonic_separator:
            self.mnemonic = mnemonic_right.strip()
            self.label = mnemonic_left.strip()
        else:
            mnemonic_left = mnemonic_right.rstrip()
            self.mnemonic = mnemonic_left.strip()

        # Fix when mnemonic ends up as first operand
        if self.mnemonic == "" and self.op1 != "" and self.op2 == "":
            self.mnemonic = self.op1.strip()
            self.op1 = ""

        self.op1 = self.op1.lower()

        if self.op1:
            if self.op1.startswith("["):
                self.op1_type = "mem_adr"
                self.op1 = self.op1.translate({91: None, 93: None})  # Remove brackets
            elif self.op1.startswith("#"):
                self.op1_type = "imm"
                self.op1 = self.op1.translate({35: None})  # Remove number sign
            elif self.op1 in self.registers[0:4]:
                self.op1_type = "reg"
                self.op1
            else:
                self.op1_type = "label"
                self.label = self.label.lower()

        self.op2 = self.op2.lower()

        if self.op2:
            if self.op2.startswith("["):
                self.op2_type = "mem_adr"
                self.op2 = self.op2.translate({91: None, 93: None})  # Remove brackets
            elif self.op2.startswith("#"):
                self.op2_type = "imm"
                self.op2 = self.op2.translate({35: None})  # Remove number sign
            elif self.op2.lower() in self.registers:
                self.op2_type = "reg"
                self.op2.lower()
            else:
                self.op2_type = "label"
                self.label = self.label.lower()

        self.mnemonic = self.mnemonic.lower()
        if self.debug_mode:
            print(f'Label: {self.label}\nMnemonic: {self.mnemonic}\nOp1: {self.op1}\nOp1 Type: {self.op1_type}\n'
                  f'Op2: {self.op2}\nOp2 Type: {self.op2_type}\nComment: {self.comment}\n')


    def parse_directive(self, line: str):
        d_label, directive, d_args = "", "", ""
        left1, sep1, right1 = line.partition(".data")
        d_type = ".data"
        if not sep1:
            left1, sep1, right1 = line.partition(".string")
            d_type = ".string"
        if not sep1:
            return d_label, directive, d_args

        directive = d_type
        d_args = right1.strip()

        left2, sep2, right2 = left1.partition(":")
        if sep2 == ":":
            left2 = left2.strip()
            if not left2.isalnum() or left2[0].isdigit():
                self.write_error(f'Invalid label "{left2}"')
            d_label = left2
        elif sep2 != ":" and left2.strip() != "":
            self.write_error(f'Invalid label "{left2}"')

        return d_label, directive, d_args

    def process(self):
        if not self.mnemonic and not (self.op1 and self.op2):
            return
        
        # Internal mnemonic format
        mnemonic = f"_{self.mnemonic}".replace("_.", "directive_")
        
        if not hasattr(self, mnemonic):
            self.write_error(f'Unrecognized mnemonic "{self.mnemonic}"')

        getattr(self, mnemonic)()

    def _mv(self):
        self.verify_ops(self.op1 and self.op2)
        # 0x00 = 0
        opcode = 0
        opcode = self.encode_operand_types(opcode, 2)

        self.pass_action(2, opcode.to_bytes(2, byteorder="little"))
        self.immediate_operand()
        self.memory_address()

    def _io(self):
        self.verify_ops(self.op1 and self.op2)
        if self.op1_type == 'imm' and (self.op2 == 'in'):
            self.write_error("Cannot read word into an immediate.")
        # 0x01 = 1
        opcode = 1
        # encode just the data type, IN/OUT will be encoding next
        opcode = self.encode_operand_types(opcode, 1)
        if self.op2.lower() == 'in':
            opcode += 0x1
        elif self.op2.lower() == 'out':
            opcode += 0x2
        else:
            self.write_error(f"Error parsing io port. {self.op2} is not a valid port, use IN or OUT.")

        self.pass_action(2, opcode.to_bytes(2, byteorder="little"))
        self.immediate_operand()
        self.memory_address()

    def _push(self):
        self.verify_ops(self.op1 and not self.op2)
        # 0x02 = 2
        opcode = 2
        opcode = self.encode_operand_types(opcode, 1)

        self.pass_action(2, opcode.to_bytes(2, byteorder="little"))
        self.immediate_operand()
        self.memory_address()

    def _pop(self):
        self.verify_ops(self.op1 and not self.op2)
        # 0x03 = 3
        opcode = 3
        opcode = self.encode_operand_types(opcode, 1)

        self.pass_action(2, opcode.to_bytes(2, byteorder="little"))
        self.memory_address()

    def _add(self):
        self.verify_ops(self.op1 and self.op2)
        # 0x04 = 4
        opcode = 4
        opcode = self.encode_operand_types(opcode, 2)
        self.pass_action(2, opcode.to_bytes(2, byteorder="little"))
        self.immediate_operand()
        self.memory_address()

    def _sub(self):
        self.verify_ops(self.op1 and self.op2)
        # 0x05 = 5
        opcode = 5
        opcode = self.encode_operand_types(opcode, 2)
        self.pass_action(2, opcode.to_bytes(2, byteorder="little"))
        self.immediate_operand()
        self.memory_address()

    def _inc(self):
        self.verify_ops(self.op1 and not self.op2)
        # 0x06 = 6
        opcode = 6
        opcode = self.encode_operand_types(opcode, 1)
        self.pass_action(2, opcode.to_bytes(2, byteorder="little"))

    def _dec(self):
        self.verify_ops(self.op1 and not self.op2)
        # 0x07 = 7
        opcode = 7
        opcode = self.encode_operand_types(opcode, 1)
        self.pass_action(2, opcode.to_bytes(2, byteorder="little"))

    def _and(self):
        self.verify_ops(self.op1 and self.op2)
        # 0x08 = 8
        opcode = 8
        opcode = self.encode_operand_types(opcode, 2)
        self.pass_action(2, opcode.to_bytes(2, byteorder="little"))
        self.immediate_operand()
        self.memory_address()

    def _or(self):
        self.verify_ops(self.op1 and self.op2)
        # 0x08 = 9
        opcode = 9
        opcode = self.encode_operand_types(opcode, 2)
        self.pass_action(2, opcode.to_bytes(2, byteorder="little"))
        self.immediate_operand()
        self.memory_address()

    def _not(self):
        self.verify_ops(self.op1 and self.op2)
        # 0x0A = 10
        opcode = 10
        opcode = self.encode_operand_types(opcode, 2)
        self.pass_action(2, opcode.to_bytes(2, byteorder="little"))
        self.immediate_operand()
        self.memory_address()

    def _cmp(self):
        self.verify_ops(self.op1 and self.op2)
        # 0x0B = 11
        opcode = 11
        opcode = self.encode_operand_types(opcode, 2)
        self.pass_action(2, opcode.to_bytes(2, byteorder="little"))
        self.immediate_operand()
        self.memory_address()

    def _call(self):
        self.verify_ops(self.op1 and not self.op2)
        # 0x0C = 12
        opcode = 12
        opcode = self.encode_operand_types(opcode, 1)
        self.pass_action(2, opcode.to_bytes(2, byteorder="little"))
        self.immediate_operand()

    def _jnz(self):
        self.verify_ops(self.op1 and not self.op2)
        # 0x0D = 13
        opcode = 13
        opcode = self.encode_operand_types(opcode, 1)
        self.pass_action(2, opcode.to_bytes(2, byteorder="little"))
        self.immediate_operand()

    def _ret(self):
        self.verify_ops(not (self.op1 or self.op2))
        # 0x0E = 14
        self.pass_action(2, b"\x00\xE0")

    def _hlt(self):
        self.verify_ops(not (self.op1 or self.op2))
        # 0x0F = 15
        self.pass_action(2, b"\x00\xF0")

    def directive_data(self):
        if self.label == "":
            self.write_error(".data and .string directives must be labeled")
        self.verify_ops(self.op1 and not self.op2)

        try:
            data = int(self.op1)
            self.pass_action(2, data.to_bytes(2, byteorder="little", signed=True))
        except ValueError:
            self.write_error(f"Error reading \"{self.op1}\", not an integer")

    def directive_string(self):
        if self.label == "":
            self.write_error(".data and .string directives must be labeled")
        self.verify_ops(self.op1 and not self.op2)

        string = self.op1
        string = string.strip('\"').strip('\'')
        if len(string) % 2 != 0:
            string += '\0'
        else:
            string += '\0\0'
        data = bytes(string, encoding='utf-8')
        self.pass_action(len(data), data)

    def encode_operand_types(self, opcode, num_ops) -> int:
        opcode <<= 12
        
        # num_ops == 1, match op1 type
        match (self.op1_type, num_ops):
            case "imm", 1:
                opcode += (14 << 4)
                
            case "reg":
                opcode += (self.register_offset(self.op1) << 4)
            
            case "mem_adr" | "label", 1:
                opcode += (15 << 4)
                if self.debug_mode:
                    print(f"DEBUG: Symbol table: {self.symbol_table}")
            
            case "", 1:
                pass
            
            case _, 1:
                self.write_error(f'Invalid operand "{self.op1}"')
        
        # num_ops == 2, match op2 type
        match (self.op2_type, num_ops):
            case "reg", 2:
                opcode += (self.register_offset(self.op2))
            
            case "mem_adr" | "label", 2:
                opcode += (15 << 4)
                if self.debug_mode:
                    print(f"DEBUG: Symbol table: {self.symbol_table}")
            
            case "", 2:
                pass
            
            case _, 2:
                self.write_error(f'Invalid operand "{self.op2}"')
        
        return opcode
    
    def immediate_operand(self):
        if self.op1_type not in ("imm", "label") or self.pass_number == 1:
            return
        
        self.address += 1
        number = self.to_int(self.op1) or self.get_label(self.op1)
        self.pass_action(2, number.to_bytes(2, byteorder="little", signed=True))
        
    
    def memory_address(self):
        if self.pass_number == 1 or not any(op == 'mem_adr' for op in (self.op1_type, self.op2_type)):
            return
        
        self.address += 1

        for op_typ, op in zip((self.op1_type, self.op2_type), (self.op1, self.op2)):
            if op_typ != 'mem_adr':
                continue

            number = self.to_int(op) or self.get_label(op)
            number = int(number, 16)
            self.pass_action(2, number.to_bytes(2, byteorder="little"))

    def register_offset(self, reg_in: str) -> int:
        reg = reg_in.lower()
        if reg not in self.registers:
            self.write_error(f'Invalid register "{reg}"')
        return self.registers.index(reg)

    def verify_ops(self, valid):
        if not valid:
            self.write_error(f'Invalid operands for mnemonic "{self.mnemonic}"')

    def write_error(self, message):
        print(f"Assembly error on line {self.line_number + 1}: {message}")
        if self.debug_mode:
            print(f"DEBUG: Current address: {self.address}\nDEBUG: Current symbol table: {self.symbol_table}")
        sys.exit(1)

    def pass_action(self, size, output_byte):
        """On pass 1: build symbol table. On pass 2: generate code.

        Args:
            size: Number of bytes in the instruction
            output_byte: Opcode, empty binary is no output generated
        """
        if not output_byte:
            return

        if self.pass_number == 1:
            align = size % 2
            if self.label:
                self.add_label()
            self.address += int(size/2) + align

        self.output += output_byte

    def add_label(self):
        """Add label to symbol table."""
        symbol = self.label.lower()
        if symbol in self.symbol_table:
            self.write_error(f'Duplicate label: "{self.label}"')
        self.symbol_table[symbol] = self.address + self.ORIGIN

    def get_label(self, label: str) -> int:
        if label.lower() in self.symbol_table:
            return int(self.symbol_table[label])
        self.write_error(f'Undefined label "{label}"')

    def to_int(self, val: str) -> int | None:
        if val.isdigit() or val.startswith('-'):
            return int(val)
        return None

if __name__ == "__main__":
    assembler = Assembler()
