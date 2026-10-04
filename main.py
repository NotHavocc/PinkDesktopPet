import sys
import random
import os

# FUCKASS macOS bug, fuck you Tim Cook
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    bundle_dir = sys._MEIPASS
    
    qt_plugins_path = os.path.join(bundle_dir, 'PyQt6', 'Qt6', 'plugins')
    if os.path.exists(qt_plugins_path):
        os.environ['QT_PLUGIN_PATH'] = qt_plugins_path
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(qt_plugins_path, 'platforms')

from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QLabel, QWidget, QVBoxLayout, 
                             QSystemTrayIcon, QMenu, QDialog, QFormLayout, 
                             QSlider, QDoubleSpinBox, QCheckBox, QPushButton, QGroupBox, QListWidget, QStackedWidget, QHBoxLayout)
from PyQt6.QtCore import Qt, QSize, QTimer, QPoint, QUrl, QSettings, QObject, pyqtSignal, QThread
from PyQt6.QtGui import QMovie, QPixmap, QImageReader, QIcon, QColor, QCursor, QDesktopServices
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
import platform
import ctypes
import ctypes.util
import subprocess

BASE_DIR = Path(__file__).parent.resolve()

# full list of sprites, append if you put your own additional ones
# do NOT remove idle, run, left, right, up, down. as theyre essenital to the core movement functions
SPRITES = {
    'idle':       str(BASE_DIR / 'sprites' / 'idle.png'),
    'burnt':      str(BASE_DIR / 'sprites' / 'burnt.png'),
    'concert':    str(BASE_DIR / 'sprites' / 'concert.gif'),
    'shocked':    str(BASE_DIR / 'sprites' / 'shocked.png'),
    'sitting':    str(BASE_DIR / 'sprites' / 'sitting.gif'),
    'laugh':      str(BASE_DIR / 'sprites' / 'laugh.gif'),
    'laugh2':     str(BASE_DIR / 'sprites' / 'laugh2.gif'),
    'crying':     str(BASE_DIR / 'sprites' / 'crying.gif'),
    'overjoyed':  str(BASE_DIR / 'sprites' / 'overjoyed.gif'),
    'run':        str(BASE_DIR / 'sprites' / 'run.gif'),
    'left':       str(BASE_DIR / 'sprites' / 'walkleft.gif'),
    'right':      str(BASE_DIR / 'sprites' / 'walkright.gif'),
    'up':         str(BASE_DIR / 'sprites' / 'walkup.gif'),
    'down':       str(BASE_DIR / 'sprites' / 'walkdown.gif'),
    'explosion':  str(BASE_DIR / 'sprites' / 'explosion.gif'),
    'spin':       str(BASE_DIR / 'sprites' / 'spin.gif'),
    'dance':      str(BASE_DIR / 'sprites' / 'dance.gif'),
    'kazotsky':   str(BASE_DIR / 'sprites' / 'kazotsky.gif'),
}

#full list of audio
AUDIO = {
    'laugh':      str(BASE_DIR / 'audio' / 'laugh.wav'),
    'laugh2':     str(BASE_DIR / 'audio' / 'laugh2.wav'),
    'explosion':  str(BASE_DIR / 'audio' / 'explosion.wav'),
    'gasp':       str(BASE_DIR / 'audio' / 'gasp.wav'),
    'sad':        str(BASE_DIR / 'audio' / 'sad.wav'),
    'trip':       str(BASE_DIR / 'audio' / 'trip.wav'),
}

# for modders (if there are any), make sure that the sum of the numbers in the 3rd
# row are 100. those are the percentages of the specific animations appearing
IDLE_BEHAVIORS = [
    # (sprite, audio, chance)
    ("idle",      None,     40),   
    ("laugh",     "laugh",  15),
    ("laugh2",    "laugh2", 10),
    ("crying",    "sad",    10),
    ("kazotsky",  None,      5),
    ("overjoyed", None,      5),
    ("sitting",   None,      5),
    ("spin",      None,      5),
    ("dance",     None,      5),
]

# sum of chance should also be 100
MUSIC_BEHAVIORS = [
    # (sprite, audio, chance)
    ("kazotsky",None, 25),
    ("concert", None, 75),
]

TRAY_ICON_PATH = str(BASE_DIR / 'sprites' / 'icon.png') 

