# Copyright 1996-2019 Cyberbotics Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# References:
# - http://paulbourke.net/dataformats/pic/
# - https://github.com/plepers/hdr2png/blob/master/hdrloader.cpp
# - https://github.com/enkimute/hdrpng.js/blob/master/hdrpng.js

import math
import re
import struct
from clamp import clamp_int

GAMMA = 2.0


class HDR:
    @classmethod
    def load_from_file(cls, filename):
        """Parse the HDR file."""
        # HDR Format Specifications: http://paulbourke.net/dataformats/pic/
        #
        # Typical header:
        #     #?RADIANCE
        #     SOFTWARE=gegl 0.4.12
        #     FORMAT=32-bit_rle_rgbe
        #
        #     -Y 1024 +X 2048
        #     Data
        hdr = HDR()
        data = []
        header = False
        with open(filename, "rb") as f:
            line = True
            while line:
                line = f.readline()

                # Case: Empty lines
                if line == '' or (len(line) == 1 and ord(line[0]) == 10):
                    continue
                # Case: header
                m = re.match(r'^#\?RADIANCE$', line)
                if m:
                    header = True
                    continue
                # Case: Size
                m = re.match(r'^(.)(.)\s(\d+)\s(.)(.)\s(\d+)$', line)
                if m:
                    hdr.rotated = m.group(2) == 'X'
                    hdr.xFlipped = m.group(1 if hdr.rotated else 4) == '-'
                    hdr.yFlipped = m.group(4 if hdr.rotated else 1) == '+'
                    hdr.width = int(m.group(6))
                    hdr.height = int(m.group(3))
                    continue
                # Case: ignored header entries
                if line.startswith('FORMAT=') or \
                        line.startswith('EXPOSURE=') or \
                        line.startswith('COLORCORR=') or \
                        line.startswith('SOFTWARE=') or \
                        line.startswith('PIXASPECT=') or \
                        line.startswith('VIEW=') or \
                        line.startswith('PRIMARIES=') or \
                        line.startswith('GAMMA=') or \
                        line.startswith('# '):
                    continue
                break
            # Case: Data
            data = line + f.read()
        assert header, 'Invalid header.'
        assert 4 * hdr.width * hdr.height == len(data) and len(data) > 0, 'Invalid dimensions.'
        assert not (hdr.rotated or hdr.xFlipped or hdr.yFlipped), 'Flip or rotation flags are not supported.'

        # Convert data to floats
        hdr.data = [0.0] * (3 * hdr.width * hdr.height)
        for i in range(hdr.width * hdr.height):
            r = float(ord(data[4 * i]))
            g = float(ord(data[4 * i + 1]))
            b = float(ord(data[4 * i + 2]))
            e = pow(2.0, float(ord(data[4 * i + 3])) - 128.0 + 8.0)
            hdr.data[3 * i] = pow(r * e, 1.0 / GAMMA) / 255.0
            hdr.data[3 * i + 1] = pow(g * e, 1.0 / GAMMA) / 255.0
            hdr.data[3 * i + 2] = pow(b * e, 1.0 / GAMMA) / 255.0

        return hdr

    @classmethod
    def create_black_image(cls, width, height):
        """Create an HDR black image."""
        hdr = HDR()
        hdr.width = width
        hdr.height = height
        hdr.data = [0.0] * (3 * hdr.width * hdr.height)
        return hdr

    def __init__(self):
        """Constructor: simply reset the fields. Prefer the static methods."""
        self.data = []  # Contains the 1D array of floats (size: 3*w*h, black: 0.0, white: 1.0, hdr: >1.0)
        self.width = -1
        self.height = -1

        self.xFlipped = False
        self.yFlipped = False
        self.rotated = False

    def is_valid(self):
        """Return True if the image has been loaded correctly."""
        return 3 * self.width * self.height == len(self.data)

    def get_pixel(self, x, y):
        """Get pixel at the speficied position."""
        assert x >= 0 and x < self.width
        assert y >= 0 and y < self.height
        i = 3 * (y * self.width + x)
        return (
            self.data[i],
            self.data[i + 1],
            self.data[i + 2]
        )

    def set_pixel(self, x, y, pixel):
        """Set pixel at the speficied position."""
        assert x >= 0 and x < self.width
        assert y >= 0 and y < self.height
        i = 3 * (y * self.width + x)
        self.data[i] = pixel[0]
        self.data[i + 1] = pixel[1]
        self.data[i + 2] = pixel[2]

    def save(self, filename):
        """Save the image to a file."""
        assert self.is_valid()
        assert filename.endswith('.hdr')
        assert not (self.rotated or self.xFlipped or self.yFlipped), 'Flip or rotation flags are not supported.'

        with open(filename, "w") as f:
            f.write('#?RADIANCE\n')
            f.write('FORMAT=32-bit_rle_rgbe\n')
            f.write('\n')
            f.write('-Y %d +X %d\n' % (self.height, self.width))
            for i in range(self.width * self.height):
                r = pow(self.data[3 * i], GAMMA)
                g = pow(self.data[3 * i + 1], GAMMA)
                b = pow(self.data[3 * i + 2], GAMMA)
                v = max(r, g, b)
                e = math.ceil(math.log(v, 2)) if v != 0.0 else 0.0
                s = pow(2, e - 8)
                bytes = [
                    clamp_int(r / s, 0, 255),
                    clamp_int(g / s, 0, 255),
                    clamp_int(b / s, 0, 255),
                    clamp_int(e + 128, 0, 255)
                ]
                f.write(struct.pack("BBBB", *bytearray(bytes)))

    def to_pil(self):
        """Create a PIL image to test the script."""
        assert self.is_valid()
        from PIL import Image
        im = Image.new('RGB', (self.width, self.height))
        pixels = im.load()
        for y in range(self.height):
            for x in range(self.width):
                i = 3 * (y * self.width + x)
                r = clamp_int(255.0 * self.data[i], 0, 255)
                g = clamp_int(255.0 * self.data[i + 1], 0, 255)
                b = clamp_int(255.0 * self.data[i + 2], 0, 255)
                pixels[x, y] = (r, g, b)
        return im
