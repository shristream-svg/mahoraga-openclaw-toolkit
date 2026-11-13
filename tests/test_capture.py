"""Synthetic providers/fake driver only; never opens a real microphone."""
import ctypes,struct,subprocess,tempfile,threading,unittest,wave
from pathlib import Path
from unittest.mock import Mock,patch
from mahoraga_toolkit import ptt_capture as ptt

PCM = struct.pack('<h', 1234) * 1600

class FakeWinMM:

    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail
        self.header = None

    def call(self, name):
        self.calls.append(name)
        return 1 if name == self.fail else 0

    def waveInOpen(self, handle, device, fmt, *args):
        self.format = ptt.WaveFormat.from_buffer_copy(ctypes.string_at(fmt, ctypes.sizeof(ptt.WaveFormat)))
        ctypes.cast(handle, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(123)
        return self.call('open')

    def waveInPrepareHeader(self, handle, header, size):
        self.header = ctypes.cast(header, ctypes.POINTER(ptt.WaveHeader)).contents
        return self.call('prepare')

    def waveInAddBuffer(self, *args):
        return self.call('buffer')

    def waveInStart(self, *args):
        return self.call('start')

    def waveInStop(self, *args):
        return self.call('stop')

    def waveInReset(self, *args):
        code = self.call('reset')
        if self.header is not None:
            ctypes.memmove(self.header.data, PCM, len(PCM))
            self.header.recorded = len(PCM)
            self.header.flags |= 1
        return code

    def waveInUnprepareHeader(self, *args):
        return self.call('unprepare')

    def waveInClose(self, *args):
        return self.call('close')

class CaptureTests(unittest.TestCase):

    def test_no_explicit_invocation_means_no_provider_or_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'no.wav'
            provider = Mock(side_effect=AssertionError('Must not access microphone'))
            r = ptt.record_ptt(p, provider=provider)
            self.assertFalse(r['ok'])
            self.assertFalse(p.exists())
            provider.assert_not_called()

    def test_nonempty_pcm_wav_has_independent_sample_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'capture.wav'
            r = ptt.record_ptt(p, 1, user_invoked=True, provider=lambda *_: PCM)
            self.assertTrue(r['ok'])
            self.assertEqual(r['result']['frames'], 1600)
            with wave.open(str(p), 'rb') as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 16000))
                self.assertEqual(w.readframes(1600), PCM)
            self.assertGreater(p.stat().st_size, 44)

    def test_empty_and_odd_pcm_are_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            for data in (b'', b'\x00', None):
                with self.subTest(data=data):
                    p = Path(tmp) / 'invalid.wav'
                    r = ptt.record_ptt(p, 1, user_invoked=True, provider=lambda *_, data=data: data)
                    self.assertFalse(r['ok'])
                    self.assertFalse(r['saved'])
                    self.assertFalse(p.exists())

    def test_header_only_wav_is_not_a_recording(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'header.wav'
            with wave.open(str(p), 'wb') as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
            with self.assertRaises(ptt.CaptureFailure):
                ptt.validate_wav(p)

    def test_cancel_before_and_during_provider_never_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'cancel.wav'
            event = threading.Event()
            event.set()
            provider = Mock()
            r = ptt.record_ptt(p, 1, user_invoked=True, provider=provider, cancel_event=event)
            self.assertEqual(r['status'], 'cancelled')
            provider.assert_not_called()
            event.clear()

            def cancelling(*_):
                event.set()
                return PCM
            r = ptt.record_ptt(p, 1, user_invoked=True, provider=cancelling, cancel_event=event)
            self.assertEqual(r['status'], 'cancelled')
            self.assertFalse(p.exists())

    def test_existing_output_preserved_and_provider_not_started(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'existing.wav'
            p.write_bytes(b'ORIGINAL')
            provider = Mock()
            r = ptt.record_ptt(p, 1, user_invoked=True, provider=provider)
            self.assertFalse(r['ok'])
            self.assertEqual(p.read_bytes(), b'ORIGINAL')
            provider.assert_not_called()

    def test_device_and_process_provider_failures_return_no_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            for failure in (ptt.CaptureFailure('CAPTURE_DEVICE_START_FAILED'), subprocess.CalledProcessError(1, ['synthetic-recorder']), RuntimeError('provider process failed'), KeyboardInterrupt()):
                p = Path(tmp) / 'failed.wav'
                r = ptt.record_ptt(p, 1, user_invoked=True, provider=Mock(side_effect=failure))
                self.assertFalse(r['ok'])
                self.assertFalse(r['saved'])
                self.assertFalse(p.exists())

    def test_invalid_duration_does_not_start_capture(self):
        for duration in (0, 61, -1, True, '10'):
            provider = Mock()
            r = ptt.record_ptt('unused.wav', duration, user_invoked=True, provider=provider)
            self.assertFalse(r['ok'])
            provider.assert_not_called()

    def test_native_buffer_pipeline_and_cleanup_using_fake_driver(self):
        fake = FakeWinMM()
        times = iter([0, 2])
        data = ptt.capture_pcm_windows(1, api=fake, clock=lambda: next(times), sleeper=lambda _: None)
        self.assertEqual(data, PCM)
        self.assertEqual(fake.calls, ['open', 'prepare', 'buffer', 'start', 'stop', 'reset', 'reset', 'unprepare', 'close'])
        self.assertEqual(ctypes.sizeof(ptt.WaveFormat), 18)
        self.assertEqual(fake.format.rate, 16000)
        self.assertEqual(fake.format.bits, 16)

    def test_native_start_error_resets_unprepares_and_closes(self):
        fake = FakeWinMM(fail='start')
        with self.assertRaises(ptt.CaptureFailure):
            ptt.capture_pcm_windows(1, api=fake)
        self.assertEqual(fake.calls[-3:], ['reset', 'unprepare', 'close'])

    def test_native_cancel_stops_device_and_releases_buffer_without_success(self):
        fake = FakeWinMM()
        event = threading.Event()
        with self.assertRaisesRegex(ptt.CaptureFailure, 'CAPTURE_CANCELLED'):
            ptt.capture_pcm_windows(1, event, api=fake, clock=lambda: 0, sleeper=lambda _: event.set())
        self.assertEqual(fake.calls[-3:], ['reset', 'unprepare', 'close'])
