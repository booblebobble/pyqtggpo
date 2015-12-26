import datetime
import time
import threading
from extensionbase import *
from PyQt4 import QtCore, QtGui

class Tournaments(ExtensionBase):

    sigReceiveUpdate = QtCore.pyqtSignal(list)
    sigReceiveInfo = QtCore.pyqtSignal(list)
    sigHideUI = QtCore.pyqtSignal()
    sigReceiveModData = QtCore.pyqtSignal(list)

    @classmethod
    def hide(cls):
        cls.ggpowindow.uiTmPanel.setVisible(False)

    def __init__(self):
        ExtensionBase.__init__(self)

        self.ChannelJoined.connect(self.onChannelJoined)
        self.PlayerStateChange.connect(self.onPlayerStateChange)

        self.sigReceiveUpdate.connect(self.receiveUpdate)
        self.sigReceiveInfo.connect(self.receiveInfo)
        self.sigHideUI.connect(self.hide)
        self.sigReceiveModData.connect(self.receiveModData)

        self.ggpowindow.uiTmRegisterButton.clicked.connect(self.registerButtonClicked)
        self.ggpowindow.uiTmBtnReady.clicked.connect(self.readyButtonClicked)
        self.ggpowindow.uiTmBtnSubmit.clicked.connect(self.submitButtonClicked)
        self.ggpowindow.uiTmModScoreSubmit.clicked.connect(self.modSubmitButtonClicked)
#        self.ggpowindow.uiTmModKickPlayer.clicked.connect(self.modKickButtonClicked)
        self.ggpowindow.uiTmBtnRules.clicked.connect(self.rulesButtonClicked)
        self.ggpowindow.uiTmModMatches.currentRowChanged.connect(self.modMatchSelectionChanged)
        self.ggpowindow.uiTmBtnMod.clicked.connect(self.modButtonClicked)

        self.ggpowindow.uiTmReportOpp.setValidator(QtGui.QIntValidator(0, 100))
        self.ggpowindow.uiTmReportMe.setValidator(QtGui.QIntValidator(0, 100))
        self.ggpowindow.uiTmModScore1.setValidator(QtGui.QIntValidator(0, 100))
        self.ggpowindow.uiTmModScore2.setValidator(QtGui.QIntValidator(0, 100))

        self.ggpowindow.uiTmBtnMod.setVisible(False)

        self.regTimer = None
        self.readyTimer = None
        self.matchEndTimer = None
        self.timerLock = threading.Lock()

        self.isGFinals = False

        self.title = ""
        self.url = ""
        self.moderators = []
        self.rules = ""

        self.modPaneOpen = False
        self.modParticipants = []
        self.modMatches = []

        self.RoundStrings = {Rounds.LosersFinals: "Losers Finals",
                             Rounds.LosersSemifinals: "Losers Semifinals",
                             Rounds.LosersBracket: "Losers Bracket",
                             Rounds.WinnersFinals: "Winners Finals",
                             Rounds.WinnersSemifinals: "Winners Semifinals",
                             Rounds.WinnersBracket: "Winners Bracket",
                             Rounds.GrandFinals1: "Grand Finals Set #1",
                             Rounds.GrandFinals2: "Grand Finals Set #2"}


    def onChannelJoined(self):
        self.sigHideUI.emit()
        self.cleanupTimers()
