# -*- coding: utf-8 -*-
import os
import cgi
import logging
import logging.handlers
from colortheme import ColorTheme
from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
from ggpo.common.playerstate import PlayerStates
import ggpo.gui
from ggpo.gui.playermodel import PlayerModel
from ggpo.gui.emoticonsdialog import EmoticonDialog
from ggpo.common import copyright, util
from ggpo.common.util import logger, openURL, findURLs, replaceURLs, isWindows, findWine
from ggpo.common.settings import Settings


class GGPOWindow(QtGui.QMainWindow):
    def __init__(self, QWidget_parent=None):
        super(GGPOWindow, self).__init__(QWidget_parent)
        ggpo.gui.loadUi(__file__, self)
        self.controller = None
        self.channels = {}
        self.expectFirstChannelResponse = True
        self.lastSplitterExpandedSizes = []
        self.lastStateChangeMsg = ''
        self.playChallengeSound = lambda: None

        self.addSplitterHandleToggleButton()
        self.uiChatInputEdit.returnPressed.connect(self.returnPressed)
        self.uiDarkThemeAct.toggled.connect(ColorTheme.setDarkTheme)
        self.uiEmoticonAct.triggered.connect(self.insertEmoticon)
        self.uiEmoticonTbtn.setDefaultAction(self.uiEmoticonAct)
        self.uiEmoticonTbtn.setText(':)')
        self.uiLocateGgpofbaAct.triggered.connect(self.locateGGPOFBA)
        if isWindows():
            self.uiLocateWineAct.setVisible(False)
        else:
            self.uiLocateWineAct.triggered.connect(self.locateWine)
        if util.geoip2Installed:
            self.uiLocateGeommdbAct.triggered.connect(self.locateGeoMMDB)
        else:
            self.uiLocateGeommdbAct.setVisible(False)
        if Settings.value(Settings.DEBUG_LOG):
            self.uiDebugLogAct.setChecked(True)
        self.uiDebugLogAct.triggered.connect(self.__class__.debuglogTriggered)
        self.uiFontAct.triggered.connect(self.changeFont)
        self.uiAboutAct.triggered.connect(self.aboutDialog)
        self.uiAwayAct.triggered.connect(self.toggleAFK)
        self.uiMuteChallengeSoundAct.toggled.connect(self.__class__.toggleSound)
        self.uiNotifyPlayerStateChangeAct.toggled.connect(self.__class__.toggleNotifyPlayerStateChange)
        self.uiSRKForumAct.triggered.connect(
            lambda: openURL('http://forums.shoryuken.com/categories/super-street-fighter-ii-turbo'))
        self.uiSRKWikiAct.triggered.connect(lambda: openURL('http://wiki.shoryuken.com/Super_Street_Fighter_2_Turbo'))
        self.uiJPWikiAct.triggered.connect(lambda: openURL('http://sf2.gamedb.info/wiki/'))
        self.uiStrevivalAct.triggered.connect(lambda: openURL('http://www.strevival.com/'))
        self.uiHitboxViewerAct.triggered.connect(lambda: openURL('http://www.strevival.com/hitbox/'))
        self.uiSafejumpGuideAct.triggered.connect(lambda: openURL('http://www.strevival.com/hitbox/st-safejump/'))
        self.uiMatchVideosAct.triggered.connect(lambda: openURL('http://www.strevival.com/yt/'))

    def aboutDialog(self):
        QtGui.QMessageBox.information(self, 'About', copyright.about())

    def addSplitterHandleToggleButton(self):
        self.uiSplitter.setStyle(QtGui.QStyleFactory.create("Cleanlooks"))
        handle = self.uiSplitter.handle(1)
        layout = QtGui.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        button = QtGui.QToolButton(handle)
        button.setArrowType(QtCore.Qt.LeftArrow)
        button.clicked.connect(self.splitterButtonClicked)
        layout.addWidget(button)
        button = QtGui.QToolButton(handle)
        button.setArrowType(QtCore.Qt.RightArrow)
        button.clicked.connect(self.splitterButtonClicked)
        layout.addWidget(button)
        handle.setLayout(layout)

    def changeFont(self):
        font, ok = QtGui.QFontDialog.getFont()
        if ok:
            Settings.setPythonValue(Settings.CHAT_HISTORY_FONT,
                                    [font.family(), font.pointSize(), font.weight(), font.italic()])
            self.uiChatHistoryTxtB.setFont(font)

    def closeEvent(self, evnt):
        Settings.setValue(Settings.WINDOW_GEOMETRY, self.saveGeometry())
        Settings.setValue(Settings.WINDOW_STATE, self.saveState())
        Settings.setValue(Settings.SPLITTER_STATE, self.uiSplitter.saveState())
        Settings.setValue(Settings.TABLE_HEADER_STATE, self.uiPlayersTableV.horizontalHeader().saveState())
        super(GGPOWindow, self).closeEvent(evnt)

    @staticmethod
    def debuglogTriggered(value):
        if value:
            level = logging.INFO
        else:
            level = logging.ERROR
        Settings.setBoolean(Settings.DEBUG_LOG, value)
        for handler in logger().handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                handler.setLevel(level)
                break

    def ignoreAdded(self, name):
        self.uiChatHistoryTxtB.append(ColorTheme.statusHtml("* Adding " + name + " to ignore list."))

    def ignoreRemoved(self, name):
        self.uiChatHistoryTxtB.append(ColorTheme.statusHtml("* Removing " + name + " from ignore list."))

    def insertEmoticon(self):
        dlg = EmoticonDialog(self)
        if dlg.exec_():
            self.uiChatInputEdit.insert(dlg.value())
            self.uiChatInputEdit.setFocus()
            dlg.destroy()

    def joinChannel(self, *args):
        it = self.uiChannelsList.selectedItems()
        if len(it) > 0:
            self.controller.sendJoinChannelRequest(self.channels[it[0].text()])
            self.uiChatInputEdit.setFocus()

    def locateGGPOFBA(self):
        fname = QtGui.QFileDialog.getOpenFileName(self, 'Locate ggpofba.exe', os.path.expanduser("~"),
                                                  "ggpofba.exe (ggpofba.exe)")
        if fname:
            Settings.setValue(Settings.GGPOFBA_LOCATION, fname)
            self.controller.checkInstallation()

    def locateGeoMMDB(self):
        fname = QtGui.QFileDialog.getOpenFileName(self, 'Locate Geo mmdb file', os.path.expanduser("~"),
                                                  "Geo mmdb (*.mmdb)")
        if fname:
            Settings.setValue(Settings.GEOIP2DB_LOCATION, fname)

    def locateWine(self):
        if isWindows():
            return
        defaultLocation = findWine()
        if not defaultLocation:
            defaultLocation = os.path.expanduser("~")
        fname = QtGui.QFileDialog.getOpenFileName(self, 'Locate wine', defaultLocation, "wine (wine)")
        if fname:
            Settings.setValue(Settings.WINE_LOCATION, fname)

    def notifyStateChange(self, msg):
        if self.lastStateChangeMsg != msg:
            self.lastStateChangeMsg = msg
            self.uiChatHistoryTxtB.append(ColorTheme.statusHtml(msg))

    def onActionFailed(self, txt):
        self.uiChatHistoryTxtB.append(ColorTheme.statusHtml(txt))

    def onChallengeCancelled(self, name):
        self.uiChatHistoryTxtB.append(ColorTheme.statusHtml(name + " cancelled challenge"))
        self.updateStatusBar()

    def onChallengeDeclined(self, name):
        self.uiChatHistoryTxtB.append(ColorTheme.statusHtml(name + " declined your challenge"))
        self.updateStatusBar()

    def onChallengeReceived(self, name):
        c = self.controller.getPlayerColor(name)
        chat = '<b><font color="' + c + '">' + cgi.escape(name) + "</font></b> challenged you"
        self.uiChatHistoryTxtB.append(chat)
        self.playChallengeSound()
        self.updateStatusBar()

    def onChatReceived(self, name, txt):
        c = self.controller.getPlayerColor(name)
        chat = '<b><font color="' + c + '">' + cgi.escape('<' + name + '>') + "</font></b> " + cgi.escape(
            txt.strip())
        urls = findURLs(txt)
        if urls:
            for url in urls:
                chat += " <a href='" + url + "'>link</a>"
        self.uiChatHistoryTxtB.append(chat)

    def onListChannelsReceived(self):
        self.uiChannelsList.clear()
        self.channels = dict((c['title'], c['room']) for c in self.controller.channels.values() if c['room'] != 'lobby')
        sortedRooms = sorted(self.channels.keys())
        if 'lobby' in self.controller.channels:
            title = self.controller.channels['lobby']['title']
            sortedRooms.insert(0, title)
            self.channels[title] = 'lobby'
            self.uiChannelsList.setItemSelected(self.uiChannelsList.item(0), True)
        self.uiChannelsList.addItems(sortedRooms)
        if self.expectFirstChannelResponse:
            self.expectFirstChannelResponse = False
            lastChannel = Settings.value(Settings.SELECTED_CHANNEL)
            if lastChannel in self.controller.channels:
                idx = sortedRooms.index(self.controller.channels[lastChannel]['title'])
                self.uiChannelsList.setItemSelected(self.uiChannelsList.item(0), False)
                self.uiChannelsList.setItemSelected(self.uiChannelsList.item(idx), True)
                self.controller.sendJoinChannelRequest(lastChannel)
        self.uiChannelsList.itemSelectionChanged.connect(self.joinChannel)

    def onMOTDReceived(self, channel, topic, msg):
        self.uiChatHistoryTxtB.setHtml(replaceURLs(msg) + '<br>')

    def onPlayerStateChange(self, name, state):
        if Settings.value(Settings.NOTIFY_PLAYER_STATE_CHANGE):
            if state == PlayerStates.QUIT:
                self.notifyStateChange(name + " left")
            elif state == PlayerStates.AVAILABLE:
                self.notifyStateChange(name + " becomes available")
            elif state == PlayerStates.PLAYING:
                self.notifyStateChange(name + " is in a game")
        self.updateStatusBar()

    def onStatusMessage(self, msg):
        self.uiChatHistoryTxtB.append(ColorTheme.statusHtml(cgi.escape(msg)))

    def restorePreference(self):
        if Settings.value(Settings.COLORTHEME):
            self.uiDarkThemeAct.setChecked(True)
        if Settings.value(Settings.MUTE_CHALLENGE_SOUND):
            self.uiMuteChallengeSoundAct.setChecked(True)
        if Settings.value(Settings.NOTIFY_PLAYER_STATE_CHANGE):
            self.uiNotifyPlayerStateChangeAct.setChecked(True)
        fontsetting = Settings.pythonValue(Settings.CHAT_HISTORY_FONT)
        if fontsetting:
            self.uiChatHistoryTxtB.setFont(QtGui.QFont(*fontsetting))
        self.restoreStateAndGeometry()

    def restoreStateAndGeometry(self):
        saved = Settings.value(Settings.WINDOW_GEOMETRY)
        if saved:
            self.restoreGeometry(saved)
        saved = Settings.value(Settings.WINDOW_STATE)
        if saved:
            self.restoreState(saved)
        saved = Settings.value(Settings.SPLITTER_STATE)
        if saved:
            self.uiSplitter.restoreState(saved)
        saved = Settings.value(Settings.TABLE_HEADER_STATE)
        if saved:
            self.uiPlayersTableV.horizontalHeader().restoreState(saved)

    def returnPressed(self):
        line = self.uiChatInputEdit.text().strip()
        if line:
            self.uiChatInputEdit.clear()
            self.controller.sendChat(line)

    def setController(self, controller):
        self.controller = controller
        self.setupMediaPlayer()
        self.setupUserTable()
        self.uiChatInputEdit.setController(controller)
        controller.sigChannelJoined.connect(self.updateStatusBar)
        controller.sigPlayersLoaded.connect(self.updateStatusBar)
        controller.sigChannelsLoaded.connect(self.onListChannelsReceived)
        controller.sigMotdReceived.connect(self.onMOTDReceived)
        controller.sigActionFailed.connect(self.onActionFailed)
        controller.sigPlayerStateChange.connect(self.onPlayerStateChange)
        controller.sigChatReceived.connect(self.onChatReceived)
        controller.sigChallengeDeclined.connect(self.onChallengeDeclined)
        controller.sigChallengeReceived.connect(self.onChallengeReceived)
        controller.sigChallengeCancelled.connect(self.onChallengeCancelled)
        controller.sigIgnoreAdded.connect(self.ignoreAdded)
        controller.sigIgnoreRemoved.connect(self.ignoreRemoved)
        controller.sigStatusMessage.connect(self.onStatusMessage)
        controller.sigServerDisconnected.connect(
            lambda: self.onStatusMessage("Disconnected from ggpo.net. Please restart application"))
        if Settings.value(Settings.MUTE_CHALLENGE_SOUND):
            self.uiMuteChallengeSoundAct.setChecked(True)

    def setupMediaPlayer(self):
        try:
            from PyQt4.phonon import Phonon

            mp3path = self.controller.ggpoPathJoin('assets', 'challenger-comes.wav')
            if os.path.isfile(mp3path):
                audioOutput = Phonon.AudioOutput(Phonon.MusicCategory, self)
                mediaObject = Phonon.MediaObject(self)
                Phonon.createPath(mediaObject, audioOutput)
                mediaObject.enqueue(Phonon.MediaSource(mp3path))

                def play():
                    if not Settings.value(Settings.MUTE_CHALLENGE_SOUND):
                        mediaObject.seek(0)
                        mediaObject.play()
                self.playChallengeSound = play
        except ImportError:
            pass

    def setupUserTable(self):
        model = PlayerModel(self.controller)
        self.uiPlayersTableV.setModel(model)
        self.uiPlayersTableV.clicked.connect(model.onCellClicked)
        self.uiPlayersTableV.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.uiPlayersTableV.verticalHeader().setVisible(False)
        hh = self.uiPlayersTableV.horizontalHeader()
        hh.setMinimumSectionSize(25)
        hh.setHighlightSections(False)
        hh.resizeSection(PlayerModel.STATE, 25)
        width = hh.fontMetrics().boundingRect('Ping').width() + 18
        # windows's sort indicator is displayed at the top so no extra space needed
        if not isWindows():
            width += 10
        hh.resizeSection(PlayerModel.PING, width)
        hh.resizeSection(PlayerModel.IGNORE, 25)
        hh.resizeSection(PlayerModel.PLAYER, 165)
        hh.resizeSection(PlayerModel.OPPONENT, 165)
        hh.resizeSection(PlayerModel.ACCEPT_CHALLENGE, 25)
        hh.resizeSection(PlayerModel.DECLINE_CHALLENGE, 25)
        hh.setResizeMode(PlayerModel.STATE, QtGui.QHeaderView.Fixed)
        hh.setResizeMode(PlayerModel.PING, QtGui.QHeaderView.Fixed)
        hh.setResizeMode(PlayerModel.IGNORE, QtGui.QHeaderView.Fixed)
        hh.setResizeMode(PlayerModel.ACCEPT_CHALLENGE, QtGui.QHeaderView.Fixed)
        hh.setResizeMode(PlayerModel.DECLINE_CHALLENGE, QtGui.QHeaderView.Fixed)
        self.uiPlayersTableV.setSortingEnabled(True)
        self.uiPlayersTableV.sortByColumn(PlayerModel.DEFAULT_SORT, Qt.AscendingOrder)
        hh.sortIndicatorChanged.connect(self.sortIndicatorChanged)

    def sortIndicatorChanged(self, index, order):
        if index not in self.uiPlayersTableV.model().sortableColumns:
            self.uiPlayersTableV.horizontalHeader().setSortIndicator(
                self.uiPlayersTableV.model().lastSort, self.uiPlayersTableV.model().lastSortOrder)

    def splitterButtonClicked(self):
        sizes = self.uiSplitter.sizes()
        if sizes[0]:
            self.lastSplitterExpandedSizes = sizes[:]
            sizes[1] += sizes[0]
            sizes[0] = 0
        else:
            if len(self.lastSplitterExpandedSizes) > 0:
                sizes = self.lastSplitterExpandedSizes
            elif sizes[1]:
                sizes[0] = sizes[1] / 2
                sizes[1] /= 2
        self.uiSplitter.setSizes(sizes)

    def toggleAFK(self, state):
        self.controller.sendToggleAFK(state)

    @staticmethod
    def toggleNotifyPlayerStateChange(state):
        Settings.setBoolean(Settings.NOTIFY_PLAYER_STATE_CHANGE, state)

    @staticmethod
    def toggleSound(state):
        Settings.setBoolean(Settings.MUTE_CHALLENGE_SOUND, state)

    def updateStatusBar(self):
        self.uiStatusbar.showMessage(self.controller.statusBarMessage())