from extensionbase import *
from ggpo.common.controller import IS_WINDOWS
from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

downarrow = unichr(0x25BC)
rightarrow = unichr(0x25B6)
blkcircle = unichr(0x2B24)

class KingOfTheHill(ExtensionBase):

    sigUpdateList = QtCore.pyqtSignal()
    sigUpdateGame = QtCore.pyqtSignal(list)

    @classmethod
    def hide(cls):
        cls.ggpowindow.uiFrmKOTH.setVisible(False)

    def __init__(self):
        ExtensionBase.__init__(self)

        self.ChannelJoined.connect(self.onChannelJoined)

        self.queue = []
        self.streak = 0

        self.tableModel = KOTHModel(self)
        self.ggpowindow.uiKOTHPlayersTable.setModel(self.tableModel)

        self.opened = False
        self.spectating = False

        self.ggpowindow.uiBtnKOTHOpen.clicked.connect(self.toggleFoldout)
        self.ggpowindow.uiBtnKOTHJoin.clicked.connect(self.joinClicked)
        self.ggpowindow.uiBtnKOTHSpec.clicked.connect(self.specClicked)

        self.sigUpdateList.connect(self.updateList)
        self.sigUpdateGame.connect(self.updateGame)

    def toggleFoldout(self, channelJoin=False):
        if self.controller.username in (x[0] for x in self.queue):
            self.chatMessage("Can't close panel while in queue.")
            return

        self.opened = not self.opened
        self.ggpowindow.uiFrmKOTH2.setVisible(self.opened)
        self.ggpowindow.uiBtnKOTHOpen.setText((downarrow if self.opened else rightarrow) + " King of the Hill")
        if not channelJoin:
            self.sendMessage(Message.UpdatesOn if self.opened else Message.UpdatesOff)
            if not self.opened and self.spectating:
                self.sendMessage(Message.SpectateOff)

    def joinClicked(self):
        inqueue = (self.controller.username in (x[0] for x in self.queue))
        self.sendMessage(Message.LeaveQueue if inqueue else Message.JoinQueueRequest)
        self.ggpowindow.uiBtnKOTHJoin.setEnabled(False)
        self.ggpowindow.uiBtnKOTHJoin.setText("Please Wait")

    def specClicked(self):
        self.sendMessage(Message.SpectateOn if not self.spectating else Message.SpectateOff)
        self.ggpowindow.uiBtnKOTHSpec.setText("Spectate" if not self.spectating else "Stop Spectating")
        self.spectating = not self.spectating
        if self.spectating:
            self.chatMessage("Spectating turned on. You will automatically spectate King of the Hill matches, beginning with the next one. " +
                             "Matches already in progress may not be spectated in order to prevent lag spikes.")
        else:
            self.chatMessage("Spectating disabled.")

    def receiveMessage(self, prefix, params):
        if prefix == Message.UpdateQueue:
            self.streak = params[0]
            self.queue = params[1:]

            self.ggpowindow.uiBtnKOTHJoin.setEnabled(True)

            if self.controller.username in (x[0] for x in self.queue):
                self.ggpowindow.uiBtnKOTHJoin.setText("Leave")
            else:
                self.ggpowindow.uiBtnKOTHJoin.setText("Join")

            self.sigUpdateList.emit()

        elif prefix == Message.UpdateGameStatus:
            self.sigUpdateGame.emit(params)

        elif prefix == Message.JoinRequestDeniedPleaseWait:
            self.chatMessage("Please wait a moment before rejoining to give others a chance.")
            self.ggpowindow.uiBtnKOTHJoin.setEnabled(True)
            self.ggpowindow.uiBtnKOTHJoin.setText("Join")

        elif prefix == Message.JoinRequestDeniedQueueFull:
            self.chatMessage("Couldn't join, queue full.")
            self.ggpowindow.uiBtnKOTHJoin.setEnabled(True)

        elif prefix == Message.PlayerJoined:
            if self.controller.username == params[0]:
                self.ggpowindow.uiBtnKOTHJoin.setEnabled(True)
                self.ggpowindow.uiBtnKOTHJoin.setText("Leave")
                self.chatMessage("You have been added to the queue. Your match will automatically start when it is your turn. " +
                                 "\r\nYou can play while waiting, but if " + 
                                 "you are still playing when your turn comes up you will be skipped.")
                if not IS_WINDOWS:
                    self.chatMessage("WARNING: Support for non-Windows operating systems is limited. " +
                                     "For technical reasons, if your turn comes up and the king is also not using Windows, your turn will be skipped. " +
                                     "Non-windows users have red names in the challenger queue.")

            if len(self.queue) == 0:
                self.streak = 0

            self.queue.append(params)
            self.sigUpdateList.emit()

        elif prefix == Message.PlayerLeft:
            if self.controller.username == params:
                self.ggpowindow.uiBtnKOTHJoin.setEnabled(True)
                self.ggpowindow.uiBtnKOTHJoin.setText("Join")

            try:
                pos = [x[0] for x in self.queue].index(params)
            except ValueError:
                self.sendMessage(Message.UpdateRequest)
                return

            if pos == 0:
                self.streak = 0

            del self.queue[pos]
            self.sigUpdateList.emit()

        elif prefix == Message.StreakUpdate:
            self.streak = params
            self.ggpowindow.uiLblKOTHStreak.setText(str(self.streak))

    def onChannelJoined(self):
        if not self.controller.isRomAvailable(self.controller.channel) or \
           not self.advancedMonitoringAvailable():
            self.hide()
        else:
            self.spectating = False

            self.queue = []
            self.streak = 0
            self.sigUpdateList.emit()

            self.opened = True  # set opened true so that call to toggleFoldout will set it back to false
            self.toggleFoldout(channelJoin=True)

            self.ggpowindow.uiBtnKOTHOpen.setVisible(True)
            self.ggpowindow.uiBtnKOTHJoin.setEnabled(True)
            self.ggpowindow.uiFrmKOTH.setVisible(True)
            self.ggpowindow.uiBtnKOTHJoin.setText("Join")
            self.ggpowindow.uiBtnKOTHSpec.setText("Spectate")

    def updateGame(self, params):
        self.ggpowindow.uiLblKOTHTimer.setText(str(params[0]))
        self.ggpowindow.uiPbKOTHHealth1.setValue(params[1])
        self.ggpowindow.uiPbKOTHHealth2.setValue(params[2])
        self.ggpowindow.uiLblKOTHRounds1.setValue(blkcircle*params[3])
        self.ggpowindow.uiLblKOTHRounds2.setValue(blkcircle*params[4])

    def updateList(self):
        self.ggpowindow.uiLblKOTHKing.setText("" if len(self.queue) == 0 else self.queue[0][0])
        self.ggpowindow.uiLblKOTHChallenger.setText("" if len(self.queue) < 2 else self.queue[1][0])
        self.ggpowindow.uiLblKOTHStreak.setText(str(self.streak))

