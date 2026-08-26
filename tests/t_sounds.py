import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bells import sounds, config
sounds.ensure(config.sounds_dir())
for f in sorted(os.listdir(config.sounds_dir())):
    print(f, os.path.getsize(os.path.join(config.sounds_dir(), f)))
