import os
import math
import wave
import struct
import pygame

pygame.init()
WIDTH, HEIGHT = 800, 600
assets = os.path.dirname(__file__)

# helper to save surface to png

def save_surface(name, surf):
    path = os.path.join(assets, name)
    pygame.image.save(surf, path)
    print('Saved', path)


# background: diagonal stripes
bg = pygame.Surface((WIDTH, HEIGHT))
for x in range(0, WIDTH, 40):
    color = (20 + (x % 80), 40 + (x % 60), 80)
    pygame.draw.rect(bg, color, (x, 0, 40, HEIGHT))
save_surface('background.png', bg)

# ball skins
for i, color in enumerate([(255, 255, 255), (255, 200, 0), (0, 200, 255)], start=1):
    s = pygame.Surface((40, 40), pygame.SRCALPHA)
    pygame.draw.circle(s, color, (20, 20), 18)
    pygame.draw.circle(s, (255, 255, 255, 60), (14, 14), 6)
    pygame.draw.circle(s, (0, 0, 0, 50), (26, 26), 4)
    save_surface(f'ball_skin_{i}.png', s)

# paddle skins
for i, color in enumerate([(0, 200, 0), (200, 0, 255)], start=1):
    s = pygame.Surface((20, 100), pygame.SRCALPHA)
    for y in range(0, 100, 5):
        shade = max(0, min(255, color[0] - y//2))
        pygame.draw.rect(s, (shade, color[1], color[2]), (0, y, 20, 5))
    pygame.draw.rect(s, (255, 255, 255, 40), (2, 2, 16, 96), 2)
    save_surface(f'paddle_skin_{i}.png', s)

# buttons
btn = pygame.Surface((200, 60), pygame.SRCALPHA)
btn.fill((60, 60, 60))
pygame.draw.rect(btn, (220, 220, 220), (0, 0, 200, 60), 3)
save_surface('button.png', btn)

btnh = pygame.Surface((200, 60), pygame.SRCALPHA)
btnh.fill((90, 90, 90))
pygame.draw.rect(btnh, (255, 255, 255), (0, 0, 200, 60), 3)
save_surface('button_hover.png', btnh)

# small helper to create a tone wav

def make_tone(filename, freq=440.0, duration=0.12, volume=0.5, sample_rate=44100):
    n_samples = int(sample_rate * duration)
    wav_file = wave.open(os.path.join(assets, filename), 'w')
    wav_file.setparams((1, 2, sample_rate, n_samples, 'NONE', 'not compressed'))

    for i in range(n_samples):
        t = float(i) / sample_rate
        val = int(volume * 32767.0 * math.sin(2.0 * math.pi * freq * t))
        wav_file.writeframes(struct.pack('<h', val))

    wav_file.close()
    print('Saved', filename)

make_tone('click.wav', 900.0, 0.06)
make_tone('wall_hit.wav', 500.0, 0.12)
make_tone('platform_hit.wav', 700.0, 0.12)

print('Asset generation complete.')