#        # DEBUG
#        self.sendMessage(Message.ToggleRegistration)

    def onPlayerStateChange(self, name, state):
        if name == self.controller.username:
            self.ggpowindow.uiTmBtnSubmit.setEnabled(state != 2)

    def cleanupTimers(self):
        with self.timerLock:
            if self.regTimer != None: self.regTimer.cancel()
            if self.readyTimer != None: self.readyTimer.cancel()
            if self.matchEndTimer != None: self.matchEndTimer.cancel()

            self.regTimer = None
            self.readyTimer = None
            self.matchEndTimer = None

    def receiveMessage(self, prefix, params):
        if prefix == Message.Update:
            self.sigReceiveUpdate.emit(params)

        elif prefix == Message.TournamentInfo:
            self.sigReceiveInfo.emit(params)

        elif prefix == Message.TournamentOver:
            self.regTimer = None
            self.cleanupTimers()
            self.sigHideUI.emit()
            if params != None:
                self.chatMessage("%s has won the tournament!" % params)

        elif prefix == Message.ModeratorInfoResponse:
            if params == None:
                self.chatMessage("You are not a moderator for this tournament.")
                return

            self.modPaneOpen = True
            self.sigReceiveModData.emit(params)

        elif prefix == Message.ModeratorScoreReportResponse:
            if params:
                self.chatMessage("Score result accepted.  Thank you.")
            else:
                QtGui.QMessageBox.information(self.ggpowindow, "Error", "Score result not accepted. " +
                                                               "Probably the participants resolved the conflict themselves.\r\n\r\n" +
                                                               "Click OK to refresh match data.")
                self.modPaneOpen = False

            self.modButtonClicked()

        # elif prefix == Message.ModeratorKickPlayerResponse:
        #     if params:
        #         self.chatMessage("Kick confirmed.  Thank you.")
        #     else:
        #         QtGui.QMessageBox.information(self.ggpowindow, "Error", "Unexpected error.\r\n\r\n" +
        #                                                        "Click OK to refresh match data.")
        #         self.modPaneOpen = False
        #
        #     self.modButtonClicked()

    def receiveInfo(self, params):
        self.title = params[0]
        self.url = "http://challonge.com/%s" % params[1]
        self.moderators = params[2]
        self.rules = params[3]

        self.ggpowindow.uiLblTmTitle.setText(params[0])
        self.ggpowindow.uiTmBracketLink.setText(
            "<a href=http://challonge.com/%s>Click Here For Bracket</a>" % params[1])
        self.ggpowindow.uiTmBtnMod.setVisible(self.controller.username in self.moderators)
        self.ggpowindow.uiTmBtnMod.setText("Moderator Tools")

    def receiveUpdate(self, params):
        if self.modPaneOpen:
            return
        else:
            self.ggpowindow.uiTmBtnMod.setEnabled(True)
            self.ggpowindow.uiTmBtnMod.setText("Moderator Tools")

        self.ggpowindow.uiTmPanel.setVisible(True)

        status = params[UpdateParams.Status]

        if status == UpdateStatus.NoMatch:
            self.ggpowindow.uiTmStacked.setVisible(False)
            return

        self.ggpowindow.uiTmStacked.setVisible(True)

        self.ggpowindow.uiTmLblRound.setText(self.RoundStrings.get(params[UpdateParams.RoundID], ""))
        self.ggpowindow.uiTmLblRound2.setText(self.RoundStrings.get(params[UpdateParams.RoundID], ""))

        if params[UpdateParams.RoundID] in {Rounds.GrandFinals2, Rounds.GrandFinals2}:
            self.isGFinals = True

        if status == UpdateStatus.RegistrationNotRegistered:
            self.ggpowindow.uiTmRegStatus.setText("Not Registered")
            with self.timerLock:
                if self.regTimer == None:
                    self.regTimer = DisplayTimer(params[UpdateParams.RegistrationTimeout],
                                                 self.ggpowindow.uiTmRegTimer,
                                                 "Registration ends in ",
                                                 ".",
                                                 self.regTimerCallback)
                else:
                    self.regTimer.alter(datetime.datetime.now() +
                                        datetime.timedelta(seconds=params[UpdateParams.RegistrationTimeout]), None, None)

            self.ggpowindow.uiTmStacked.setCurrentIndex(0)
            self.ggpowindow.uiTmRegisterButton.setEnabled(True)
            self.ggpowindow.uiTmRegisterButton.setText("Register")

        elif status == UpdateStatus.RegistrationRegistered:
            self.ggpowindow.uiTmRegStatus.setText("Registered!")
            with self.timerLock:
                if self.regTimer == None:
                    self.regTimer = DisplayTimer(params[UpdateParams.RegistrationTimeout],
                                                 self.ggpowindow.uiTmRegTimer,
                                                 "Registration ends in ",
                                                 ".",
                                                 self.regTimerCallback)
                else:
                    self.regTimer.alter(datetime.datetime.now() +
                                        datetime.timedelta(seconds=params[UpdateParams.RegistrationTimeout]), None, None)

            self.ggpowindow.uiTmStacked.setCurrentIndex(0)
            self.ggpowindow.uiTmRegisterButton.setEnabled(True)
            self.ggpowindow.uiTmRegisterButton.setText("Unregister")

        elif status == UpdateStatus.MatchPendingPrereqPending:
            self.ggpowindow.uiTmStacked.setCurrentIndex(1)
            self.ggpowindow.uiTmNextOpponent.setText("To be determined.")

        elif status == UpdateStatus.MatchPendingPrereqOpen:
            self.ggpowindow.uiTmStacked.setCurrentIndex(1)
            self.ggpowindow.uiTmNextOpponent.setText(
                "%s of %s vs. %s" % ("Loser" if params[UpdateParams.PrereqLoser] else "Winner",
                                     params[UpdateParams.PrereqP1Name],
                                     params[UpdateParams.PrereqP2Name]))

        elif status == UpdateStatus.MatchOpenNotStarted:
            self.ggpowindow.uiTmStacked.setCurrentIndex(2)
            self.ggpowindow.uiTmBtnReady.setEnabled(True)
            self.ggpowindow.uiTmLblMe.setText(self.controller.username)
            self.ggpowindow.uiTmLblOpp.setText(params[UpdateParams.OppName])
            self.ggpowindow.uiTmLblReadyMe.setText("Ready!" if params[UpdateParams.SelfReady] else "Not ready.")
            self.ggpowindow.uiTmLblReadyOpp.setText("Ready!" if params[UpdateParams.OppReady] else "Not ready.")
            self.ggpowindow.uiTmLblReadyMe.setStyleSheet("" if params[UpdateParams.SelfReady] else "QLabel {color:red;}")
            self.ggpowindow.uiTmLblReadyOpp.setStyleSheet("" if params[UpdateParams.OppReady] else "QLabel {color:red;}")
            self.ggpowindow.uiTmReportMe.setText("")
            self.ggpowindow.uiTmReportOpp.setText("")

            with self.timerLock:
                if self.regTimer != None:
                    self.regTimer.cancel()
                    self.regTimer = None
                if self.readyTimer == None:
                    self.readyTimer = DisplayTimer(params[UpdateParams.StartTimeout],
                                                   self.ggpowindow.uiTmBtnReady,
                                                   "Not Ready (" if params[UpdateParams.SelfReady] else "Ready (",
                                                   ")",
                                                   self.readyTimerCallback)
                else:
                    self.readyTimer.alter(datetime.datetime.now() +
                                          datetime.timedelta(seconds=params[UpdateParams.StartTimeout]),
                                          "Not Ready (" if params[UpdateParams.SelfReady] else "Ready (", None)

        elif status == UpdateStatus.MatchOpenStarted:
            self.ggpowindow.uiTmStacked.setCurrentIndex(3)
            self.ggpowindow.uiTmBtnSubmit.setEnabled(self.controller.playingagainst == "")

            merep, opprep = params[UpdateParams.MeReport], params[UpdateParams.OppReport]
            emptyrep = [None, None]

            if opprep != emptyrep and merep == emptyrep:
                self.ggpowindow.uiTmLblReportStatus.setText("Opponent has submitted score of You: %d, Them: %d" % (opprep[0], opprep[1]))

            if opprep == emptyrep and merep != emptyrep:
                self.ggpowindow.uiTmLblReportStatus.setText("Score submitted. Waiting for opponent.")

            elif merep != emptyrep and opprep != emptyrep and merep != opprep:
                self.ggpowindow.uiTmLblReportStatus.setText("Opponent has submitted conflicting score.  See chat for more info.")
                # server should send some chat info here

            with self.timerLock:
                if self.regTimer != None:
                    self.regTimer.cancel()
                    self.regTimer = None
                if self.readyTimer != None:
                    self.readyTimer.cancel()
                    self.readyTimer = None
                if self.matchEndTimer == None:
                    self.matchEndTimer = DisplayTimer(params[UpdateParams.FinishTimeout],
                                                      self.ggpowindow.uiTmBtnSubmit,
                                                      "Submit Score ",
                                                      "",
                                                      self.matchEndTimerCallback)
                else:
                    self.matchEndTimer.alter(datetime.datetime.now() +
                                             datetime.timedelta(seconds=params[UpdateParams.FinishTimeout]), None, None)

    def receiveModData(self, data):
        self.ggpowindow.uiTmBtnMod.setEnabled(True)
        self.ggpowindow.uiTmBtnMod.setText("Close Mod Tools")
        self.ggpowindow.uiTmModScoreSubmit.setEnabled(True)
