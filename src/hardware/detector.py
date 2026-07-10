from collections.abc import Sequence
import time
import clr
import os

from System import Int32

import numpy as np


dll_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '.', 'bin', 'ttInterface.dll'))
print("Loading DLL from:", dll_path)

clr.AddReference(dll_path)

from TimeTag import TTInterface, Logic

# Helper function to convert channel to binary code
def binary_code(channel: int | Sequence[int]) -> int:
    if isinstance(channel, Sequence):
        return sum(1 << (ch - 1) for ch in channel)
    return 1 << (channel - 1)

class Logic16:
    def __init__(self, coincidence_window=1e-9, logic_mode=True,
                integration_window=0.5):
        self.MyTagger = TTInterface()
        self.MyTagger.Open()
        self._resolution = self.MyTagger.GetResolution()
        self._logic_mode = False
        if logic_mode:
            self._logic_mode = True
            self.MyLogic = Logic(self.MyTagger)
            self.MyLogic.SwitchLogicMode()

        self._total_channels = self.MyTagger.GetNoInputs()
        self._integration_window = integration_window # same as self.timeInterval
        self._coincidence_window = coincidence_window
        # For antilatch
        self.singles = None
        self._antilatch_timeslice = 0.100 # 100 miliseconds
        self.antilatch_func = lambda: print('test')
        self.coincidences = None

        self.TimerCounter1 = Int32
        self.clear_buffer() 

    def __enter__(self):
        """
        Context manager
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Context manager
        """
        self.MyTagger.Close()

    def set_channels(self, singles, coincidences=None):
        assert isinstance(singles, Sequence)
        self.singles = singles
        self._bsingles = [binary_code(channel) for channel in singles]
        if coincidences is not None:
            assert isinstance(coincidences[0], Sequence)
            self.coincidences = coincidences
            self._bcoincidences = [binary_code(pair) for pair in coincidences]

    def set_delays(self, channel_delays: dict | list | None = None, default_delay: int = 100):
        if isinstance(channel_delays, (list, tuple)):
            channel_delays = {i + 1: channel_delays[i] for i in range(min(len(channel_delays), self._total_channels))}
        if channel_delays is None:
            channel_delays = {}

        if hasattr(self, 'delays'):
            for k, v in channel_delays.items():
                if not 1 <= k <= self._total_channels:
                    raise ValueError(f"Invalid channel {k}")
                self.delays.update({k: v})
                m = int((v * 1e-9) / self._resolution)
                self.MyTagger.SetDelay(k, m)
        else:
            self.delays = {k: default_delay for k in range(1, self._total_channels + 1)}
            self.set_delays(channel_delays=channel_delays)

    def configure(self, threshold: float = 0.5, coincidence_window: float = None, delays=None):
        self.set_input_threshold(default_threshold=threshold)
        if coincidence_window is not None:
            self.set_coincidence_window(coincidence_window)
        if delays is not None:
            self.set_delays(delays)

    def set_input_threshold(self, channel_threshold_dict=None, default_threshold=0.5):
        # Configure the channel for measurement
        if channel_threshold_dict is not None:
            for k,v in channel_threshold_dict.items():
                if not 1 <= k <= self._total_channels:
                    raise ValueError(f"Invalid channel {k}")
                self.MyTagger.SetInputThreshold(k, v)
        else:
            for k in range(1, self._total_channels+1): # 16 channels if low-resolution
                self.MyTagger.SetInputThreshold(k, default_threshold)

    def set_coincidence_window(self, window):
        assert self._logic_mode
        self._coincidence_window = window*1e-9
        self.MyLogic.SetWindowWidth(Int32(int(self._coincidence_window / self._resolution)))

    def get_status(self):
        msg = '>>> Logic16 counting card\n'
        msg += '> FPGA version:\t\t{}\n'.format(self.MyTagger.GetFpgaVersion())
        msg += '> Resolution:\t\t{}\n'.format(self._resolution)
        msg += '> Input channels:\t{}\n'.format(self.MyTagger.GetNoInputs())
        msg += '> Integration window:\t{} s\n'.format(self._integration_window)
        msg += '> Coincidence window:\t{} ns\n'.format(self._coincidence_window*1e9)
        print(msg)

    def clear_buffer(self):
        self.MyLogic.ReadLogic()
        TimeCounter1 = self.MyLogic.GetTimeCounter()

    def calc_single_count(self, pos, neg):
        """
        Calculates the count for a single channel.
        Uses binary encoding for the positive and negative channels.
        """
        neg_code = binary_code(neg) if neg != 0 else 0
        return self.MyLogic.CalcCount(binary_code(pos), neg_code)

    def read_counts(self, pos_coincidence, pos_singles, neg_singles=[0]):
        """
        Reads the counts for singles and coincidences for the specified channels.
        Returns the counts as arrays and the time counter value.
        """
        self.MyLogic.ReadLogic()
        timecounter = self.MyLogic.GetTimeCounter()

        counts_singles = [self.calc_single_count(pos, 0) for pos in pos_singles]
        neg_singles = neg_singles * len(pos_coincidence) if len(neg_singles) == 1 else neg_singles
        assert len(neg_singles) == len(pos_coincidence)
        counts_coinc = [self.calc_single_count(pos, neg_singles[k]) for k, pos in enumerate(pos_coincidence)]

        return np.array(counts_coinc, dtype=int), np.array(counts_singles, dtype=int), timecounter

    def antilatch_check(self, singles_to_check):
        """
        Checks for latching events, both in the case of one detector latching (any) or all detectors latching (all). It is a good idea to differentiate between the two cases: if all detectors latch, it might be indicative of the cryostat being warm.
        """
        check = [singles==0 for singles in singles_to_check]
        return any(check) + all(check)

    def read_counts_integrated(self, pos_coincidence, pos_singles, neg_singles=[0]):
        """
        Reads integrated counts over a specified integration window.
        Handles antilatching by checking for repeated latch events and retrying if necessary.
        """
        counting_time = 0
        total_c_counts = np.zeros(len(pos_coincidence))
        total_s_counts = np.zeros(len(pos_singles))
        has_latched = 0
        self.clear_buffer()

        # Instead of reading counts for the entire `counting_time` duration, which can be quite large,
        # read for a smaller integration time (we call this the "timeslice"). Doing this reduces the
        # chance of latching events messing up the photon counts.
        while counting_time <= self._integration_window:
            time.sleep(self._antilatch_timeslice)
            c_counts, s_counts, timecounter = self.read_counts(pos_coincidence=pos_coincidence,
                                                               pos_singles=pos_singles,
                                                               neg_singles=neg_singles)
            antilatch_flags = self.antilatch_check(s_counts)
            has_latched += antilatch_flags

            # If detectors keep latching, wait for a bit instead of sending another antilatch request.
            if has_latched > 5:
                self.antilatch_func()
                print('WARNING: several latching events in a row, waiting 1 min.')
                has_latched = 0
                time.sleep(60)
                continue
            if antilatch_flags > 0:
                self.antilatch_func()
                print('.', end='') # Simple way to keep track of antilatch events
                time.sleep(0.2)
                self.clear_buffer()
                continue
            else:
                has_latched = 0
            total_c_counts += c_counts
            total_s_counts += s_counts
            counting_time += timecounter * self._resolution
        return total_c_counts, total_s_counts, counting_time
