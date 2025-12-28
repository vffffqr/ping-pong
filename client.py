import os
import json
import socket
import math
import threading
import time
import pygame
from pygame import gfxdraw

# --- НАЛАШТУВАННЯ ---
WIDTH, HEIGHT = 800, 600
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()
pygame.display.set_caption("Пінг-Понг")

ROOT = os.path.dirname(__file__)
ASSETS_DIR = os.path.join(ROOT, 'assets')
CONFIG_PATH = os.path.join(ROOT, 'config.json')

# --- Utility: config and asset generation ---

def load_config():
    default = {'player_name': 'Player', 'volume': 0.6, 'ball_skin': 'ball_skin_1.png', 'paddle_skin': 'paddle_skin_1.png'}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                default.update(data)
        except Exception:
            pass
    return default


def save_config(cfg):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def ensure_assets():
    # If assets are missing, try to generate them via the generator script
    needed = ['background.png', 'ball_skin_1.png', 'ball_skin_2.png', 'paddle_skin_1.png', 'paddle_skin_2.png', 'button.png', 'button_hover.png', 'click.wav', 'wall_hit.wav', 'platform_hit.wav']
    if not os.path.isdir(ASSETS_DIR):
        os.makedirs(ASSETS_DIR, exist_ok=True)
    missing = [f for f in needed if not os.path.exists(os.path.join(ASSETS_DIR, f))]
    if missing:
        gen = os.path.join(ASSETS_DIR, 'generate_assets.py')
        if os.path.exists(gen):
            try:
                print('Generating missing assets...')
                # Run generator in same process
                import runpy
                runpy.run_path(gen, run_name='__main__')
            except Exception as e:
                print('Asset generation failed:', e)
        else:
            print('Missing assets and no generator found:', missing)

# --- Asset loader ---

def load_image(name, size=None):
    path = os.path.join(ASSETS_DIR, name)
    if os.path.exists(path):
        img = pygame.image.load(path).convert_alpha()
        if size:
            img = pygame.transform.smoothscale(img, size)
        return img
    # fallback: generate simple surface
    surf = pygame.Surface(size or (20, 20), pygame.SRCALPHA)
    surf.fill((200, 50, 50))
    pygame.draw.rect(surf, (255, 255, 255), surf.get_rect(), 2)
    return surf


def load_sound(name):
    path = os.path.join(ASSETS_DIR, name)
    try:
        if os.path.exists(path):
            return pygame.mixer.Sound(path)
    except Exception:
        pass
    return None

# --- UI primitives ---

class Button:
    def __init__(self, rect, text, font, bg_img=None, hover_img=None, callback=None):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.bg_img = bg_img
        self.hover_img = hover_img
        self.callback = callback
        self.hovered = False

    def draw(self, surf):
        img = self.hover_img if self.hovered and self.hover_img else self.bg_img
        if img:
            surf.blit(pygame.transform.smoothscale(img, (self.rect.w, self.rect.h)), self.rect.topleft)
        else:
            col = (90, 90, 90) if self.hovered else (60, 60, 60)
            pygame.draw.rect(surf, col, self.rect)
            pygame.draw.rect(surf, (255, 255, 255), self.rect, 2)
        txt = self.font.render(self.text, True, (255, 255, 255))
        tr = txt.get_rect(center=self.rect.center)
        surf.blit(txt, tr)

    def handle_event(self, ev):
        if ev.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(ev.pos)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.rect.collidepoint(ev.pos):
                if self.callback:
                    self.callback()
                return True
        return False

# --- Particles for simple VFX ---

class Particle:
    def __init__(self, pos, vel, color, life=0.6):
        self.pos = list(pos)
        self.vel = list(vel)
        self.color = color
        self.life = life

    def update(self, dt):
        self.pos[0] += self.vel[0] * dt
        self.pos[1] += self.vel[1] * dt
        self.life -= dt

    def draw(self, surf):
        if self.life > 0:
            alpha = max(0, min(255, int(255 * (self.life / 0.6))))
            r = 3
            s = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*self.color, alpha), (r, r), r)
            surf.blit(s, (self.pos[0]-r, self.pos[1]-r))

# --- Main application ---

cfg = load_config()
ensure_assets()

# load images and sounds (scaled later as needed)
imgs = {
    'background': load_image('background.png', (WIDTH, HEIGHT)),
    'ball_skin_1': load_image('ball_skin_1.png', (20, 20)),
    'ball_skin_2': load_image('ball_skin_2.png', (20, 20)),
    'paddle_skin_1': load_image('paddle_skin_1.png', (20, 100)),
    'paddle_skin_2': load_image('paddle_skin_2.png', (20, 100)),
    'button': load_image('button.png', (200, 60)),
    'button_hover': load_image('button_hover.png', (200, 60)),
}