#        self.ggpowindow.uiTmModKickPlayer.setEnabled(True)
        self.ggpowindow.uiTmStacked.setCurrentIndex(4)

#        self.modParticipants = sorted(data[0])
#        self.modMatches = data[1]
        self.modMatches = data

        self.ggpowindow.uiTmModMatches.clear()
        self.ggpowindow.uiTmModMatches.addItems(["%s vs. %s" % (mInfo[0], mInfo[1]) for mInfo in self.modMatches])

        self.ggpowindow.uiTmModPlayers.clear()
        self.ggpowindow.uiTmModPlayers.addItems(self.modParticipants)

        self.ggpowindow.uiTmModP1.setText("")
        self.ggpowindow.uiTmModP2.setText("")
        self.ggpowindow.uiTmModScore1.setText("")
        self.ggpowindow.uiTmModScore2.setText("")

        self.modMatchSelectionChanged(self.ggpowindow.uiTmModMatches.currentRow())

    def modMatchSelectionChanged(self, row):
        names = {1:self.modMatches[row][0], 2:self.modMatches[row][1]}
        reports = {1:{1:self.modMatches[row][2], 2:self.modMatches[row][3]}, 2:{1:self.modMatches[row][4], 2:self.modMatches[row][5]}}
        refreport = {1:self.modMatches[row][6], 2:self.modMatches[row][7]}

        self.ggpowindow.uiTmModP1.setText(names[1])
        self.ggpowindow.uiTmModP2.setText(names[2])
        self.ggpowindow.uiTmModScore1.setText("")
        self.ggpowindow.uiTmModScore2.setText("")

        self.ggpowindow.uiTmModReports.setText("Reports: %s (%s), %s (%s), Automated (%s)" % (
                names[1], "%s - %s" % (reports[1][1], reports[1][2]) if reports[1] != [None, None] else "N/A",
                names[2], "%s - %s" % (reports[2][1], reports[2][2]) if reports[2] != [None, None] else "N/A",
                "%s - %s" % (refreport[1], refreport[2]) if refreport != [0, 0] else "N/A"
        ))

    def modSubmitButtonClicked(self):
        try:
            score1 = int(self.ggpowindow.uiTmModScore1.text())
            score2 = int(self.ggpowindow.uiTmModScore2.text())
            err = score1 < 0 or score2 < 0 or score1 == score2
        except:
            err = True

        if err:
            QtGui.QMessageBox.warning(self.ggpowindow, "Error", "Scores must be numeric, nonnegative, and different.")
            return

        self.ggpowindow.uiTmBtnMod.setEnabled(False)
        self.ggpowindow.uiTmModScoreSubmit.setEnabled(False)
