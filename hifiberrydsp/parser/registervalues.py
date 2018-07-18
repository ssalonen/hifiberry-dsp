'''
Copyright (c) 2018 Modul 9/HiFiBerry

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

from collections import Iterable

import logging

from hifiberrydsp.filtering.volume import percent2amplification, \
    decibel2amplification
from hifiberrydsp.filtering.biquad import Biquad
from hifiberrydsp.parser.xmlprofile import XmlProfile
from hifiberrydsp.hardware.adau145x import Adau145x
from hifiberrydsp.datatools import int_data, parse_int


class RegisterFile():

    def __init__(self, filename, fs=48000, dsp=Adau145x()):
        self.values = {}
        self.fs = fs
        self.dsp = dsp
        with open(filename) as settingsfile:
            for line in settingsfile:
                if len(line.strip()) == 0 or line.startswith("#"):
                    continue

                try:
                    (attrib, value) = line.split(":", maxsplit=1)
                except:
                    logging.error("can't parse line %s", line)
                    continue

                attrib = attrib.strip()
                if attrib.lower().startswith("iir"):
                    value = self.parse_biquad(value)
                else:
                    value = self.parse_value(value.strip())
                self.values[attrib] = value

    def parse_value(self, value):
        if value.endswith("%"):
            percent = int(value[0:-1])
            return percent2amplification(percent)
        elif value.lower().endswith("db"):
            db = int(value[0:-2])
            return decibel2amplification(db)
        elif "." in value:
            return float(value)
        elif value.startswith("0x"):
            return int(value, 16)
        else:
            return int(value)

    def parse_biquad(self, value):
        filters = value.split(",")
        result = []
        for f in filters:
            try:
                filter = Biquad.create_filter(f, self.fs)
            except Exception as e:
                filter = None

            if filter == None:
                logging.error("can't parse filter definition %s", f)
            else:
                result.append(filter)
        return result

    def update_xml_profile(self, xmlprofile):

        replace = {}

        for attribute in self.values:
            val = self.values[attribute]
            addr = xmlprofile.get_meta(attribute)
            if addr is None:
                logging.error(
                    "control name %s not defined in XML profile, ignoring", attribute)
                continue

            if "/" in addr:
                (addr, length) = addr.split("/")
            else:
                length = "1"

            addr = parse_int(addr)
            length = parse_int(length)
            memory = self.param_to_bytes(val, length)

            if len(memory) <= self.dsp.WORD_LENGTH:
                replace[addr] = memory
            else:
                # Split long replaced into single words
                assert len(memory) % self.dsp.WORD_LENGTH == 0

                while len(memory) > 0:
                    cellvalue = memory[0:self.dsp.WORD_LENGTH]
                    replace[addr] = cellvalue
                    addr += 1
                    memory = memory[self.dsp.WORD_LENGTH:]

        xmlprofile.replace_eeprom_cells(replace)
        xmlprofile.replace_ram_cells(replace)

    def param_to_bytes(self, value, max_length=1, ignore_limit=False):
        if isinstance(value, float):
            value = self.dsp.decimal_repr(value)
            res = int_data(value, self.dsp.WORD_LENGTH)
        elif isinstance(value, int):
            res = int_data(value, self.dsp.WORD_LENGTH)
        elif isinstance(value, Biquad):
            res = []
            bqn = value.normalized()
            vals = []
            vals.append(-bqn.a1)
            vals.append(-bqn.a2)
            vals.append(bqn.b0)
            vals.append(bqn.b1)
            vals.append(bqn.b2)
            for v in vals:
                dec = self.dsp.decimal_repr(v)
                res = res + list(int_data(dec, self.dsp.WORD_LENGTH))

        elif isinstance(value, Iterable):
            res = []
            for part in value:
                res = res + self.param_to_bytes(part, 0, ignore_limit=True)
        else:
            raise RuntimeError("parameter type not implemented: %s",
                               type(value).__name__)

        # Fill with zeros
        while len(res) < max_length * self.dsp.WORD_LENGTH:
            res.append(0)

        if not(ignore_limit) and len(res) > (max_length * self.dsp.WORD_LENGTH):
            logging.error("parameter set too long (%s bytes), won't fit into %s words",
                          len(res),
                          max_length * self.dsp.WORD_LENGTH)
            res = None

        return res


def demo():
    xml = XmlProfile("sample_files/xml/4way-iir.xml")
    xml.write_xml("/tmp/x.xml")
    fs = xml.samplerate()
    rf = RegisterFile("sample_files/simple-settings.txt", fs)
    print(rf.values)
    rf.update_xml_profile(xml)
    print("writing y.xml")
    xml.write_xml("/tmp/y.xml")
    rf = RegisterFile("sample_files/settings.txt", fs)
    print(rf.values)
    rf.update_xml_profile(xml)
    print("writing z.xml")
    xml.write_xml("/tmp/z.xml")
