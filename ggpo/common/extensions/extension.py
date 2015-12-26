""" Extension.py - Hub for all extension-related communications.

    The Extension object created here contains the client-side code to pass extension messages between server and client
    extension objects, and serves as the interface to the fightcade application itself.  The main Fightcade code interacts
    with extensions by emitting signals from the controller and by feeding server messages to the parseMessage() method.

    Exposed objects:
        Extension - Object to receive information from fightcade code.
"""

from PyQt4 import QtCore
import json
import threading
import ctypes
import struct
import time
import importlib
from ggpo.common.protocol import Protocol
from ggpo.common.settings import Settings
from ggpo.common.runtime import IS_WINDOWS
from extensionconstants import *
from tournaments import Tournaments
from kingofthehill import KingOfTheHill
from quickmatch import QuickMatch

# Dict of extensions with unique identifiers.
#       Individual extensions may be disabled universally by removing them from this list and restarting the server.  When this
#       is done none of the extension's server or client code will run and their UI will not display in any client.
_ExtensionDict = {
                          # ID 0 is reserved
                          1: Tournaments,
                          2: KingOfTheHill,
                          3: QuickMatch,
                       }

_READ_LOOP_DELAY = 1  # time between memory scans, in seconds.
                      # Once a second should be adequate and not cause any lag

class _Extension(QtCore.QObject):
    """ Provides methods for extension-related communication and handles all interaction with the Fightcade code itself.

        Signals:
            ChannelJoined() (controller.sigChannelJoined)
            MotdReceived(channel, topic, msg) (controller.sigMotdReceived)
            PlayerStateChange(name, state) (controller.sigPlayerStateChange)
            MatchStarting(opponent, playernum) (controller.sigMatchStarting)
            Disconnected() (controller.sigServerDisconnected)

        Exposed Methods:
            setWindow(ggpowindow)
                Provide the window handle to our code.

            parseMessage(data)
                Parse and dispatch an extension message received from the server.

            processAnchorClick(data)
                Handles clicks on text anchors placed by extensions

            tryParseCommand(cmd, args)
                Handles chat commands.
    """

    _sigInstantiate = QtCore.pyqtSignal(list)
    _evtInstantiationFinished = threading.Event()
    _sigChatMessage = QtCore.pyqtSignal(str)

    def __init__(self):
        QtCore.QObject.__init__(self)

        self.controller = None
        self.ggpowindow = None

        self.ChannelJoined = None
        self.MotdReceived = None
        self.PlayerStateChange = None
        self.MatchStarting = None
        self.Disconnected = None
        self.referee = None
        self.chatMessage = None

        self.gameVariableData = None                    # copy of the GameVariableData dict from the server
        self._hProcess = None                           # handle to the emulator process
        self._gamehwnd = None                           # handle to the emulator window
        self._monitorThread = None

        self._instanceDict = {}
        self._commandDict = {}
        self._codeToString = {}

    def Initialize(self, ggpowindow):
        """ Prepare for startup and request initialization data from server. """
        self.ggpowindow = ggpowindow
        self.controller = self.ggpowindow.controller

        self.moveToThread(self.ggpowindow.thread())

        # aliases for some controller variables
        self.PlayerStateChange = self.controller.sigPlayerStateChange
#        self.MatchStarting = self.controller.sigMatchStarting
        self.Disconnected = self.controller.sigServerDisconnected
        self.ChannelJoined = self.controller.sigChannelJoined