#        self.ggpowindow.uiTmModKickPlayer.setEnabled(False)

        names = self.modMatches[self.ggpowindow.uiTmModMatches.currentRow()][0:2]

        # noinspection PyUnboundLocalVariable
        res = QtGui.QMessageBox.question(self.ggpowindow, "Please Verify", ("About to submit a result of %s - %s, %s - %s. Is this correct?" %
                                                                                        (names[0], str(score1), names[1], score2)) +
                                                                           "\r\n\r\n" +
                                                                           "This cannot be undone.",
                                                                            QtGui.QMessageBox.Yes,
                                                                            QtGui.QMessageBox.No
                                                                            )
        if res == QtGui.QMessageBox.Yes:
            self.sendMessage(Message.ModeratorScoreReport, (names, [score1, score2]))
        else:
            self.ggpowindow.uiTmBtnMod.setEnabled(True)
            self.ggpowindow.uiTmModScoreSubmit.setEnabled(True)
#            self.ggpowindow.uiTmModKickPlayer.setEnabled(True)

    # def modKickButtonClicked(self):
    #     self.ggpowindow.uiTmBtnMod.setEnabled(False)
    #     self.ggpowindow.uiTmModScoreSubmit.setEnabled(False)
    #     self.ggpowindow.uiTmModKickPlayer.setEnabled(False)
    #
    #     name = self.modParticipants[self.ggpowindow.uiTmModPlayers.currentRow()]
    #     res = QtGui.QMessageBox.question(self.ggpowindow, "Please Verify", ("About to kick player %s from current tournament." % name) +
    #                                                                        "\r\n\r\n" +
    #                                                                        "This cannot be undone.",
    #                                                                         QtGui.QMessageBox.Yes,
    #                                                                         QtGui.QMessageBox.No
    #                                                                         )
    #
    #     if res == QtGui.QMessageBox.Yes:
    #         self.sendMessage(Message.ModeratorKickPlayer, name)
    #     else:
    #         self.ggpowindow.uiTmBtnMod.setEnabled(True)
    #         self.ggpowindow.uiTmModScoreSubmit.setEnabled(True)
    #         self.ggpowindow.uiTmModKickPlayer.setEnabled(True)

    def regTimerCallback(self):
        with self.timerLock:
            if self.regTimer != None:
                self.ggpowindow.uiTmStacked.setVisible(False)
            self.regTimer = None

    def readyTimerCallback(self):
        with self.timerLock:
            if self.readyTimer != None:
                self.ggpowindow.uiTmStacked.setVisible(False)
            self.readyTimer = None

    def matchEndTimerCallback(self):
        with self.timerLock:
            if self.matchEndTimer != None:
                self.ggpowindow.uiTmStacked.setVisible(False)
            self.matchEndTimer = None

    def registerButtonClicked(self):
        self.ggpowindow.uiTmRegisterButton.setEnabled(False)
        self.ggpowindow.uiTmRegisterButton.setText("Please Wait")
        self.sendMessage(Message.ToggleRegistration)

    def readyButtonClicked(self):
        self.ggpowindow.uiTmBtnReady.setEnabled(False)
        self.sendMessage(Message.ToggleReady)

    def submitButtonClicked(self):
        if self.controller.playingagainst != '' and not self.isGFinals:
            self.ggpowindow.uiTmLblReportStatus.setText("Cannot submit scores during a match.")
            return

        try:
            score1 = int(self.ggpowindow.uiTmReportMe.text())
            score2 = int(self.ggpowindow.uiTmReportOpp.text())
        except:
            self.ggpowindow.uiTmLblReportStatus.setText("Invalid scores.")
            return

        if score1 < 0 or score2 < 0:
            self.ggpowindow.uiTmLblReportStatus.setText("Scores must be positive.")
            return

        if score1 == score2:
            self.ggpowindow.uiTmLblReportStatus.setText("Scores must be different.")
            return

        self.sendMessage(Message.ScoreReport, (score1, score2))
        self.ggpowindow.uiTmLblReportStatus.setText("Score submitted.")

    def modButtonClicked(self):
        if self.modPaneOpen:
            self.modPaneOpen = False
            self.sendMessage(Message.RequestUpdate)
        else:
            self.sendMessage(Message.ModeratorRequestInfo)

        self.ggpowindow.uiTmBtnMod.setEnabled(False)
        self.ggpowindow.uiTmBtnMod.setText("Please Wait")

    def rulesButtonClicked(self):
        self.chatMessage(self.rules)
        self.chatMessage("")
        self.chatMessage("<br>Moderators for this tournament are: " + ", ".join(self.moderators))

