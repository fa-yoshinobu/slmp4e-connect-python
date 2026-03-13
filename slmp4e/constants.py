"""SLMP 4E binary constants and command/device definitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum

FRAME_4E_REQUEST_SUBHEADER = b"\x54\x00"
FRAME_4E_RESPONSE_SUBHEADER = b"\xD4\x00"


class PLCSeries(str, Enum):
    """Series option for subcommand compatibility."""

    QL = "ql"  # MELSEC-Q/L compatible (0000/0001)
    IQR = "iqr"  # MELSEC iQ-R/iQ-L (0002/0003)


class Command(IntEnum):
    """Command list from SH080956ENGN 5.1."""

    # Device
    DEVICE_READ = 0x0401
    DEVICE_WRITE = 0x1401
    DEVICE_READ_RANDOM = 0x0403
    DEVICE_WRITE_RANDOM = 0x1402
    DEVICE_ENTRY_MONITOR = 0x0801
    DEVICE_EXECUTE_MONITOR = 0x0802
    DEVICE_READ_BLOCK = 0x0406
    DEVICE_WRITE_BLOCK = 0x1406

    # Label
    LABEL_ARRAY_READ = 0x041A
    LABEL_ARRAY_WRITE = 0x141A
    LABEL_READ_RANDOM = 0x041C
    LABEL_WRITE_RANDOM = 0x141B

    # Memory / Extend unit
    MEMORY_READ = 0x0613
    MEMORY_WRITE = 0x1613
    EXTEND_UNIT_READ = 0x0601
    EXTEND_UNIT_WRITE = 0x1601

    # Remote control
    REMOTE_RUN = 0x1001
    REMOTE_STOP = 0x1002
    REMOTE_PAUSE = 0x1003
    REMOTE_LATCH_CLEAR = 0x1005
    REMOTE_RESET = 0x1006
    READ_TYPE_NAME = 0x0101

    # Remote password
    REMOTE_PASSWORD_LOCK = 0x1631
    REMOTE_PASSWORD_UNLOCK = 0x1630

    # File control
    FILE_READ_DIRECTORY = 0x1810
    FILE_SEARCH_DIRECTORY = 0x1811
    FILE_NEW = 0x1820
    FILE_DELETE = 0x1822
    FILE_COPY = 0x1824
    FILE_CHANGE_STATE = 0x1825
    FILE_CHANGE_DATE = 0x1826
    FILE_OPEN = 0x1827
    FILE_READ = 0x1828
    FILE_WRITE = 0x1829
    FILE_CLOSE = 0x182A

    # Other
    SELF_TEST = 0x0619
    CLEAR_ERROR = 0x1617
    ONDEMAND = 0x2101


SUBCOMMAND_DEVICE_WORD_QL = 0x0000
SUBCOMMAND_DEVICE_BIT_QL = 0x0001
SUBCOMMAND_DEVICE_WORD_IQR = 0x0002
SUBCOMMAND_DEVICE_BIT_IQR = 0x0003

SUBCOMMAND_DEVICE_WORD_QL_EXT = 0x0080
SUBCOMMAND_DEVICE_BIT_QL_EXT = 0x0081
SUBCOMMAND_DEVICE_WORD_IQR_EXT = 0x0082
SUBCOMMAND_DEVICE_BIT_IQR_EXT = 0x0083

# Direct memory specification (binary, Appendix 1)
DIRECT_MEMORY_NORMAL = 0x00
DIRECT_MEMORY_MODULE_ACCESS = 0xF8
DIRECT_MEMORY_LINK_DIRECT = 0xF9
DIRECT_MEMORY_CPU_BUFFER = 0xFA


@dataclass(frozen=True)
class DeviceCode:
    """Device code and number radix."""

    code: int
    radix: int  # 10 or 16


# Device codes from SH080956ENGN 5.2 (binary code column).
DEVICE_CODES: dict[str, DeviceCode] = {
    "SM": DeviceCode(0x0091, 10),
    "SD": DeviceCode(0x00A9, 10),
    "X": DeviceCode(0x009C, 16),
    "Y": DeviceCode(0x009D, 16),
    "M": DeviceCode(0x0090, 10),
    "L": DeviceCode(0x0092, 10),
    "F": DeviceCode(0x0093, 10),
    "V": DeviceCode(0x0094, 10),
    "B": DeviceCode(0x00A0, 16),
    "D": DeviceCode(0x00A8, 10),
    "W": DeviceCode(0x00B4, 16),
    "TS": DeviceCode(0x00C1, 10),
    "TC": DeviceCode(0x00C0, 10),
    "TN": DeviceCode(0x00C2, 10),
    "LTS": DeviceCode(0x0051, 10),
    "LTC": DeviceCode(0x0050, 10),
    "LTN": DeviceCode(0x0052, 10),
    "STS": DeviceCode(0x00C7, 10),
    "STC": DeviceCode(0x00C6, 10),
    "STN": DeviceCode(0x00C8, 10),
    "LSTS": DeviceCode(0x0059, 10),
    "LSTC": DeviceCode(0x0058, 10),
    "LSTN": DeviceCode(0x005A, 10),
    "CS": DeviceCode(0x00C4, 10),
    "CC": DeviceCode(0x00C3, 10),
    "CN": DeviceCode(0x00C5, 10),
    "LCS": DeviceCode(0x0055, 10),
    "LCC": DeviceCode(0x0054, 10),
    "LCN": DeviceCode(0x0056, 10),
    "SB": DeviceCode(0x00A1, 16),
    "SW": DeviceCode(0x00B5, 16),
    "S": DeviceCode(0x0098, 10),
    "DX": DeviceCode(0x00A2, 16),
    "DY": DeviceCode(0x00A3, 16),
    "Z": DeviceCode(0x00CC, 10),
    "LZ": DeviceCode(0x0062, 10),
    "R": DeviceCode(0x00AF, 10),
    "ZR": DeviceCode(0x00B0, 10),
    "RD": DeviceCode(0x002C, 10),
    # Appendix 1 extension device codes
    "G": DeviceCode(0x00AB, 10),  # module access device (engineering-tool form: U\\G, e.g. U4\\G0)
    "HG": DeviceCode(0x002E, 10),  # fixed-cycle area of CPU buffer memory
}
