import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bells import audio, config
p = os.path.join(config.sounds_dir(), 'bell_classic.wav')
alias, has_volume = audio._open(p)
print('open ->', alias, '| length_ms =', audio._length_ms(alias) if alias else 'n/a')
if alias:
    audio._send('close %s' % alias)