sounds = {
    'click': load_sound('click.wav'),
    'wall_hit': load_sound('wall_hit.wav'),
    'platform_hit': load_sound('platform_hit.wav'),
}
if pygame.mixer:
    try:
        # ensure mixer is initialized
        if not pygame.mixer.get_init():
            pygame.mixer.init()
    except Exception:
        pass
    for k, s in sounds.items():
        if s:
            s.set_volume(cfg.get('volume', 0.6))
    # background music (streamed)
    music_path = os.path.join(ASSETS_DIR, 'bg.ogg')
    if os.path.exists(music_path):
        try:
            pygame.mixer.music.load(music_path)
            pygame.mixer.music.set_volume(cfg.get('volume', 0.6))
            pygame.mixer.music.play(-1)
        except Exception:
            pass

font_main = pygame.font.Font(None, 36)
font_title = pygame.font.Font(None, 72)
font_small = pygame.font.Font(None, 24)

# global gameplay variables
game_state = {}
buffer = ''
client = None
my_id = None
receive_thread = None
running = True

particles = []

def spawn_hit_particles(x, y, kind='wall'):
    color = (255, 255, 0) if kind == 'wall' else (255, 200, 50)
    for i in range(10):
        ang = math.radians(i*36)
        vel = (math.cos(ang)*80, math.sin(ang)*80)
        particles.append(Particle((x, y), vel, color, life=0.4))

# --- Networking ---

def connect_to_server():
    global client, my_id, buffer, game_state, receive_thread
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(('localhost', 8080))
        data = client.recv(24).decode().strip()
        my_id = int(data)
        buffer = ''
        game_state = {}
        receive_thread = threading.Thread(target=receive, daemon=True)
        receive_thread.start()
        print('Connected as', my_id)
        return True
    except Exception as e:
        print('Connection failed:', e)
        return False


def receive():
    global buffer, game_state
    while running:
        try:
            data = client.recv(1024).decode()
            if not data:
                break
            buffer += data
            while "\n" in buffer:
                packet, buffer = buffer.split("\n", 1)
                if packet.strip():
                    game_state = json.loads(packet)
        except Exception:
            break
    print('Receive thread ended')

# --- UI screens ---

