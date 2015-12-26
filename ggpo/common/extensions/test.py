from PyQt4 import QtCore
import json
import threading
import ctypes
import struct
import time
from ggpo.common.protocol import Protocol
from ggpo.common.settings import Settings
from ggpo.common.runtime import IS_WINDOWS
from extensionconstants import *

_READ_LOOP_DELAY = 1
_gamehwnd = None
_hProcess = None

gameVariableData = dict()
gameVariableData['sfiii3n'] = (
                                [0x78, 0x00, 0x79, 0x00, 0x76, 0x00],
                                [
                                    (-0x60AA0,4), #frame number
#                                    (0x8E2,1),    #win streak player 1
#                                    (0x8E0,1),    #win streak player 2
                                    (-0x51CC6,1), #win streak player 1
                                    (-0x51CC8,1), #win streak player 2
                                    (-0x57620,1), #rounds won this game player 1
                                    (-0x5761A,1), #rounds won this game player 2
                                    (-0x5762C,1), #timer
                                    (0x368,1),    #health player 1 (out of 160)
                                    (0x800,1),    #health player 2 (out of 160)
                                ]
                             )


def sendMessage(extID, prefix, params=None):
    print prefix, params

def _monitorCurrentMatch():
    """ The server has requested we monitor the match currently being played and return data.  Calcualte addresses
    for game variables, then read them and relay them to the server periodically, or tell the server that we're
    unable to do so.

    This will be called after the two players have succesfully connected and the emulation has actually begun.
    """

#    sendMessage(1, _Message.MatchEvent, (MatchEvent.CalibrationFail,))

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.py_object))
    EnumWindows = ctypes.windll.user32.EnumWindows
    EnumWindows.argtypes = [EnumWindowsProc, ctypes.POINTER(ctypes.py_object)]
    EnumWindows.restype = ctypes.c_long

    data = ctypes.create_string_buffer(256)  # buffer to use for various things

    """ Identify the window in which the game is taking place by the presence of the "X (p1) vs. Y (p2)" string that's
        displayed in the upper left.

        Ideally we'd be able to simply take the process ID from the Popen object created when opening FBA.  Unfortunately
        the emulator window winds up living in a different descendant process that's very difficult to figure out from
        the original.  So instead, simply loop through all desktop windows and find the FBA window with the "X (p1) vs. Y (p2)"
        string somewhere in its memory.
    """

    # The "X (p1) vs Y (p2)" string displayed in the game window.
#    nameString = "{d[1]} (p1) vs {d[2]} (p2)".format(d = {    self._controller.side: self._controller.username,
#                                                          3 - self._controller.side: self._controller.playingagainst})
    # DEBUG
    nameString = "sfiii3n"

    # noinspection PyUnusedLocal
    def ewp(hwnd, lparam):
        """ callback for EnumWindowsProc.  Checks if the passed window is an FBA window and scans for nameString if it is. """
        ctypes.windll.user32.GetWindowTextA(hwnd, data, 255)

        if data.value.find("FB Alpha") != -1:
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            # 0x410 = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
            # PROCESS_QUERY_INFORMATION needed for VirtualQueryEx, PROCESS_VM_READ needed for ReadProcessMemory
            # https://msdn.microsoft.com/en-us/library/windows/desktop/ms684320%28v=vs.85%29.aspx
            hProcess = ctypes.windll.kernel32.OpenProcess(0x410, False, pid)

            if _scanProcessMemoryForString(hProcess, nameString) >= 0:
                global _gamehwnd, _hProcess
                _gamehwnd = hwnd
                _hProcess = hProcess
                return False

        return True

    if EnumWindows(EnumWindowsProc(ewp), None):  # True = bad, False = good
        sendMessage(1, _Message.MatchEvent, (MatchEvent.CalibrationFail,))
        return

    """ self._hProcess now contains the process handle for the game.  Attempt to find the sequence of bytes identifying
        our calibration point inside the process' memory and use it to calculate the absolute addresses of our game
        variables
    """

    calibArray, variableData = gameVariableData["sfiii3n"]

    base = _scanProcessMemoryForString(_hProcess, "".join([chr(i) for i in calibArray]))

    if base < 0:
        sendMessage(1, _Message.MatchEvent, (MatchEvent.CalibrationFail,))
        return

    pointers = [(addr + base, sz) for (addr, sz) in variableData]
    sendMessage(1, _Message.MatchEvent, (MatchEvent.CalibrationSuccess,))  # :D

    """ Pointers to game variables are now valid.  Read them in a loop and send the info to the server until the
        emulator is closed.
    """

    bytesRead = ctypes.c_size_t()
    values = None
    formatStrings = [None, "<B", "<H", None, "<L"]  # for struct.unpack

    while ctypes.windll.user32.IsWindow(_gamehwnd):
        lvalues = values
        values = []

        readSuccess = True
        try:
            for addr, sz in pointers:
                rc = ctypes.windll.kernel32.ReadProcessMemory(_hProcess, addr, data, sz, ctypes.byref(bytesRead))
                if rc == 0 or bytesRead.value != sz:
                    readSuccess = False
                    break
                else:
