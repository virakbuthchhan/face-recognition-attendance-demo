"""Generate original, gentle feedback tones. No third-party audio assets required."""
import math
import struct
import wave
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'kiosk/assets'
root.mkdir(exist_ok=True)
rate = 44100
for name, notes in [('success', [(659.25, .13), (880, .23)]), ('unknown', [(330, .17), (261.63, .22)])]:
    samples = []
    for frequency, duration in notes:
        count = int(rate * duration)
        for i in range(count):
            t = i / rate
            envelope = min(1, t / .015) * min(1, (duration-t) / .06) * math.exp(-2*t)
            signal = math.sin(2*math.pi*frequency*t) + .15*math.sin(4*math.pi*frequency*t)
            samples.append(int(9000 * envelope * signal))
        samples.extend([0] * int(.035*rate))
    with wave.open(str(root / f'{name}.wav'), 'wb') as output:
        output.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        output.writeframes(struct.pack('<'+'h'*len(samples), *samples))
