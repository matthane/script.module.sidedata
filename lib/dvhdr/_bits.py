# MSB-first bitstream reader shared by the RPU and HDR10+ parsers. Mirrors the
# bit-reader semantics of bitvec_helpers (BigEndian, standard Exp-Golomb) so
# the field-by-field parse below matches the reference bitstream layouts.


class BitReader:
    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.nbits = len(data) * 8

    def bits_left(self):
        return self.nbits - self.pos

    def read_bit(self):
        if self.pos >= self.nbits:
            raise EOFError('out of bits')
        byte = self.data[self.pos >> 3]
        bit = (byte >> (7 - (self.pos & 7))) & 1
        self.pos += 1
        return bit

    def read_bits(self, n):
        if n <= 0:
            return 0
        if n > self.bits_left():
            raise EOFError('out of bits')
        v = 0
        for _ in range(n):
            v = (v << 1) | self.read_bit()
        return v

    def read_ue(self):
        leading = 0
        while self.read_bit() == 0:
            leading += 1
            if leading > 62:
                raise ValueError('ue(v) leading zero run too long')
        if leading == 0:
            return 0
        return self.read_bits(leading) + (1 << leading) - 1

    def read_se(self):
        code_num = self.read_ue()
        m = (code_num + 1) // 2
        return -m if code_num % 2 == 0 else m

    def byte_aligned(self):
        return self.pos % 8 == 0

    def align(self):
        while not self.byte_aligned():
            self.read_bit()

    def skip_bits(self, n):
        if n < 0 or n > self.bits_left():
            raise EOFError('out of bits')
        self.pos += n