#                       values.append(sum([ord(data[i]) << 8*i for i in range(sz)]))
                    values.append(struct.unpack(formatStrings[sz], data[:sz])[0])
        except Exception as e:
            # DEBUG
            print e
            raise

            readSuccess = False

        if readSuccess:
            if lvalues == None:
                lvalues = values  # first loop only

            if lvalues[1:] != values[1:]:  # first value is always frame number.  Don't send if only that has changed.
                sendMessage(0, _Message.MatchData, values)

            if values[0] < lvalues[0]:  # frame number decreased, so reset was pressed
                sendMessage(0, _Message.MatchEvent, (MatchEvent.ResetPressed,))
        else:
            values = lvalues

        time.sleep(_READ_LOOP_DELAY)


# noinspection PyMethodMayBeStatic
def _scanProcessMemoryForString(hProcess, searchString):
    """ Scans the process specified by hProcess for the string searchString.

    The technique used here is adapted from various posts on the Cheat Engine forum.  I assume there are equivalents
    for other operating systems, but I wouldn't know where to start (and don't have the setup to test anyway).

    Args:
        hProcess: Windows process handle
        searchString: string to find

    Returns:
        Integer offset of searchString in the process' memory if found, -1 otherwise.

    """

    si, mbi, bytesRead = _SYSTEM_INFO(), _MEMORY_BASIC_INFORMATION(), ctypes.c_size_t()

    VirtualQueryEx = ctypes.windll.kernel32.VirtualQueryEx
    VirtualQueryEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_MEMORY_BASIC_INFORMATION), ctypes.c_size_t]

    GetSystemInfo = ctypes.windll.kernel32.GetSystemInfo
    GetSystemInfo.argtypes = [ctypes.POINTER(_SYSTEM_INFO)]

    GetSystemInfo(ctypes.byref(si))
    min_address = si.lpMinimumApplicationAddress
    max_address = si.lpMaximumApplicationAddress

    # Cycle through process' memory pages and try to find our string
    while min_address < max_address:
        # Get address and size of next memory region
        # https://msdn.microsoft.com/en-us/library/windows/desktop/aa366907%28v=vs.85%29.aspx
        if VirtualQueryEx(hProcess, min_address, ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
            break

        if mbi.RegionSize == 0:
            break

        # Only search regions that have actually been allocated and which we have access to
        # https://msdn.microsoft.com/en-us/library/windows/desktop/aa366775%28v=vs.85%29.aspx
        if mbi.State == 0x1000 and mbi.Protect == 4:
            data = ctypes.create_string_buffer(mbi.RegionSize)
            ctypes.windll.kernel32.ReadProcessMemory(hProcess, mbi.BaseAddress, data, mbi.RegionSize, ctypes.byref(bytesRead))

            pos = data.raw.find(searchString)

            if pos != -1:
                return mbi.BaseAddress + pos

        # Set pointer to beginning of next region
        min_address += mbi.RegionSize

    return -1



""" Structures to use with VirtualQueryEx and GetSystemInfo """

class _SYSTEM_INFO_struct(ctypes.Structure):
    _fields_ = [("wProcessorArchitecture", ctypes.c_ushort), ("wReserved", ctypes.c_ushort)]

class _SYSTEM_INFO_union(ctypes.Union):
    _fields_ = [("dwOemId", ctypes.c_ulong), ("", _SYSTEM_INFO_struct)]

class _SYSTEM_INFO(ctypes.Structure):
    _fields_ = [
        ("", _SYSTEM_INFO_union),
        ("dwPageSize", ctypes.c_ulong),
        ("lpMinimumApplicationAddress", ctypes.c_void_p),
        ("lpMaximumApplicationAddress", ctypes.c_void_p),
        ("dwActiveProcessorMask", ctypes.c_void_p),
        ("dwNumberOfProcessors", ctypes.c_ulong),
        ("dwProcessorType", ctypes.c_ulong),
        ("dwAllocationGranularity", ctypes.c_ulong),
        ("wProcessorLevel", ctypes.c_ushort),
        ("wProcessorRevision", ctypes.c_ushort)]

class _MEMORY_BASIC_INFORMATION (ctypes.Structure):
    _fields_ = [
        ("BaseAddress",  ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", ctypes.c_ulong),
        ("RegionSize", ctypes.c_size_t),
        ("State", ctypes.c_ulong),
        ("Protect", ctypes.c_ulong),
        ("Type", ctypes.c_ulong)]

# noinspection PyClassHasNoInit
class _Message:
    # client to server
    InitializationDataRequest = 1
    ExtensionNotFound = 2
    AnchorClicked = 3
    ChatCommand = 4
    MatchEvent = 5
    MatchData = 6

    # server to client
    InitializationDataResponse = 101
    ChatMessage = 102
    KillEmulator = 103
    BeginMonitoring = 104






_monitorCurrentMatch()