def main_menu():
    selected = None
    clicked_sound = sounds.get('click')

    def start_game_cb():
        nonlocal selected
        selected = 'play'
        if clicked_sound: clicked_sound.play()

    def settings_cb():
        nonlocal selected
        selected = 'settings'
        if clicked_sound: clicked_sound.play()

    def shop_cb():
        nonlocal selected
        selected = 'shop'
        if clicked_sound: clicked_sound.play()

    def exit_cb():
        nonlocal selected
        selected = 'exit'
        if clicked_sound: clicked_sound.play()

    btn_play = Button((WIDTH//2-100, 240, 200, 60), 'Грати', font_main, imgs['button'], imgs['button_hover'], start_game_cb)
    btn_settings = Button((WIDTH//2-100, 320, 200, 60), 'Налаштування', font_main, imgs['button'], imgs['button_hover'], settings_cb)
    btn_shop = Button((WIDTH//2-100, 400, 200, 60), 'Магазин скінів', font_main, imgs['button'], imgs['button_hover'], shop_cb)
    btn_exit = Button((WIDTH//2-100, 480, 200, 60), 'Вихід', font_main, imgs['button'], imgs['button_hover'], exit_cb)

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return 'exit'
            for b in (btn_play, btn_settings, btn_shop, btn_exit):
                if b.handle_event(ev):
                    pass
        # draw
        screen.blit(imgs['background'], (0, 0))
        title = font_title.render('Пінг-Понг', True, (255, 240, 100))
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 80))
        pygame.draw.rect(screen, (0,0,0,50), (WIDTH//2-220, 220, 440, 360), 0)
        for b in (btn_play, btn_settings, btn_shop, btn_exit):
            b.draw(screen)
        pygame.display.update()
        clock.tick(60)
        if selected:
            return selected


def settings_screen():
    selected = None
    input_rect = pygame.Rect(WIDTH//2-150, 260, 300, 44)
    player_name = cfg.get('player_name', 'Player')
    volume = cfg.get('volume', 0.6)
    active = False

    def save_cb():
        nonlocal selected
        cfg['player_name'] = player_name
        cfg['volume'] = volume
        save_config(cfg)
        if sounds.get('click'):
            sounds['click'].play()
        selected = 'menu'

    def back_cb():
        nonlocal selected
        selected = 'menu'
        if sounds.get('click'):
            sounds['click'].play()

    btn_save = Button((WIDTH//2-100, 360, 200, 60), 'Зберегти', font_main, imgs['button'], imgs['button_hover'], save_cb)
    btn_back = Button((WIDTH//2-320, 360, 200, 60), 'Назад', font_main, imgs['button'], imgs['button_hover'], back_cb)

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return 'exit'
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    selected = 'menu'
                if ev.key == pygame.K_BACKSPACE and active:
                    player_name = player_name[:-1]
                elif ev.key == pygame.K_RETURN and active:
                    active = False
                elif active and ev.unicode:
                    player_name += ev.unicode
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                active = input_rect.collidepoint(ev.pos)
            if ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 4:
                    volume = min(1.0, volume + 0.05)
                elif ev.button == 5:
                    volume = max(0.0, volume - 0.05)
            btn_save.handle_event(ev)
            btn_back.handle_event(ev)

        # draw
        screen.blit(imgs['background'], (0, 0))
        title = font_title.render('Налаштування', True, (255, 240, 100))
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 80))

        # name input
        pygame.draw.rect(screen, (255,255,255), input_rect, 2)
        txt = font_main.render(player_name, True, (255,255,255))
        screen.blit(txt, (input_rect.x+8, input_rect.y+8))
        hint = font_small.render('Ім`я гравця (клік + ввод)', True, (200,200,200))
        screen.blit(hint, (input_rect.x, input_rect.y-24))

        # volume
        vol_txt = font_main.render(f'Гучність: {int(volume*100)}%', True, (255,255,255))
        screen.blit(vol_txt, (WIDTH//2 - vol_txt.get_width()//2, 330))
        note = font_small.render('Колесо миші змінює гучність, або натисніть Зберегти', True, (180,180,180))
        screen.blit(note, (WIDTH//2 - note.get_width()//2, 420))

        btn_save.draw(screen)
        btn_back.draw(screen)
        pygame.display.update()
        clock.tick(60)
        # reflect volume
        cfg['volume'] = volume
        for s in sounds.values():
            if s:
                s.set_volume(volume)
        # update background music volume as well
        try:
            pygame.mixer.music.set_volume(volume)
        except Exception:
            pass
        if selected:
            return selected
        if btn_save.callback and btn_save.hovered and pygame.mouse.get_pressed()[0]:
            save_cb()


def shop_screen():
    selected_skin = cfg.get('ball_skin')
    selected_paddle = cfg.get('paddle_skin')

    ball_options = ['ball_skin_1.png', 'ball_skin_2.png']
    paddle_options = ['paddle_skin_1.png', 'paddle_skin_2.png']

    btn_back = Button((WIDTH//2-100, 520, 200, 60), 'Назад', font_main, imgs['button'], imgs['button_hover'], None)

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return 'exit'
            btn_back.handle_event(ev)
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if btn_back.rect.collidepoint(ev.pos):
                    cfg['ball_skin'] = selected_skin
                    cfg['paddle_skin'] = selected_paddle
                    save_config(cfg)
                    if sounds.get('click'):
                        sounds['click'].play()
                    return 'menu'
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                mx, my = ev.pos
                # pick a skin
                for i, name in enumerate(ball_options):
                    rect = pygame.Rect(120 + i*140, 200, 120, 120)
                    if rect.collidepoint(ev.pos):
                        selected_skin = name
                for i, name in enumerate(paddle_options):
                    rect = pygame.Rect(120 + i*140, 360, 60, 200)
                    if rect.collidepoint(ev.pos):
                        selected_paddle = name

        # draw
        screen.blit(imgs['background'], (0, 0))
        title = font_title.render('Магазин скінів', True, (255, 240, 100))
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 40))

        # balls
        btitle = font_main.render('М’ячі', True, (255,255,255))
        screen.blit(btitle, (120, 160))
        for i, name in enumerate(ball_options):
            s = load_image(name, (120, 120))
            rect = pygame.Rect(120 + i*140, 200, 120, 120)
            screen.blit(s, rect.topleft)
            if selected_skin == name:
                pygame.draw.rect(screen, (255, 215, 0), rect, 4)

        # paddles
        ptitle = font_main.render('Платформи', True, (255,255,255))
        screen.blit(ptitle, (120, 320))
        for i, name in enumerate(paddle_options):
            s = load_image(name, (60, 200))
            rect = pygame.Rect(120 + i*140, 360, 60, 200)
            screen.blit(s, rect.topleft)
            if selected_paddle == name:
                pygame.draw.rect(screen, (255, 215, 0), rect, 4)

        btn_back.draw(screen)
        pygame.display.update()
        clock.tick(60)

# --- Gameplay loop ---

def gameplay_loop():
    global game_state
    # connect if not connected
    if not connect_to_server():
        # show simple message
        start = time.time()
        while time.time() - start < 2:
            screen.fill((0,0,0))
            txt = font_main.render('Не вдалося підключитися до сервера', True, (255,0,0))
            screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2))
            pygame.display.update()
            clock.tick(60)
        return 'menu'

    # local skin selections
    ball_img = load_image(cfg.get('ball_skin', 'ball_skin_1.png'), (20, 20))
    paddle_img = load_image(cfg.get('paddle_skin', 'paddle_skin_1.png'), (20, 100))
    you_winner = None
    game_over_local = False

    while True:
        dt = clock.tick(60) / 1000.0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return 'exit'
        # input
        keys = pygame.key.get_pressed()
        if client:
            try:
                if keys[pygame.K_w]:
                    client.send(b'UP')
                elif keys[pygame.K_s]:
                    client.send(b'DOWN')
            except Exception:
                pass

        # update particles
        for p in particles[:]:
            p.update(dt)
            if p.life <= 0:
                particles.remove(p)

        # draw
        if imgs.get('background'):
            screen.blit(imgs['background'], (0,0))
        else:
            screen.fill((30,30,30))

        if game_state and 'countdown' in game_state and game_state['countdown'] > 0:
            countdown_text = font_title.render(str(game_state['countdown']), True, (255,255,255))
            screen.blit(countdown_text, (WIDTH//2 - 20, HEIGHT//2 - 30))
            pygame.display.update()
            continue

        if game_state and 'winner' in game_state and game_state['winner'] is not None:
            if you_winner is None:
                you_winner = (game_state['winner'] == my_id)
            if you_winner:
                text = 'Ти переміг!'
            else:
                text = 'Пощастить наступним разом!'
            win_text = font_title.render(text, True, (255, 215, 0))
            screen.blit(win_text, (WIDTH//2 - win_text.get_width()//2, HEIGHT//2 - 40))
            tips = font_main.render('Натисніть ESC щоб вийти у меню', True, (255,255,255))
            screen.blit(tips, (WIDTH//2 - tips.get_width()//2, HEIGHT//2 + 40))
            pygame.display.update()
            if pygame.key.get_pressed()[pygame.K_ESCAPE]:
                return 'menu'
            continue

        if game_state:
            # paddles
            p0_y = game_state['paddles']['0']
            p1_y = game_state['paddles']['1']
            # left
            screen.blit(paddle_img, (20, p0_y))
            # right
            screen.blit(paddle_img, (WIDTH - 40, p1_y))
            # ball
            bx, by = game_state['ball']['x'], game_state['ball']['y']
            screen.blit(ball_img, (bx-10, by-10))
            # score
            score_text = font_main.render(f"{game_state['scores'][0]} : {game_state['scores'][1]}", True, (255, 255, 255))
            screen.blit(score_text, (WIDTH // 2 -25, 20))

            # handle sound events and vfx
            sev = game_state.get('sound_event')
            if sev:
                s = sounds.get(sev)
                if s:
                    s.play()
                if sev == 'wall_hit':
                    spawn_hit_particles(bx, by, kind='wall')
                elif sev == 'platform_hit':
                    spawn_hit_particles(bx, by, kind='platform')

        else:
            waiting_text = font_main.render('Очікування гравців...', True, (255, 255, 255))
            screen.blit(waiting_text, (WIDTH // 2 - 25, 20))

        # draw particles
        for p in particles:
            p.draw(screen)

        pygame.display.update()

    # unreachable
    return 'menu'

# --- App State Machine ---

def run_app():
    state = 'menu'
    while True:
        if state == 'menu':
            res = main_menu()
            if res == 'play':
                state = 'play'
            elif res == 'settings':
                state = 'settings'
            elif res == 'shop':
                state = 'shop'
            elif res == 'exit':
                break
        elif state == 'settings':
            res = settings_screen()
            if res == 'exit':
                break
            state = 'menu'
        elif state == 'shop':
            res = shop_screen()
            if res == 'exit':
                break
            state = 'menu'
        elif state == 'play':
            res = gameplay_loop()
            if res == 'exit':
                break
            state = res or 'menu'

    try:
        pygame.mixer.music.stop()
    except Exception:
        pass
    pygame.quit()

if __name__ == '__main__':
    run_app()