#        self.MotdReceived = self.controller.sigMotdReceived

        self._sigChatMessage.connect(self.ggpowindow.appendChat)
        self.chatMessage = self._sigChatMessage.emit

        # make a dictionary translating message codes to message names just to make the logs easier to follow
        self._codeToString = {(0, val):nm for nm, val in _Message.__dict__.iteritems() if nm[0] != "_"}

        # Tell each extension what it's ID# is and where the communication functions are, then hide its UI
        for extID, ext in _ExtensionDict.iteritems():
            try:
                messageEnum = importlib.import_module(ext.__module__).Message
                self._codeToString.update({(extID, val):nm for nm, val in messageEnum.__dict__.iteritems() if nm[0] != "_"})
            except:
                pass

            ext.Initialize(extID=extID, extensionIO=self)
            ext.hide()

        self._sigInstantiate.connect(self._instantiate)
        self.sendMessage(0, _Message.InitializationDataRequest)  # request referee data and the list of available extensions from the server


    def _instantiate(self, extIDs):
        """ Instantiate extensions that the server says are available.

        Args:
            extIDs: list of IDs for extensions running on server

        """
        self._instanceDict = {extID: _ExtensionDict[extID]() for extID in extIDs if extID in _ExtensionDict}
        self._evtInstantiationFinished.set()  # Done!

    def parseMessage(self, data):
        """ Decode and route a message received from server

        Message is encoded as follows:
            byte 0-3 - positive integer, 0 for internal messages, 1 for referee messages, otherwise the extension ID of
                       the extension to receive the message.
            byte 4-7 - extension-defined positive integer
            byte 8+ - json-packed python object parameter

        Args:
            data: Encoded message data
        """

        cmd, data = Protocol.extractTLV(data)
        extID, cmd = Protocol.extractInt(cmd)
        prefix, cmd = Protocol.extractInt(cmd)
        params = None if cmd == '' else json.loads(cmd)

        # DEBUG
        dispext = "Extension" if extID == 0 else _ExtensionDict[extID].__name__
        dispprefix = self._codeToString.get((extID, prefix), prefix)
        self.controller.sigStatusMessage.emit("Ext Rcv: ext=%s, prefix=%s, params=%s" % (dispext, dispprefix, params))

        if extID == 0:
            # internal message

            if prefix == _Message.InitializationDataResponse:
                # initialization data received from server

#                self.referee = ExtensionReferee(gamedata=params[1], extensionIO=self)
                self.gameVariableData = params[1]
                self._commandDict = {("/"+chatcommand): extID for chatcommand, extID in params[2]}
                self._sigInstantiate.emit(params[0])
                self._evtInstantiationFinished.wait()  # Block message loop until extensions are initialized
                                                       # If it hangs here, the __init__() in some extension is freezing

            elif prefix == _Message.ChatMessage:
                self.chatMessage(params)

            elif prefix == _Message.KillEmulator:
                self.controller.killEmulator()

            elif prefix == _Message.BeginMonitoring:
                if self._monitorThread != None and self._monitorThread.is_alive():
                    return

                self._monitorThread = threading.Thread(target=self._monitorCurrentMatch)
                self._monitorThread.daemon = True
                self._monitorThread.start()

        elif extID in self._instanceDict:
            # message for another extension
            if extID in self._instanceDict:
                self._instanceDict[extID].receiveMessage(prefix, params)

    def sendMessage(self, extID, prefix, params=None):
        """ Encode a message and send it to the server

        Args:
            extID: positive integer.  0 for internal messages, 1 for referee messages, otherwise is an extension ID
            prefix: extension-defined positive integer
            params: json-serializable python object
        """
        data = Protocol.packInt(extID) + Protocol.packInt(prefix) + json.dumps(params)
        self.controller.sendAndRemember(Protocol.EXTENSION_OUTBOUND, Protocol.packTLV(data))

        # DEBUG
        dispext = "Extension" if extID == 0 else _ExtensionDict[extID].__name__
        dispprefix = self._codeToString.get((extID, prefix), prefix)
        self.controller.sigStatusMessage.emit("Ext Snd: ext=%s, prefix=%s, params=%s" % (dispext, dispprefix, params))

    def tryParseCommand(self, command, args):
        """ Application got a chat command it didn't recognize.  See if it's one of ours and relay to the server if it is

        Args:
            command: string, the chat command.
            args: the arguments as a list of strings

        Returns:
            True/False according to whether the passed command was recognized

        """
        if command in self._commandDict:
            self.sendMessage(0, _Message.ChatCommand, [self._commandDict[command], args])
            return True

        return False

    # noinspection PyMethodMayBeStatic
    def saveSetting(self, extID, key, val):
        """ Store an object in the application settings file.

        Args:
            extID: ID of the calling extension
            key: string key.  Needs only to be unique within the extension
            val: picklable object
        """
        Settings.setPythonValue("EXT%s%s" % (extID, key), val)

    # noinspection PyMethodMayBeStatic
    def loadSetting(self, extID, key):
        """ Retrieves an object stored by saveSetting

        Args:
            extID: ID of calling extension
            key: string key previously passed to saveSetting

        Returns:
            The object previously stored, or None if not found
        """
        return Settings.pythonValue("EXT%s%s" % (extID, key))

    def processAnchorClick(self, data):
        """ A text anchor that we previously constructed with buildAnchorString has been clicked.  Relay to the server.

        Args:
            data: string consisting of the extension ID, then a comma, then the string previously passed to buildAnchorString
        """
        try:
            idstr, arg = data.split(",", 1)
            self.sendMessage(0, _Message.AnchorClicked, [int(idstr), arg])
        except:
            pass

    """ Routines to scan emulator memory for game data to pass to server """

    def _monitorCurrentMatch(self):
        """ The server has requested we monitor the match currently being played and return data.  Calcualte addresses
        for game variables, then read them and relay them to the server periodically, or tell the server that we're
        unable to do so.

        This will be called after the two players have succesfully connected and the emulation has actually begun.
        """

        if not (IS_WINDOWS and self._controller.channel in self.gameVariableData):
            self.sendMessage(1, _Message.MatchEvent, (MatchEvent.CalibrationFail,))
            return

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
        nameString = "{d[1]} (p1) vs {d[2]} (p2)".format(d = {    self._controller.side: self._controller.username,
                                                              3 - self._controller.side: self._controller.playingagainst})
