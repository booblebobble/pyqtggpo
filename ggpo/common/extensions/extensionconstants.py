# noinspection PyClassHasNoInit
class MatchStartReturnCode:
    """ Return values from EventMatch.start() """
    OK = 0
    P1Unavailable = 1
    P2Unavailable = 2
    BothPlayersUnavailable = 3
    GeneralError = 4


# noinspection PyClassHasNoInit
class MatchEvent:
    """  Event codes emitted by ExtensionMatch objects.  Each code will come with a tuple containing additional
         information, if applicable.  If a code sends additional data, it is described after the definition of the code.
         If a code has no additional data, an empty tuple is sent.

         The sequence these codes are sent in is described below.
    """

    """ Step 1) Startup

        Sent immediately after calling start() and when restarting after a failed startup attempt.

        If PlayersNotAvailable is sent, it is the last event sent and the match is aborted.  Otherwise proceed to Step 2.
    """

    # One of the players is not available
    PlayersNotAvailable = 100  # args=(side of player not available (1 or 2), or 3 if both)
    # Match startup is being attempted.
    EmulatorOpened = 101

    """ Step 2) Startup result

        One of the following will be sent

        If StartupFailedRetrying is sent, jump back to step 1

        If StartupFailedNotRetrying, jump ahead to step 5

        Otherwise continue to step 3
    """

    # Emulation has started successfully and the game is actually running
    EmulationStarted = 200
    # Emulation did not start within the time limit specified on match creation but will be reattempted.
    StartupFailedRetrying = 201
    # Emulation did not start within the time limit and will not be reattempted.
    StartupFailedNotRetrying = 202

    """ Step 3) Calibration """
    # We will be able to send in-game events for this match
    CalibrationSuccess = 300
    # We will *not* be able to send in-game events for this match
    CalibrationFail = 301

    """ Step 4) Game Events

        If CalibrationSuccess was sent in the last step, these codes will be sent repeatedly until the emulator is closed.

        If CalibrationFail was sent in the last step, no events at all will be sent for this step and no more events
        will be sent until step 5 below.
    """

    # A game (i.e. one best-of-3-rounds fight) has started
    GameStarted = 400
    # A round has started
    RoundStarted = 401
    # Player health has changed
    HealthChanged = 402       # args = (health player 1, health player 2)  Health is given on scale of 0-100
    # Timer has changed
    TimerChanged = 403        # args = (timer,)
    # A round has ended
    RoundEnded = 404          # args = (# of rounds won by player 1 this game, # of rounds won by player 1 this game)
    # A game has ended
    GameEnded = 405           # args = (winning side,)
    # Reset button has been pressed
    ResetPressed = 406


    """ Step 5) Emulator has been closed

        EmulatorClosed will always be sent unless the match couldn't start due to player status (PlayersNotAvailable)

        This will be the last event sent.
    """
    EmulatorClosed = 500
