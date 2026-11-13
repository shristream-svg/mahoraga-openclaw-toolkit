"""Explicit-invocation local PCM capture; no import-time device access or daemon.

Windows waveform API reference:
https://learn.microsoft.com/en-us/windows/win32/multimedia/managing-waveform-audio-recording
Prefer the existing OpenClaw voice controls when configured. This module is the
existing CLI PTT fallback and passes validated local WAVs to the existing bridge.
"""
import ctypes
import hashlib
import os
from pathlib import Path
import time
import wave

RATE=16000
class CaptureFailure(Exception):
    def __init__(self,code):self.code=code;super().__init__(code)

class WaveFormat(ctypes.Structure):
    _pack_=1
    _fields_=[('format',ctypes.c_uint16),('channels',ctypes.c_uint16),('rate',ctypes.c_uint32),('average',ctypes.c_uint32),('align',ctypes.c_uint16),('bits',ctypes.c_uint16),('extra',ctypes.c_uint16)]
class WaveHeader(ctypes.Structure):
    _fields_=[('data',ctypes.c_void_p),('length',ctypes.c_uint32),('recorded',ctypes.c_uint32),('user',ctypes.c_size_t),('flags',ctypes.c_uint32),('loops',ctypes.c_uint32),('next',ctypes.c_void_p),('reserved',ctypes.c_size_t)]

def _winmm():
    if os.name!='nt':raise CaptureFailure('WINDOWS_CAPTURE_UNAVAILABLE')
    api=ctypes.WinDLL('winmm')
    api.waveInOpen.argtypes=[ctypes.POINTER(ctypes.c_void_p),ctypes.c_uint32,ctypes.POINTER(WaveFormat),ctypes.c_size_t,ctypes.c_size_t,ctypes.c_uint32]
    api.waveInOpen.restype=ctypes.c_uint32
    for name in ('waveInPrepareHeader','waveInAddBuffer','waveInUnprepareHeader'):
        f=getattr(api,name);f.argtypes=[ctypes.c_void_p,ctypes.POINTER(WaveHeader),ctypes.c_uint32];f.restype=ctypes.c_uint32
    for name in ('waveInStart','waveInStop','waveInReset','waveInClose'):
        f=getattr(api,name);f.argtypes=[ctypes.c_void_p];f.restype=ctypes.c_uint32
    return api

def capture_pcm_windows(duration,cancel_event=None,*,api=None,clock=time.monotonic,sleeper=time.sleep):
    """Capture one bounded PCM buffer. Only record_ptt's confirmed path calls this."""
    if cancel_event is not None and cancel_event.is_set():raise CaptureFailure('CAPTURE_CANCELLED')
    api=api if api is not None else _winmm()
    handle=ctypes.c_void_p()
    fmt=WaveFormat(1,1,RATE,RATE*2,2,16,0)
    data=ctypes.create_string_buffer(int(duration*RATE)*2)
    header=WaveHeader(ctypes.cast(data,ctypes.c_void_p),len(data),0,0,0,0,None,0)
    prepared=False;opened=False
    def check(code,stage):
        if code!=0:raise CaptureFailure('CAPTURE_DEVICE_'+stage+'_FAILED')
    try:
        check(api.waveInOpen(ctypes.byref(handle),0xFFFFFFFF,ctypes.byref(fmt),0,0,0),'OPEN');opened=True
        check(api.waveInPrepareHeader(handle,ctypes.byref(header),ctypes.sizeof(header)),'PREPARE');prepared=True
        check(api.waveInAddBuffer(handle,ctypes.byref(header),ctypes.sizeof(header)),'BUFFER')
        check(api.waveInStart(handle),'START')
        deadline=clock()+duration
        while not (header.flags&1) and clock()<deadline:
            if cancel_event is not None and cancel_event.is_set():raise CaptureFailure('CAPTURE_CANCELLED')
            sleeper(0.02)
        check(api.waveInStop(handle),'STOP')
        check(api.waveInReset(handle),'RESET')
        if cancel_event is not None and cancel_event.is_set():raise CaptureFailure('CAPTURE_CANCELLED')
        if header.recorded>len(data):raise CaptureFailure('CAPTURE_INVALID_BUFFER')
        return data.raw[:header.recorded]
    finally:
        if opened:
            # Reset returns queued buffers before unprepare/close, even on failure.
            api.waveInReset(handle)
            if prepared:api.waveInUnprepareHeader(handle,ctypes.byref(header),ctypes.sizeof(header))
            api.waveInClose(handle)

def validate_wav(path):
    """Independent container/readback check; never calls a device or STT model."""
    with wave.open(str(path),'rb') as audio:
        if (audio.getnchannels(),audio.getsampwidth(),audio.getframerate(),audio.getcomptype())!=(1,2,RATE,'NONE'):
            raise CaptureFailure('CAPTURE_INVALID_WAV_FORMAT')
        count=audio.getnframes();samples=audio.readframes(count)
        if count<=0 or len(samples)!=count*2:raise CaptureFailure('CAPTURE_EMPTY_OR_TRUNCATED_AUDIO')
    return {'frames':count,'recordedDurationSeconds':count/RATE,'pcmSha256':hashlib.sha256(samples).hexdigest()}

def record_ptt(output,duration=10,*,user_invoked=False,provider=None,cancel_event=None):
    """Return an execution receipt. No capture until the explicit invocation gate."""
    def failure(code):return {'ok':False,'status':'cancelled' if code=='CAPTURE_CANCELLED' else 'failed','error':{'code':code},'saved':False}
    if user_invoked is not True:return failure('EXPLICIT_PTT_INVOCATION_REQUIRED')
    if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not 1<=duration<=60:return failure('CAPTURE_INVALID_DURATION')
    if cancel_event is not None and cancel_event.is_set():return failure('CAPTURE_CANCELLED')
    target=Path(output)
    if target.exists():return failure('CAPTURE_OUTPUT_EXISTS')
    created=False
    try:
        pcm=(provider or capture_pcm_windows)(duration,cancel_event)
        if cancel_event is not None and cancel_event.is_set():raise CaptureFailure('CAPTURE_CANCELLED')
        if not isinstance(pcm,bytes) or len(pcm)==0 or len(pcm)%2:raise CaptureFailure('CAPTURE_EMPTY_OR_INVALID_PCM')
        if len(pcm)>int(duration*RATE)*2:raise CaptureFailure('CAPTURE_INVALID_BUFFER')
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:
            created=True
            with wave.open(stream,'wb') as audio:
                audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(RATE);audio.writeframes(pcm)
        readback=validate_wav(target)
        if readback['pcmSha256']!=hashlib.sha256(pcm).hexdigest():raise CaptureFailure('CAPTURE_READBACK_MISMATCH')
        if cancel_event is not None and cancel_event.is_set():raise CaptureFailure('CAPTURE_CANCELLED')
        return {'ok':True,'status':'captured','saved':True,'result':{'path':str(target.resolve()),'requestedDurationSeconds':duration,**readback},'scope':'Audio bytes captured and WAV read back; speech/Hinglish accuracy is not established.'}
    except (KeyboardInterrupt,CaptureFailure,OSError,wave.Error) as exc:
        if created:target.unlink(missing_ok=True)
        code='CAPTURE_CANCELLED' if isinstance(exc,KeyboardInterrupt) else exc.code if isinstance(exc,CaptureFailure) else 'CAPTURE_DEVICE_OR_WRITE_FAILED'
        return failure(code)
    except Exception:
        if created:target.unlink(missing_ok=True)
        return failure('CAPTURE_PROVIDER_FAILED')
