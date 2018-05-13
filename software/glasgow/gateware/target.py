import os
import sys
import tempfile
import shutil
from migen import *

from .platform import Platform
from .i2c import I2CSlave
from .registers import Registers
from .fx2 import FX2Arbiter


__all__ = ["GlasgowTarget"]


class _CRG(Module):
    def __init__(self, platform):
        clk_if = platform.request("clk_if")

        self.clock_domains.cd_por = ClockDomain(reset_less=True)
        self.clock_domains.cd_sys = ClockDomain()
        self.specials += [
            Instance("SB_GB_IO",
                i_PACKAGE_PIN=clk_if,
                o_GLOBAL_BUFFER_OUTPUT=self.cd_por.clk),
        ]

        reset_delay = Signal(max=2047, reset=2047)
        self.comb += [
            self.cd_sys.clk.eq(self.cd_por.clk),
            self.cd_sys.rst.eq(reset_delay != 0)
        ]
        self.sync.por += [
            If(reset_delay != 0,
                reset_delay.eq(reset_delay - 1)
            )
        ]


class GlasgowTarget(Module):
    def __init__(self, out_count=0, in_count=0, fifo_depth=511, reg_count=0):
        self.platform = Platform()

        self.submodules.crg = _CRG(self.platform)

        self.submodules.i2c_slave = I2CSlave(self.platform.request("i2c"))
        self.comb += self.i2c_slave.address.eq(0b0001000)

        if reg_count > 0:
            self.submodules.registers = Registers(self.i2c_slave, reg_count)

        self.submodules.arbiter = FX2Arbiter(self.platform.request("fx2"),
                                             out_count=out_count,
                                             in_count=in_count,
                                             depth=fifo_depth)

        self.sync_port = self.platform.request("sync")
        self.io_ports = [self.platform.request("io") for _ in range(2)]

    def build(self, **kwargs):
        self.platform.build(self, **kwargs)

    def get_verilog(self, **kwargs):
        return self.platform.get_verilog(self)

    def get_bitstream(self, build_dir=None, debug=False, **kwargs):
        if build_dir is None:
            build_dir = tempfile.mkdtemp(prefix="glasgow_")
        try:
            self.build(build_dir=build_dir)
            with open(os.path.join(build_dir, "top.bin"), "rb") as f:
                bitstream = f.read()
            if debug:
                shutil.rmtree(build_dir)
        except:
            if debug:
                print("Keeping build tree as " + build_dir, file=sys.stderr)
            raise
        finally:
            if not debug:
                shutil.rmtree(build_dir)
        return bitstream

    @staticmethod
    def _port_spec_to_number(spec):
        if spec == "A":
            return 0
        if spec == "B":
            return 1
        raise ValueError("Unknown I/O port {}".format(spec))

    def get_io_port(self, spec):
        """Return an I/O port ``spec``."""
        num = self._port_spec_to_number(spec)
        return self.io_ports[num]

    def get_out_fifo(self, spec):
        """Return an OUT FIFO for I/O port ``spec``."""
        num = self._port_spec_to_number(spec)
        return self.arbiter.out_fifos[num]

    def get_in_fifo(self, spec):
        """Return an IN FIFO for I/O port ``spec``."""
        num = self._port_spec_to_number(spec)
        return self.arbiter.in_fifos[num]

    def get_inout_fifo(self, spec):
        """Return an (IN, OUT) FIFO pair for I/O port ``spec``."""
        num = self._port_spec_to_number(spec)
        return (self.arbiter.in_fifos[num], self.arbiter.out_fifos[num])