#        # DEBUG
#        nameString = "sfiii3n"

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

                if self._scanProcessMemoryForString(hProcess, nameString) >= 0:
                    self._gamehwnd = hwnd
                    self._hProcess = hProcess
                    return False

            return True

        if EnumWindows(EnumWindowsProc(ewp), None):  # True = bad, False = good
            self.sendMessage(1, _Message.MatchEvent, (MatchEvent.CalibrationFail,))
            return

        """ self._hProcess now contains the process handle for the game.  Attempt to find the sequence of bytes identifying
            our calibration point inside the process' memory and use it to calculate the absolute addresses of our game
            variables
        """

        calibArray, variableData = self.gameVariableData[self._controller.channel]

        base = self._scanProcessMemoryForString(self._hProcess, "".join([chr(i) for i in calibArray]))

        if base < 0:
            self.sendMessage(1, _Message.MatchEvent, (MatchEvent.CalibrationFail,))
            return

        pointers = [(addr + base, sz) for (addr, sz) in variableData]
        self.sendMessage(1, _Message.MatchEvent, (MatchEvent.CalibrationSuccess,))  # :D

        """ Pointers to game variables are now valid.  Read them in a loop and send the info to the server until the
            emulator is closed.
        """

        bytesRead = ctypes.c_size_t()
        values = None
        formatStrings = [None, "<B", "<H", None, "<L"]  # for struct.unpack

        while ctypes.windll.user32.IsWindow(self._gamehwnd) and self._controller.playingagainst != '':
            lvalues = values
            values = []

            readSuccess = True
            try:
                for addr, sz in pointers:
                    rc = ctypes.windll.kernel32.ReadProcessMemory(self._hProcess, addr, data, sz, ctypes.byref(bytesRead))
                    if rc == 0 or bytesRead.value != sz:
                        readSuccess = False
                        break
                    else:
#                       values.append(sum([ord(data[i]) << 8*i for i in range(sz)]))
                        values.append(struct.unpack(formatStrings[sz], data[:sz])[0])
            except Exception as e:
#                # DEBUG
#                print e
#                raise

                readSuccess = False

            if readSuccess:
                if lvalues == None:
                    lvalues = values  # first loop only

                if lvalues[1:] != values[1:]:  # first value is always frame number.  Don't send if only that has changed.
                    self.sendMessage(0, _Message.MatchData, values)

                if values[0] < lvalues[0]:  # frame number decreased, so reset was pressed
                    self.sendMessage(0, _Message.MatchEvent, (MatchEvent.ResetPressed,))
            else:
                values = lvalues

            time.sleep(_READ_LOOP_DELAY)


    # noinspection PyMethodMayBeStatic
    def _scanProcessMemoryForString(self, hProcess, searchString):
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


Extension = _Extension()  # Need an actual instance instead of a static class so we can use Qt signals.


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