#        ss = "" if (IS_WINDOWS or len(self.queue) == 0 or self.queue[0][1] != 1) else "QLabel {color:red;}"
        ss = "" if (len(self.queue) == 0 or self.queue[0][1] == 1) else "QLabel {color:red;}"
        self.ggpowindow.uiLblKOTHKing.setStyleSheet(ss)

#        ss = "" if (IS_WINDOWS or len(self.queue) < 2 or self.queue[1][1] != 1) else "QLabel {color:red;}"
        ss = "" if (len(self.queue) < 2 or self.queue[1][1] == 1) else "QLabel {color:red;}"
        self.ggpowindow.uiLblKOTHChallenger.setStyleSheet(ss)

        self.tableModel.emit(QtCore.SIGNAL("layoutAboutToBeChanged()"))
        self.tableModel.emit(QtCore.SIGNAL("layoutChanged()"))


class KOTHModel(QtCore.QAbstractTableModel):
    def __init__(self, koth):
        QtCore.QAbstractTableModel.__init__(self)
        self.koth = koth

    def rowCount(self, QModelIndex_parent=None, *args, **kwargs):
        return len(self.koth.queue)-1

    def columnCount(self, QModelIndex_parent=None, *args, **kwargs):
        return 1

    def headerData(self, section, Qt_Orientation, role=None):
        if role == Qt.DisplayRole and Qt_Orientation == Qt.Horizontal:
            return "Queue"

    def data(self, modelIndex, role=None):
        if role == Qt.DisplayRole:
            try:
                return self.koth.queue[modelIndex.row()+1][0]
            except:
                return ""

        elif role == Qt.ForegroundRole:
#            if not IS_WINDOWS and self.koth.queue[modelIndex.row()+1][1] != 1:
            if self.koth.queue[modelIndex.row()+1][1] != 1:
                return QtGui.QColor(Qt.red)

        elif role == Qt.TextAlignmentRole:
            return Qt.AlignCenter


# noinspection PyClassHasNoInit
class Message:
    # server to client
    UpdateQueue = 1
    UpdateGameStatus = 2
    PlayerJoined = 3
    PlayerLeft = 4
    StreakUpdate = 5
    JoinRequestDeniedQueueFull = 6
    JoinRequestDeniedPleaseWait = 7

    # client to server
    JoinQueueRequest = 101
    LeaveQueue = 102
    UpdateRequest = 103
    UpdatesOff = 104
    UpdatesOn = 105
    SpectateOff = 106
    SpectateOn = 107
