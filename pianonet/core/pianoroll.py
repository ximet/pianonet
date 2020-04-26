import numpy as np
from pypianoroll import Track, Multitrack

from pianonet.core.midi_tools import play_midi_from_file


class Pianoroll:
    """
    An wrapped array representing piano key states in time. The first axis represents the time step, each of which has
    an associated key state of 128 keys. This implementation represents keys as binary on or off states at each time
    step, so the array is a 2D set of booleans.

    Example pianoroll array state:

            t = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, ...

            C   0  1  1  1  1  0  0  0  0  0
            B   0  0  0  0  0  1  1  1  1  1
            A#  1  0  0  0  0  0  0  0  0  0
            A   0  1  1  1  1  0  0  0  0  0
            G#  0  0  0  0  0  0  0  0  0  0

    General MIDI notes: Note index 60 is middle C, program = 0 is piano instrument, the max velocity allowed is 128.
                        A midi file can store up to 16 different tracks.
    """

    def __init__(self, initializer):
        """
        initializer: A string that is a path to a midi file or an array of shape (time_steps, 128).
        """

        if isinstance(initializer, str):
            midi_file_path = initializer
            self.load_from_midi_file(midi_file_path)
        else:
            np_array = initializer
            self.array = np.copy(np_array)

    def load_from_midi_file(self, midi_file_path):
        """
        midi_file_path: String that is path to a midi file to load. This midi file is assumed to have a beat resolution
                        of 24.

        A merged and binarized numpy array (time_steps, 128) in shape is loaded into self.array.
        """

        multitrack = Multitrack(filename=midi_file_path)

        multitrack.check_validity()

        if multitrack.beat_resolution != 24:
            raise Exception("Beat resolution of all midi files should be 24. Encountered beat resolution is " + str(
                multitrack.beat_resolution))

        multitrack.merge_tracks(track_indices=[i for i in range(len(multitrack.tracks))], mode='max', program=0,
                                remove_merged=True)

        pianoroll_array = (multitrack.tracks[0].pianoroll > 0.0).astype('bool')

        if (pianoroll_array.shape[0] == 0) or (pianoroll_array.shape[1] != 128):
            raise Exception(
                "Shape of pianoroll array should be (timesteps, 128), where timesteps > 0. Encountered shape is " + str(
                    pianoroll_array.shape))

        self.array = pianoroll_array

    def get_multitrack(self):
        """
        Returns the pypianoroll Multitrack representation of the midi created from the pianoroll array. This track has
        one piano track with an assumed tempo of 120 and a beat resolution of 24.
        """

        track = Track(pianoroll=self.array, program=0, is_drum=False)

        m = Multitrack(tracks=[track], tempo=120, downbeat=None, beat_resolution=24)

        return Multitrack(tracks=[track], tempo=120, downbeat=None, beat_resolution=24)

    def play(self):
        """
        Play the notes represented in self.array as a midi audio output.
        """

        play_midi_from_file(multitrack=self.get_multitrack())

    def stretch(self, stretch_fraction):
        """
        stretch_fraction: float >= 0.0 indicating how much to stretch the pianoroll

        stratch_fraction = 1.0 returns the original pianoroll
        stretch_fraction < 1.0 shortens (speeds up) the pianoroll
        stretch_fraction > 1.0 lengthens (slows down) the pianoroll

        This method modifies self.array in place.
        """

        time_steps_in_original = self.array.shape[0]
        num_keys_in_original = self.array.shape[1]

        time_steps_in_stretched = round(time_steps_in_original * stretch_fraction)

        if time_steps_in_stretched == 0:
            raise Exception("Cannot have zero timesteps in stretched pianoroll.")

        stretched_pianoroll = np.zeros((time_steps_in_stretched, num_keys_in_original)).astype('bool')

        for stretched_time_step in range(time_steps_in_stretched):
            stretch_time_fraction = stretched_time_step / time_steps_in_stretched

            original_time_step = round(stretch_time_fraction * time_steps_in_original)

            original_time_step = min(original_time_step, time_steps_in_original - 1)

            stretched_pianoroll[stretched_time_step, :] = self.array[original_time_step, :]

        self.array = stretched_pianoroll

    def get_copy(self):
        """
        Returns copy of this pianoroll instance.
        """
        return Pianoroll(np_array=self.array.copy())

    def __getitem__(self, val):
        """
        val: A slice denoting what timesteps of the pianoroll to keep.

        A new pianoroll instance is returned with the requested slice.

        Example: p[10:20] returns a new pianoroll instance with the key state sets between 10 inclusive and 20 exclusive.
        """
        if isinstance(val, slice):
            return Pianoroll(self.array[val])
