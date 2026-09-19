// Runs on the audio rendering thread. Converts each render quantum of mic audio
// (Float32, [-1, 1]) to Int16 PCM and posts it to the main thread for sending over
// the WebSocket. No resampling here -- the server is told the AudioContext's actual
// sample rate via the "start" message and configures Deepgram STT to match it.
class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channelData = inputs[0]?.[0];
    if (channelData && channelData.length > 0) {
      const int16 = new Int16Array(channelData.length);
      for (let i = 0; i < channelData.length; i++) {
        const s = Math.max(-1, Math.min(1, channelData[i]));
        int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      this.port.postMessage(int16.buffer, [int16.buffer]);
    }
    return true;
  }
}

registerProcessor("pcm-capture-processor", PcmCaptureProcessor);