class FloatingMediaWindow(QWidget):
    closed = pyqtSignal(object)
    
    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.manager.settings_changed.connect(self.reload_settings)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")
        
        self.raise_()
        self.activateWindow()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.label = QLabel(self)
        self.label.setStyleSheet("background: transparent;")
        self.label.setScaledContents(False)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.label)

        self.movie = None
        self.original_size = QSize()
        self.current_native_size = QSize()
        self.size_locked = False
        self.pixel_scale = 1.0
        self.drag_enabled = True
        self.walk_speed = 2
        self.target_w = 0
        self.target_h = 0
        self.current_pixmap = None
        
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(0.5)
        
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)

        self.settings = QSettings("Pink", "DesktopPet")
        self.wandering_enabled = True
        self.sound_enabled = True

        self.state = 'idle'      
        self.idle_pos = self.pos() 
        self.direction = 'down'
        self.target_pos = self.pos()
        self.wandering = False
        self.is_dragging = False
        self.is_despawning = False
        
        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.decide_next_state)

        self.move_timer = QTimer(self)
        self.move_timer.timeout.connect(self.step_toward_target)
        
        self.setMouseTracking(True)
        self.mouse_history = []
        self.is_being_petted = False
        self.petting_cooldown_active = False
        self.base_pos = self.pos()
        self.shake_offset = 0
        
        self.explode_timer = QTimer(self)
        self.explode_timer.setSingleShot(True)
        self.explode_timer.timeout.connect(self.kaboom)
        
        self.petting_timeout = QTimer(self)
        self.petting_timeout.setSingleShot(True)
        self.petting_timeout.timeout.connect(self.end_petting)

        self.hover_timer = QTimer(self)
        self.hover_timer.timeout.connect(self.check_mouse_hover)
        self.hover_timer.start(50)
        
        particle_path = str(BASE_DIR / 'sprites' / 'heart.png')
        # i hope that the things im currently doing help
        # people in atleast some way. i love you all <3
        if os.path.exists(particle_path):
            self.particle_pixmap = QPixmap(particle_path).scaled(
                18, 18, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.FastTransformation
            )
        else:
            self.particle_pixmap = None

        self.particles = []
        self.particle_timer = QTimer(self)
        self.particle_timer.timeout.connect(self.update_particles)
        self.particle_timer.setInterval(50)
        
        self.overlay_label = QLabel(self)
        self.overlay_label.setStyleSheet("background: transparent;")
        self.overlay_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.overlay_movie = None
        self.last_overlay_frame = -1
        self.overlay_label.hide()
        
        self.is_music_playing = False
        self.music_timer = QTimer(self)
        self.music_timer.timeout.connect(self.do_music_behavior)
        
        self.music_detection_enabled = self.settings.value("music_detection_enabled", True, type=bool)
        self.music_detector = MusicDetectorThread()
        self.music_detector.music_changed.connect(self.on_music_state_changed)
        if self.music_detection_enabled:
            self.music_detector.start()

        self.load_settings()
        self.set_media(SPRITES['idle'])
        self.apply_scale()
        self.state_timer.start(random.randint(3000, 8000))

    def set_media(self, file_path):
        if self.movie:
            self.movie.stop()
            try:
                self.movie.frameChanged.disconnect(self._update_gif_frame)
            except TypeError:
                pass
            self.movie = None
        self.current_pixmap = None

        if file_path.lower().endswith('.gif'):
            reader = QImageReader(file_path)
            size = reader.size()
            
            if not size.isEmpty():
                self.current_native_size = size
                
                if not self.size_locked:
                    self.original_size = size
                    self.size_locked = True

            self.movie = QMovie(file_path)
            if not self.movie.isValid():
                print(f"error: invalid GIF file at {file_path}")
                return
            
            self.movie.frameChanged.connect(self._update_gif_frame)
            self.movie.start()
            self._update_gif_frame()
            
        else:
            pixmap = QPixmap(file_path)
            if pixmap.isNull():
                print(f"error: invalid image file at {file_path}")
                return

            if not pixmap.size().isEmpty():
                self.current_native_size = pixmap.size()

                if not self.size_locked:
                    self.original_size = pixmap.size()
                    self.size_locked = True
            
            self.current_pixmap = pixmap
            self._apply_static_pixmap()

        self.apply_scale()

    def _update_gif_frame(self):
        if not self.movie:
            return
        pixmap = self.movie.currentPixmap()
        scaled = pixmap.scaled(
            self.target_w, 
            self.target_h, 
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
        )
        self.label.setPixmap(scaled)

    def _apply_static_pixmap(self):
        if self.current_pixmap:
            scaled = self.current_pixmap.scaled(
                self.target_w, 
                self.target_h, 
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
            self.label.setPixmap(scaled)

    def apply_scale(self):
        if self.original_size.isEmpty() or self.current_native_size.isEmpty():
            return

        fixed_height = self.original_size.height() * self.pixel_scale
        aspect_ratio = self.current_native_size.width() / self.current_native_size.height()
        new_width = aspect_ratio * fixed_height

        self.target_w = max(10, int(round(new_width)))
        self.target_h = max(10, int(round(fixed_height)))

        self.resize(self.target_w, self.target_h)

        if self.movie:
            self._update_gif_frame()
        else:
            self._apply_static_pixmap()
    
    def play_sound(self, sound_key):
        if sound_key not in AUDIO:
            print(f"error: sound '{sound_key}' not found in directory")
            return
        
        file_path = AUDIO[sound_key]
        url = QUrl.fromLocalFile(file_path)
        
        self.player.setSource(url)
        self.player.play()
        
    def load_settings(self, apply_position=True):
        self.pixel_scale = self.settings.value("pixel_scale", 1.0, type=float)
        self.walk_speed = self.settings.value("walk_speed", 2, type=int)
        self.drag_enabled = self.settings.value("drag_enabled", True, type=bool)
        self.wandering_enabled = self.settings.value("wandering_enabled", True, type=bool)
        self.sound_enabled = self.settings.value("sound_enabled", True, type=bool)
        self.music_detection_enabled = self.settings.value("music_detection_enabled", True, type=bool)
        
        volume = self.settings.value("volume", 50, type=int)
        self.audio_output.setVolume(volume / 100.0 if self.sound_enabled else 0.0)
        
        if apply_position:
            base_x = self.settings.value("window_x", 100, type=int)
            base_y = self.settings.value("window_y", 100, type=int)
            self.move(base_x + random.randint(-100, 100), base_y + random.randint(-100, 100))
            
    def reload_settings(self):
        old_scale = self.pixel_scale
        old_music = self.music_detection_enabled
        self.load_settings(apply_position=False)
        if self.pixel_scale != old_scale:
            self.apply_scale()
        if self.music_detection_enabled != old_music:
            self.set_music_detection(self.music_detection_enabled)

    def save_settings(self):
        self.settings.setValue("pixel_scale", self.pixel_scale)
        self.settings.setValue("drag_enabled", self.drag_enabled)
        self.settings.setValue("wandering_enabled", self.wandering_enabled)
        self.settings.setValue("sound_enabled", self.sound_enabled)
        self.settings.setValue("music_detection_enabled", self.music_detection_enabled)
        
        vol = int(self.audio_output.volume() * 100)
        self.settings.setValue("volume", vol if vol > 0 else 50) 
                
        self.settings.setValue("window_x", self.pos().x())
        self.settings.setValue("window_y", self.pos().y())
        self.manager.notify_settings_changed()
        self.settings.sync()

    def closeEvent(self, event):
        self.music_detector.running = False
        self.music_detector.wait()
        self.save_settings()
        self.closed.emit(self)
        event.accept()
        
    def despawn(self):
        if self.is_despawning:
            return
        self.is_despawning = True

        self.state_timer.stop()
        self.move_timer.stop()
        self.hover_timer.stop()
        self.petting_timeout.stop()
        self.explode_timer.stop()
        self.wandering = False
        self.is_dragging = False

        self.kaboom()
        QTimer.singleShot(2000, self.close)

    def decide_next_state(self):
        if self.is_despawning:
            return
        if self.is_music_playing:
            self.set_media(SPRITES['concert'])
            return   
        if self.is_being_petted or self.is_dragging:
            self.state_timer.start(1000)
            return

        if not self.wandering_enabled and self.state == 'walking':
            self.move_timer.stop()
            self.go_idle(skip_special=True)
            return

        if self.state == 'walking':
            self.state_timer.start(1000)
            return

        if self.wandering_enabled and random.random() < 0.6:
            self.start_wander()
        else:
            self.go_idle()

    def go_idle(self, skip_special=False):
        self.state = 'idle'
        self.wandering = False
        self.idle_pos = self.pos()
        self.base_pos = self.pos()
        self.move_timer.stop()

        if self.is_music_playing:
            flip_the_coin = random.randint(1,4)
            if flip_the_coin == 1 or flip_the_coin == 2:
                self.set_media(SPRITES['concert'])
            elif flip_the_coin == 3 or flip_the_coin == 4:
                self.set_media(SPRITES['kazotsky'])
            else:
                print("how did you fail to flip a coin??? idiot idiot IDIOT!!!!!!")
        elif skip_special:
            self.set_media(SPRITES['idle'])
        else:
            weights = [b[2] for b in IDLE_BEHAVIORS]
            sprite_key, sound_key, _ = random.choices(IDLE_BEHAVIORS, weights=weights, k=1)[0]
            self.set_media(SPRITES.get(sprite_key, SPRITES['idle']))
            if sound_key:
                self.play_sound(sound_key)

        self.state_timer.start(random.randint(3000, 8000))

    def start_wander(self):
        if self.is_music_playing:
            return
        
        screen = QApplication.primaryScreen().geometry()
        max_x = screen.width() - self.width()
        max_y = screen.height() - self.height()

        self.target_pos = QPoint(
            random.randint(0, max(0, max_x)),
            random.randint(0, max(0, max_y))
        )

        current = self.pos()
        dx = self.target_pos.x() - current.x()
        dy = self.target_pos.y() - current.y()

        if abs(dx) > abs(dy):
            self.direction = 'right' if dx > 0 else 'left'
        else:
            self.direction = 'down' if dy > 0 else 'up'

        self.set_media(SPRITES.get(self.direction, SPRITES['idle']))

        self.state = 'walking'
        self.wandering = True
        self.move_timer.start(16)

        self.state_timer.start(random.randint(4000, 9000))
    
    def step_toward_target(self):
        current = self.pos()
        dx = self.target_pos.x() - current.x()
        dy = self.target_pos.y() - current.y()
        dist = (dx ** 2 + dy ** 2) ** 0.5

        if dist < 4 or dist <= self.walk_speed:
            self.move(self.target_pos)
            self.move_timer.stop()
            self.go_idle()
            return

        speed = self.walk_speed
        step_x = current.x() + int(speed * dx / dist)
        step_y = current.y() + int(speed * dy / dist)
        self.move(step_x, step_y)
        
    def spawn_particle(self):
        if not self.particle_pixmap:
            return
            
        label = QLabel(self)
        label.setPixmap(self.particle_pixmap)
        label.setStyleSheet("background: transparent;")
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        start_x = (self.width() // 2) + random.randint(-20, 20)
        start_y = (self.height() // 4) + random.randint(-10, 10)
        
        label.move(start_x, start_y)
        label.show()
        
        self.particles.append({
            'widget': label,
            'x': float(start_x),
            'y': float(start_y),
            'dx': random.uniform(-1.5, 1.5),
            'dy': random.uniform(-5.5, -2.5), 
            'life': 1.0, 
            'decay': random.uniform(0.03, 0.06)
        })

    def update_particles(self):
        if self.is_being_petted and random.random() < 0.5:
            self.spawn_particle()

        dead_particles = []
        for p in self.particles:
            p['x'] += p['dx']
            p['y'] += p['dy']
            p['life'] -= p['decay']
            
            if p['life'] <= 0:
                dead_particles.append(p)
            else:
                p['widget'].move(int(p['x']), int(p['y']))

        for p in dead_particles:
            p['widget'].deleteLater()
            self.particles.remove(p)
        
    def check_mouse_hover(self):
        if self.is_despawning or self.is_dragging or self.state == 'walking' or self.petting_cooldown_active:
            return
        
        global_pos = QCursor.pos()
        
        if self.geometry().contains(global_pos):
            local_y = global_pos.y() - self.pos().y()
            local_x = global_pos.x() - self.pos().x()

            if local_y < self.height() * 0.25:
                self.mouse_history.append(local_x)

                if len(self.mouse_history) >= 2:
                    dx = local_x - self.mouse_history[-2]
                    self.shake_offset += int(dx * 0.15) 
                    self.shake_offset = max(-5, min(5, self.shake_offset)) 
                    self.move(self.base_pos.x() + self.shake_offset, self.base_pos.y())

                if len(self.mouse_history) > 40:
                    self.mouse_history.pop(0)

                total_movement = sum(abs(self.mouse_history[i] - self.mouse_history[i-1]) for i in range(1, len(self.mouse_history)))

                if total_movement > 120:
                    self.trigger_petting()
                    self.mouse_history.clear()
            else:
                if self.shake_offset != 0:
                    self.shake_offset = int(self.shake_offset * 0.5) 
                    if abs(self.shake_offset) < 1:
                        self.shake_offset = 0
                    self.move(self.base_pos.x() + self.shake_offset, self.base_pos.y())
                self.mouse_history.clear()
        else:
            if self.shake_offset != 0:
                self.shake_offset = int(self.shake_offset * 0.5)
                if abs(self.shake_offset) < 1:
                    self.shake_offset = 0
                self.move(self.base_pos.x() + self.shake_offset, self.base_pos.y())
            self.mouse_history.clear()

    def mousePressEvent(self, event):
        if self.is_despawning or not self.drag_enabled:
            return
        self.music_timer.stop() 

        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.state_timer.stop()
            
            grab_sound = random.randint(1, 2)
            if grab_sound == 1:
                self.play_sound('gasp')
            else:
                self.play_sound('trip')
            self.set_media(SPRITES['run'])
            self.move_timer.stop()
            self.wandering = False
            self.state = 'idle'
            self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if not self.drag_enabled or not self.is_dragging:
            return

        move = event.globalPosition().toPoint() - self.drag_pos
        self.move(self.pos() + move)
        self.drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        if not self.drag_enabled or not self.is_dragging:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False      
            self.base_pos = self.pos()
            self.go_idle(skip_special=True)
        
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False      
            self.base_pos = self.pos()

            if self.is_music_playing:
                self.music_timer.start(random.randint(8000, 15000))
                self.do_music_behavior()
            else:
                self.go_idle(skip_special=True)
    
    def trigger_petting(self):
        if not self.is_being_petted:
            self.is_being_petted = True
            
            self.explode_timer.start(3000)
            self.set_media(SPRITES['shocked'])
            self.play_sound('gasp')
            
            if self.particle_pixmap:
                self.particle_timer.start()
        
        self.petting_timeout.start(2000)

    def end_petting(self):
        self.is_being_petted = False
        self.petting_cooldown_active = True
        self.explode_timer.stop()
        
        self.particle_timer.stop()
        for p in self.particles:
            p['widget'].deleteLater()
        self.particles.clear()
        
        self.base_pos = self.pos()
        self.go_idle(skip_special=True)
        
        QTimer.singleShot(4000, self.end_cooldown)
        
    def play_overlay_gif(self, gif_path):
        if self.overlay_movie:
            self.overlay_movie.stop()
            try:
                self.overlay_movie.frameChanged.disconnect(self.update_overlay_frame)
            except TypeError:
                pass

        self.overlay_movie = QMovie(gif_path)
        if not self.overlay_movie.isValid():
            return

        self.last_overlay_frame = -1
        
        self.overlay_movie.frameChanged.connect(self.update_overlay_frame)
        self.overlay_movie.start()
        self.overlay_label.show()
        self.overlay_label.raise_()
        
    def update_overlay_frame(self):
        if not self.overlay_movie:
            return
            
        current_frame = self.overlay_movie.currentFrameNumber()
        if current_frame < self.last_overlay_frame:
            self.overlay_movie.stop()
            self.hide_overlay()
            if self.is_despawning:
                self.close()
            return
            
        self.last_overlay_frame = current_frame
        pixmap = self.overlay_movie.currentPixmap()
        native_w = pixmap.width()
        native_h = pixmap.height()

        scale_factor = 4.0 * self.pixel_scale 
        
        scaled_w = int(native_w * scale_factor)
        scaled_h = int(native_h * scale_factor)

        scaled = pixmap.scaled(
            scaled_w, 
            scaled_h, 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.FastTransformation
        )
        
        x = (self.width() - scaled_w) // 2
        y = (self.height() - scaled_h) // 2
        
        self.overlay_label.setGeometry(x, y, scaled_w, scaled_h)
        self.overlay_label.setPixmap(scaled)
       
    def hide_overlay(self):
        if self.overlay_movie:
            self.overlay_movie.stop()
            try:
                self.overlay_movie.frameChanged.disconnect(self.update_overlay_frame)
            except TypeError:
                pass
        
        self.last_overlay_frame = -1
        self.overlay_label.hide()
        self.overlay_label.clear()
        
    def kaboom(self):
        self.particle_timer.stop()
        for p in self.particles:
            p['widget'].deleteLater()
        self.particles.clear()
        
        self.play_overlay_gif(SPRITES['explosion'])
        self.play_sound('explosion')        
        self.set_media(SPRITES['burnt'])

    def end_cooldown(self):
        self.petting_cooldown_active = False
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            
    def on_music_state_changed(self, is_playing):
        if self.is_despawning:
            return
        self.is_music_playing = is_playing

        if is_playing:
            self.state_timer.stop()
            self.move_timer.stop()
            self.wandering = False
            self.set_media(SPRITES['concert'])
        else:
            self.go_idle()

    def do_music_behavior(self):
        if not self.is_music_playing or self.is_despawning or self.is_dragging:
            return
            
        weights = [b[2] for b in MUSIC_BEHAVIORS]
        sprite_key, sound_key, _ = random.choices(MUSIC_BEHAVIORS, weights=weights, k=1)[0]
        
        if sprite_key in SPRITES:
            self.set_media(SPRITES[sprite_key])
        if sound_key:
            self.play_sound(sound_key)
            
    def set_music_detection(self, enabled):
        self.music_detection_enabled = bool(enabled)
        if self.music_detection_enabled:
            self.music_detector.running = True
            if not self.music_detector.isRunning():
                self.music_detector.start()
        else:
            self.music_detector.running = False
            self.music_detector.wait()
            if self.is_music_playing:
                self.is_music_playing = False
                self.go_idle()


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Pink Desktop Pet Settings, mew~!")
        self.setFixedSize(650, 450)

        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QListWidget {
                background-color: #1e1e1e;
                color: #ffffff;
                border: none;
                font-size: 14px;
                outline: none;
            }
            QListWidget::item {
                padding: 12px;
                border-bottom: 1px solid #3d3d3d;
            }
            QListWidget::item:selected {
                background-color: #ff8a90;
                color: #ffffff;
                font-weight: bold;
            }
            QListWidget::item:hover {
                background-color: #3d3d3d;
            }
            QGroupBox {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 15px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #aaaaaa;
            }
            QLabel {
                color: #ffffff;
                background-color: transparent;
            }
            QSlider::groove:horizontal {
                border: 1px solid #555555;
                height: 4px;
                background: #444444;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ff8a90;
                border: 1px solid #005a9e;
                width: 12px;
                margin: -4px 0;
                border-radius: 2px;
            }
            QDoubleSpinBox {
                background-color: #444444;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 4px;
                border-radius: 3px;
            }
            QCheckBox {
                color: #ffffff;
                background-color: transparent;
                spacing: 5px;
            }
            QPushButton {
                background-color: #ff8a90;
                color: #ffffff;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005a9e;
            }
            QPushButton#cancelBtn {
                background-color: #555555;
            }
            QPushButton#cancelBtn:hover {
                background-color: #666666;
            }
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(160)
        self.sidebar.addItems(["About", "Appearance", "Behavior", "Audio"])
        self.sidebar.currentRowChanged.connect(self.change_page)
        main_layout.addWidget(self.sidebar)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        
        self.content_stack = QStackedWidget()
        right_layout.addWidget(self.content_stack, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("cancelBtn")
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = QPushButton("Save and Close")
        self.save_button.clicked.connect(self.save_and_close)
        btn_layout.addWidget(self.cancel_button)
        btn_layout.addWidget(self.save_button)
        right_layout.addLayout(btn_layout)

        main_layout.addWidget(right_panel, 1)

        self.content_stack.addWidget(self.create_about_page())
        self.content_stack.addWidget(self.create_appearance_page(parent))
        self.content_stack.addWidget(self.create_behavior_page(parent))
        self.content_stack.addWidget(self.create_audio_page(parent))

        self.sidebar.setCurrentRow(0)

    def change_page(self, index):
        self.content_stack.setCurrentIndex(index)

    def create_about_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon_label = QLabel()
        icon_path = str(BASE_DIR / 'sprites' / 'icon.png') 
        icon_pixmap = QPixmap(icon_path)
        
        if not icon_pixmap.isNull():
            scaled_icon = icon_pixmap.scaled(
                128, 128, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.FastTransformation
            )
            icon_label.setPixmap(scaled_icon)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setStyleSheet("margin-bottom: 15px;")
            layout.addWidget(icon_label)
        
        title = QLabel("Pink Desktop Pet")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #ff8a90; margin-bottom: 5px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        version = QLabel("Version 2.3.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(version)
        
        desc = QLabel("a custom-made desktop pet engine that only shows the goat PINK \nCreated by nothavoc, 2026.")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #cccccc; margin-top: 20px; font-size: 14px;")
        layout.addWidget(desc)
        
        def make_link(text, url):
            lbl = QLabel(f'<a href="{url}" style="color: #ff8a90; text-decoration: none;">{text}</a>')
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("QLabel { margin-top: 8px; font-size: 14px; background: transparent; } QLabel:hover { color: #4da6ff; text-decoration: underline; }")
            lbl.linkActivated.connect(self.open_github_link)
            return lbl

        layout.addWidget(make_link("Check for Updates on GitHub", "https://github.com/NotHavocc/PinkDesktopPet/releases/latest"))
        layout.addWidget(make_link("My Website", "https://nothavoc.is-a.dev"))
        
        layout.addStretch()
        return page

    def create_appearance_page(self, parent):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        group = QGroupBox("Sprite Scale")
        form = QFormLayout()
        
        self.scale_spinbox = QDoubleSpinBox()
        self.scale_spinbox.setRange(0.1, 10.0)
        self.scale_spinbox.setDecimals(1)
        self.scale_spinbox.setSingleStep(0.5)
        self.scale_spinbox.setValue(1.0)
        if parent:
            self.scale_spinbox.setValue(parent.pixel_scale)
        self.scale_spinbox.valueChanged.connect(self.on_scale_changed)
        self.scale_spinbox.setSuffix("x")
        
        form.addRow("Scale:", self.scale_spinbox)
        group.setLayout(form)
        layout.addWidget(group)
        layout.addStretch()
        return page

    def create_behavior_page(self, parent):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        wander_group = QGroupBox("Wandering")
        wander_layout = QVBoxLayout()
        self.wander_checkbox = QCheckBox("Enable Wandering")
        self.wander_checkbox.setChecked(True)
        if parent:
            self.wander_checkbox.setChecked(parent.wandering_enabled)
        self.wander_checkbox.stateChanged.connect(self.on_wander_changed)
        wander_layout.addWidget(self.wander_checkbox)
        wander_group.setLayout(wander_layout)
        layout.addWidget(wander_group)
        
        # she has so much aura when speed is at 10 trust frfr
        speed_group = QGroupBox("Movement Speed")
        speed_layout = QFormLayout()
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 10)
        self.speed_slider.setValue(2)
        if parent:
            self.speed_slider.setValue(parent.walk_speed)
        self.speed_label = QLabel(str(self.speed_slider.value()))
        self.speed_slider.valueChanged.connect(lambda v: self.speed_label.setText(str(v)))
        speed_layout.addRow("Speed:", self.speed_slider)
        speed_layout.addRow("", self.speed_label)
        speed_group.setLayout(speed_layout)
        layout.addWidget(speed_group)
        
        interaction_group = QGroupBox("Interaction")
        interaction_layout = QVBoxLayout()
        
        self.drag_checkbox = QCheckBox("Enable Dragging")
        self.drag_checkbox.setChecked(True)
        if parent:
            self.drag_checkbox.setChecked(parent.drag_enabled)
        self.drag_checkbox.stateChanged.connect(self.on_drag_changed)
        
        interaction_layout.addWidget(self.drag_checkbox)
        interaction_group.setLayout(interaction_layout)
        layout.addWidget(interaction_group)
        
        music_group = QGroupBox("Music Reaction")
        music_layout = QVBoxLayout()
        self.music_checkbox = QCheckBox("Audio Detection (sing/dance when playing music)")
        self.music_checkbox.setChecked(True)
        if parent:
            self.music_checkbox.setChecked(parent.music_detection_enabled)
        self.music_checkbox.stateChanged.connect(self.on_music_changed)
        music_layout.addWidget(self.music_checkbox)
        music_group.setLayout(music_layout)
        layout.addWidget(music_group)
        
        layout.addStretch()
        return page

    def create_audio_page(self, parent):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        vol_group = QGroupBox("Volume")
        vol_layout = QFormLayout()
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        
        if parent and hasattr(parent, 'audio_output'):
            self.volume_slider.setValue(int(parent.audio_output.volume() * 100))
            
        self.volume_label = QLabel(str(self.volume_slider.value()) + "%")
        self.volume_slider.valueChanged.connect(lambda v: self.volume_label.setText(str(v) + "%"))
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        
        vol_layout.addRow("Volume:", self.volume_slider)
        vol_layout.addRow("", self.volume_label)
        vol_group.setLayout(vol_layout)
        layout.addWidget(vol_group)
        
        sound_group = QGroupBox("Sound Effects")
        sound_layout = QVBoxLayout()
        self.sound_checkbox = QCheckBox("Enable Sound Effects")
        self.sound_checkbox.setChecked(True)
        if parent:
            self.sound_checkbox.setChecked(parent.sound_enabled)
        self.sound_checkbox.stateChanged.connect(self.on_sound_changed)
        sound_layout.addWidget(self.sound_checkbox)
        sound_group.setLayout(sound_layout)
        layout.addWidget(sound_group)
        
        layout.addStretch()
        return page
    
    def open_github_link(self, url):
        QDesktopServices.openUrl(QUrl(url))

    def on_wander_changed(self, state):
        if self.parent():
            self.parent().wandering_enabled = bool(state)
    
    def on_drag_changed(self, state):
        if self.parent():
            self.parent().drag_enabled = bool(state)

    def on_sound_changed(self, state):
        if self.parent():
            self.parent().sound_enabled = bool(state)
            vol = self.parent().settings.value("volume", 50, type=int)
            vol_float = (vol / 100.0) if self.parent().sound_enabled else 0.0
            self.parent().audio_output.setVolume(vol_float)

    def on_volume_changed(self, value):
        self.volume_label.setText(str(value) + "%")
        if self.parent() and self.parent().sound_enabled:
            vol_float = value / 100.0
            self.parent().audio_output.setVolume(vol_float)

    def on_scale_changed(self, value):
        if self.parent():
            self.parent().pixel_scale = float(value)
            self.parent().apply_scale()
            
    def on_music_changed(self, state):
        if self.parent():
            self.parent().set_music_detection(bool(state))
            self.parent().save_settings()

    def save_and_close(self):
        if self.parent():
            self.parent().walk_speed = self.speed_slider.value()
            self.parent().save_settings()
        self.accept()
        

class AppManager(QObject):
    settings_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.settings = QSettings("Pink", "DesktopPet")
        self.pets = []
        self.setup_tray()

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon()
        if os.path.exists(TRAY_ICON_PATH):
            icon = QIcon(TRAY_ICON_PATH)
            if sys.platform == 'darwin':
                pixmap = icon.pixmap(32, 32)
                mask = pixmap.createMaskFromColor(QColor(0, 0, 0), Qt.MaskMode.MaskOutColor)
                pixmap.setMask(mask)
                icon = QIcon(pixmap)
                icon.setIsMask(True)
            if not icon.isNull():
                self.tray_icon.setIcon(icon)
        else:
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(100, 149, 237))
            self.tray_icon.setIcon(QIcon(pixmap))

        tray_menu = QMenu()
        tray_menu.addAction("Spawn Pet").triggered.connect(self.spawn_pet)
        tray_menu.addAction("Settings").triggered.connect(self.open_settings)
        tray_menu.addSeparator()
        
        self.pets_menu = tray_menu.addMenu("Active Pets")
        self.pets_menu.aboutToShow.connect(self.update_pets_menu)
        
        self.music_action = tray_menu.addAction("Music Detection: ON")
        self.music_action.triggered.connect(self.toggle_music_detection)
        self.update_music_action_text()
        
        tray_menu.addSeparator()
        tray_menu.addAction("Close All Pets").triggered.connect(self.close_all_pets)
        tray_menu.addAction("Quit").triggered.connect(self.quit_app)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def spawn_pet(self):
        pet = FloatingMediaWindow(self)
        self.pets.append(pet)
        pet.closed.connect(lambda p=pet: self.remove_pet(p))
        pet.show()

    def remove_pet(self, pet):
        if pet in self.pets:
            self.pets.remove(pet)
        if not self.pets:
            QApplication.quit()

    def open_settings(self):
        if self.pets:
            SettingsDialog(self.pets[0]).exec()

    def update_pets_menu(self):
        self.pets_menu.clear()
        if not self.pets:
            self.pets_menu.addAction("No pets").setEnabled(False)
            return
        for i, pet in enumerate(self.pets):
            action = self.pets_menu.addAction(f"Remove Pink #{i+1}")
            action.triggered.connect(lambda checked, p=pet: p.despawn())

    def close_all_pets(self):
        for pet in self.pets[:]:
            pet.despawn()

    def quit_app(self):
        for pet in self.pets[:]:
            pet.save_settings()
        QApplication.quit()

    def notify_settings_changed(self):
        self.settings_changed.emit()
    
    def toggle_music_detection(self):
        current = self.settings.value("music_detection_enabled", True, type=bool)
        self.settings.setValue("music_detection_enabled", not current)
        self.settings.sync()
        self.update_music_action_text()
        self.notify_settings_changed()

    def update_music_action_text(self):
        on = self.settings.value("music_detection_enabled", True, type=bool)
        self.music_action.setText("Music Detection: ON" if on else "Music Detection: OFF")