class DisplayTimer(QtCore.QObject):
    sig1 = QtCore.pyqtSignal(str)
    sig2 = QtCore.pyqtSignal()

    def __init__(self, duration, label, prefixString, postfixString, callback):
        QtCore.QObject.__init__(self)
        self.callback = callback
        self.label = label
        self.prefix = prefixString
        self.postfix = postfixString
        self.timeout = datetime.datetime.now() + datetime.timedelta(seconds=duration)

        self.sig1.connect(self._updateLabel)
        self.sig2.connect(self._doCallback)

        self.abort = False

        self.thd = threading.Thread(target=self._loop)
        self.thd.daemon = True
        self.thd.start()

    def cancel(self):
        self.abort = True

    def alter(self, timeout, prefix, postfix):
        if timeout != None:
            self.timeout = timeout
        if prefix != None:
            self.prefix = prefix
        if postfix != None:
            self.postfix = postfix

        tmp = (self.timeout - datetime.datetime.now()).total_seconds()
        if tmp > 0 and self.label != None:
            self.sig1.emit(self.prefix + ("%i:%02i" % (tmp / 60, tmp % 60)) + self.postfix)

    def _doCallback(self):
        if not self.abort:
            self.callback()

    def _updateLabel(self, s):
        self.label.setText(s)

    def _loop(self):
        while True:
            if self.abort:
                break

            tmp = (self.timeout - datetime.datetime.now()).total_seconds()
            if tmp < 0:
                break

            if self.label != None:
                self.sig1.emit(self.prefix + ("%i:%02i" % (tmp / 60, tmp % 60)) + self.postfix)

            time.sleep(1)

        if self.callback != None and not self.abort:
            self.sig2.emit()


