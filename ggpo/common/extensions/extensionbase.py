from PyQt4 import QtCore
from extensionconstants import *

class ExtensionBase(QtCore.QObject):
    """ Base class for extension client component.

    This class is the base class for all extensions. An extension module must contain one main class deriving from
    ExtensionBase.  This class will be instantitated once after logging right after the main window is created.

    ExtensionBase provides access to application events (Qt signals) that may be hooked into to receive notification
    about application activities such as the user changing rooms or other players changing their status.  Access to UI
    elements can be done through the cls.ggpowindow member, which contains a handle to the main application window, and
    chatMessage can be used to display text strings in the chat box.

    The methods sendMessage and receiveMessage are used to communicate with the server component of the extension.

    A derived class must override hide() and recieveMessage().
    """

    @classmethod
    def Initialize(cls, extID, extensionIO):
        """Pre-instantiation setup.  Do not override."""

        cls.__extIO = extensionIO
        cls.extID = extID                           # Identification number of the extension.
        cls.title = cls.__name__                    # Title of the extension.  By default the name of the class.
        cls.ggpowindow = cls.__extIO.ggpowindow     # handle to the main window
        cls.controller = cls.__extIO.controller     # handle to the controller

        cls.ChannelJoined = cls.__extIO.ChannelJoined           # controller.sigChannelJoined
        cls.PlayerStateChange = cls.__extIO.PlayerStateChange   # controller.sigPlayerStateChange
        cls.MatchStarting = cls.__extIO.MatchStarting           # controller.sigMatchStarting
        cls.Disconnected = cls.__extIO.Disconnected             # controller.sigServerDisconnected
        cls.MotdReceived = cls.__extIO.MotdReceived             # controller.sigMotdReceived

    def __init__(self):
        QtCore.QObject.__init__(self)

    @classmethod
    def hide(cls):
        """Hides all UI elements belonging to this extension.

        Must override if extension has UI components that are visible by default.
        """
        pass

    def receiveMessage(self, prefix, params):
        """Process a message sent to us by the server half of the extension

        Must override if extension needs to receive communication from the server.

        WARNING: The second parameter has been json packed and unpacked en route, which may change the object in certain
                 circumstances.  For example, tuples will arrive as lists, and dictionaries will arrive with all keys
                 converted to strings.

        Args:
            prefix: Extension-defined positive integer
            params: Python object
        """
        pass

    @classmethod
    def sendMessage(cls, prefix, params=None):
        """Send a message to the server extension instance associated with your channel

        WARNING: The second parameter will be json packed and unpacked en route, which may change the object in certain
                 circumstances.  For example, tuples will arrive as lists, and dictionaries will arrive with all keys
                 converted to strings.

        Args:
            prefix: An extension-defined positive integer.
            params: A json serializable python object
        """
        cls.__extIO.sendMessage(cls.extID, prefix, params)

    @classmethod
    def chatMessage(cls, msg):
        """ Display the string msg in chat.  Uses ggpowindow.appendChat. """
        cls.__extIO.chatMessage(msg)

    @classmethod
    def saveSetting(cls, key, val):
        """Store an object in the application settings file.

        Args:
            key: A string used for future retrieval.
            val: A picklable python object

        """
        cls.__extIO.saveSetting(cls.extID, key, val)

    @classmethod
    def loadSetting(cls, key):
        """Retrieve an object stored by saveSetting.

        Args:
            key: A string previously used in saveSetting

        Returns:
            object stored with the passed key if available, or None if not found

        """
        return cls.__extIO.loadSetting(cls.extID, key)

    def advancedMonitoringAvailable(self):
        """ Returns True/False according to whether we are in a channel configured for live monitoring of game events. """

        return self.controller.channel in self.__extIO.gameVariableData

    @classmethod
    def buildAnchorString(cls, key, linktext):
        """Format a clickable link to display in chat.

        Args:
            key: a string
            linktext: the displayed text to be hotlinked

        Returns: A string of the form "<a href=...>linkText</a>" which can be inserted into a chat message.  When clicked,
                    the value of key will be passed to receiveChatCommand() on the server.

        """

        return "<a href=extension:%s,%s>%s</a>" % (cls.extID, key, linktext)