class MacAudioListener:
    # more complications for macOS, yippie. (sarcasm)
    # might keep this untested as of now, since idk how many ppl even use this with mac

    def __init__(self):
        self._ready = False
        try:
            path = ctypes.util.find_library('CoreAudio')
            self.ca = ctypes.cdll.LoadLibrary(
                path or '/System/Library/Frameworks/CoreAudio.framework/CoreAudio'
            )
            self._ready = True
        except Exception:
            self._ready = False

    @staticmethod
    def _cc(s):
        return (ord(s[0]) << 24) | (ord(s[1]) << 16) | (ord(s[2]) << 8) | ord(s[3])

    class _Addr(ctypes.Structure):
        _fields_ = [('mSelector', ctypes.c_uint32),
                    ('mScope',    ctypes.c_uint32),
                    ('mElement',  ctypes.c_uint32)]

    def is_playing(self):
        if not self._ready:
            return False
        try:
            glob = self._cc('glob')

            addr = self._Addr(self._cc('dOut'), glob, 0)
            dev  = ctypes.c_uint32()
            size = ctypes.c_uint32(4)
            if self.ca.AudioObjectGetPropertyData(ctypes.c_uint32(0), ctypes.byref(addr),
                                                  0, None, ctypes.byref(size), ctypes.byref(dev)) != 0:
                return False

            addr2   = self._Addr(self._cc('rsom'), glob, 0)
            running = ctypes.c_uint32()
            size2   = ctypes.c_uint32(4)
            if self.ca.AudioObjectGetPropertyData(dev, ctypes.byref(addr2),
                                                  0, None, ctypes.byref(size2), ctypes.byref(running)) != 0:
                return False
            return running.value == 1
        except Exception:
            return False