# noinspection PyClassHasNoInit
class Message:
    # server-to-client messages
    TournamentInfo = 1
    Update = 2
    TournamentOver = 3
    ModeratorInfoResponse = 4
    ModeratorScoreReportResponse = 5
#    ModeratorKickPlayerResponse = 6

    # client-to-server messages
    ToggleRegistration = 101
    ToggleReady = 102
    ScoreReport = 103
    ModeratorRequestInfo = 104
    ModeratorScoreReport = 105
#    ModeratorKickPlayer = 106
    RequestUpdate = 107


# noinspection PyClassHasNoInit
class UpdateParams:
    Status = 0                  # One of UpdateStatus
    OppName = 1                 # Name of opponent
    SelfReady = 2               # If user is set as ready or not
    OppReady = 3                # If user's opponent is set as ready
    RegistrationTimeout = 4     # Seconds until registration period ends
    StartTimeout = 5            # Seconds until players must ready up and start match
    FinishTimeout = 6           # Seconds until players must finish playing match
    PrereqP1Name = 7            # Names of players in match which will determine opponent
    PrereqP2Name = 8            #
    PrereqLoser = 9             # Whether opponent will be the loser of the prereq match
    RoundID = 10                # One of Rounds
    MeReport = 11               # Score reported by user
    OppReport = 12              # Score reported by opponent


# noinspection PyClassHasNoInit
class Rounds:
    LosersFinals = 1
    LosersSemifinals = 2
    LosersBracket = 3
    WinnersFinals = 4
    WinnersSemifinals = 5
    WinnersBracket = 6
    GrandFinals1 = 7
    GrandFinals2 = 8

# noinspection PyClassHasNoInit
class UpdateStatus:
    RegistrationNotRegistered = 1   # Registration period, you are not registered
    RegistrationRegistered = 2      # Registration period, you are registered
    MatchOpenNotStarted = 3         # Match available, not started yet
    MatchOpenStarted = 4            # Match in progress
    MatchPendingPrereqPending = 5   # Next opponent is winner/loser of a match in progress
    MatchPendingPrereqOpen = 6      # Next opponent is TBD
    NoMatch = 7                     # No matches for this user
