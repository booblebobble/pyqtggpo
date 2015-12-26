
from extensionbase import *
import threading
import time

downarrow = unichr(0x25BC)
rightarrow = unichr(0x25B6)


class QuickMatch(ExtensionBase):

    # map from slider positions to corresponding ping data
    pingDict = [(50, "Best (<50ms)"),
                (100, "Better (<100ms)"),
                (150, "Good (<150ms)"),
                (200, "OK (<200ms)"),
                (0, "Any")]

    @classmethod
    def hide(cls):
        cls.ggpowindow.uiFrmRanked.setVisible(False)

    def __init__(self):
        ExtensionBase.__init__(self)

        self.opened = False

        self.state = 0  # 0 - not searching, 1 - searching
        self.searchPool = set()  # list of other users currently searching for opponents
        self.maxping = -1
        self.requestsSent = set()  # list of players we've already requested matches with

        self.onValueChanged(self.ggpowindow.uiRnkSliderPing.value())

        self.ChannelJoined.connect(self.onChannelJoined)
        self.PlayerStateChange.connect(self.onPlayerStateChange)
        self.Disconnected.connect(self.onDisconnected)

        self.ggpowindow.uiBtnRankedOpen.clicked.connect(self.toggleFoldout)
        self.ggpowindow.uiBtnRankedFindMatch.clicked.connect(self.findMatchClicked)
        self.ggpowindow.uiRnkSliderPing.valueChanged.connect(self.onValueChanged)

        thd = threading.Thread(target=self.checkSearchPoolLoop)
        thd.daemon = True
        thd.start()

    def onDisconnected(self):
        # stop searching if we get DC'd
        self.state = 0

    def onValueChanged(self, idx):
        self.maxping = self.pingDict[idx][0]
        self.ggpowindow.uiRnkLblPing.setText(self.pingDict[idx][1])

        if self.state == 1:
            self.sendMessage(Message.ResetRequests)
            self.requestsSent = set()
            self.checkSearchPool()

    def toggleFoldout(self):
        self.opened = not self.opened
        self.ggpowindow.uiSwRanked.setVisible(self.opened)
        self.ggpowindow.uiBtnRankedOpen.setText((downarrow if self.opened else rightarrow) + " Quick Match")

    def receiveMessage(self, prefix, params):
        if prefix == Message.SearchPoolAdd:
            self.searchPool |= set(params)
            self.checkSearchPool()

        elif prefix == Message.SearchPoolRemove:
            self.requestsSent -= set(params)
            self.searchPool -= set(params)

        elif prefix == Message.MatchStarting:
             self.onChannelJoined()

        elif prefix == Message.MatchEnding:
            self.state = 0
            self.ggpowindow.uiSwRanked.setCurrentIndex(0)
            self.ggpowindow.uiBtnRankedFindMatch.setText("Find Opponent")

            if params:
                self.chatMessage("A Winner Is You \o/")
            else:
                self.chatMessage("WOW! YOU LOSE!")

    def findMatchClicked(self):
        if self.controller.username not in self.controller.available:
            self.chatMessage("You must be set to available to use this!")
            return

        if self.state == 0:
            self.sendMessage(Message.StartSearch)
            self.state = 1
            self.searchPool = set([])
            self.requestsSent = set()
            self.ggpowindow.uiBtnRankedFindMatch.setText("Searching... Press to cancel.")
        else:
            self.sendMessage(Message.CancelSearch)
            self.state = 0
            self.searchPool = set([])
            self.ggpowindow.uiBtnRankedFindMatch.setText("Find Opponent")

    def checkSearchPoolLoop(self):
        while True:
            if self.state == 1:
                self.checkSearchPool()
            time.sleep(3)

    def checkSearchPool(self):
        try:
            validOpps = [name for name in self.searchPool - self.requestsSent if
                                         self.maxping == 0 or
                                             (name in self.controller.players and
                                             self.controller.players[name].ping != '' and
                                             self.controller.players[name].ping < self.maxping)]
            if len(validOpps) > 0:
                self.requestsSent |= set(validOpps)
                self.sendMessage(Message.RequestMatch, validOpps)
        except KeyError:
            # someone left and we weren't notified.  Shouldn't happen?
            self.searchPool = {nm for nm in self.searchPool if nm in self.controller.players}
            # we'll be called again in 3 seconds, so don't bother retrying here

    def onChannelJoined(self):
        if not self.controller.isRomAvailable(self.controller.channel) or self.controller.channel == "lobby":
            self.hide()
        else:
            self.state = 0
            self.searchPool = set([])

            self.opened = True  # call to toggleFoldout will reset 'opened' to false
            self.toggleFoldout()

            self.ggpowindow.uiSwRanked.setCurrentIndex(0)
            self.ggpowindow.uiBtnRankedOpen.setVisible(True)
            self.ggpowindow.uiFrmRanked.setVisible(True)
            self.ggpowindow.uiBtnRankedFindMatch.setText("Find Opponent")

    def onPlayerStateChange(self, name, state):
        if name == self.controller.username and state != 0:
            self.ggpowindow.uiSwRanked.setCurrentIndex(0)
            self.ggpowindow.uiBtnRankedFindMatch.setText("Find Opponent")


# noinspection PyClassHasNoInit
class Message:
    # server to client
    SearchPoolAdd = 1
    SearchPoolRemove = 2
    MatchStarting = 3
    MatchEnding = 4

    # client to server
    RequestMatch = 101
    StartSearch = 102
    CancelSearch = 103
    ResetRequests = 104