class MusicDetectorThread(QThread):
    music_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.running = True
        self.last_state = False
        self.mac_listener = MacAudioListener() if platform.system() == "Darwin" else None

    def run(self):
        yes = no = 0
        while self.running:
            try:
                raw = self.check_music()
            except Exception:
                raw = self.last_state

            if raw == self.last_state:
                yes = no = 0
            elif raw:
                yes += 1; no = 0
                if yes >= 2:
                    self.last_state = True
                    self.music_changed.emit(True)
                    yes = 0
            else:
                no += 1; yes = 0
                if no >= 2:
                    self.last_state = False
                    self.music_changed.emit(False)
                    no = 0

            self.msleep(1000)

    def check_music(self):
        system = platform.system()
        if system == "Darwin":
            return self._check_mac()
        elif system == "Windows":
            return self._check_win()
        return False

    def _check_mac(self):
        if self.mac_listener and self.mac_listener.is_playing():
            return True

        for app in ["Spotify", "Music"]:
            try:
                script = f'if application "{app}" is running then tell application "{app}" to return player state'
                result = subprocess.run(['osascript', '-e', script],
                                        capture_output=True, text=True, timeout=1)
                if 'playing' in result.stdout.lower():
                    return True
            except Exception:
                pass
        return False

    def _check_win(self):
        ps_script = (
            "Add-Type -AssemblyName System.Runtime.WindowsRuntime;"
            "$t = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Foundation, ContentType=WindowsRuntime];"
            "$m = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? { $_.Name -eq 'AsTask' -and $_.IsGenericMethod })[0].MakeGenericMethod($t).Invoke($null, @($t::RequestAsync()));"
            "if ($m.Wait(2000)) { $s = $m.Result.GetCurrentSession(); if ($s) { [int]$s.GetPlaybackInfo().PlaybackStatus } else { -1 } } else { -1 }"
        )
        try:
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps_script],
                capture_output=True, text=True, timeout=4,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )
            return result.stdout.strip() == '4'
        except Exception:
            return False


if __name__ == '__main__':
    app = QApplication(sys.argv)
    manager = AppManager()
    manager.spawn_pet()
    sys.exit(app.exec())