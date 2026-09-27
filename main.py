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
from PyQt6.QtCore import Qt, QSize, QTimer, QPoint, QUrl, QSettings
from PyQt6.QtGui import QMovie, QPixmap, QImageReader, QIcon, QColor, QCursor, QDesktopServices
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

BASE_DIR = Path(__file__).parent.resolve()

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
    'dance':       str(BASE_DIR / 'sprites' / 'dance.gif'),
}

AUDIO = {
    'laugh':      str(BASE_DIR / 'audio' / 'laugh.wav'),
    'laugh2':     str(BASE_DIR / 'audio' / 'laugh2.wav'),
    'explosion':  str(BASE_DIR / 'audio' / 'explosion.wav'),
    'gasp':       str(BASE_DIR / 'audio' / 'gasp.wav'),
    'sad':        str(BASE_DIR / 'audio' / 'sad.wav'),
    'trip':       str(BASE_DIR / 'audio' / 'trip.wav'),
}

# new random special sprite method
# modders (if there are any), please keep the sum of the chances to 100%
IDLE_BEHAVIORS = [
    #(sprite,        audio,    chance)
    ("idle",         None,       40),   
    ("concert",      None,       10),
    ("laugh",        "laugh",    10),
    ("laugh2",       "laugh2",   10),
    ("crying",       "sad",      10),
    ("overjoyed",    None,        5),
    ("sitting",      None,        5),
    ("spin",         None,        5),
    ("dance",        None,        5),
]

TRAY_ICON_PATH = str(BASE_DIR / 'sprites' / 'icon.png') 


class FloatingMediaWindow(QWidget):
    def __init__(self):
        super().__init__()
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

        self.load_settings()

        self.state = 'idle'      
        self.idle_pos = self.pos() 
        self.direction = 'down'
        self.target_pos = self.pos()
        self.wandering = False
        self.is_dragging = False
        
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

        self.hover_timer = QTimer(self)
        self.hover_timer.timeout.connect(self.check_mouse_hover)
        self.hover_timer.start(50)
        self.setup_system_tray()
        
        particle_path = str(BASE_DIR / 'sprites' / 'heart.png')
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
        
    def load_settings(self):
        self.pixel_scale = self.settings.value("pixel_scale", 1.0, type=float)
        self.walk_speed = self.settings.value("walk_speed", 2, type=int)
        self.drag_enabled = self.settings.value("drag_enabled", True, type=bool)
        self.wandering_enabled = self.settings.value("wandering_enabled", True, type=bool)
        self.sound_enabled = self.settings.value("sound_enabled", True, type=bool)
        
        volume = self.settings.value("volume", 50, type=int)
        self.audio_output.setVolume(volume / 100.0 if self.sound_enabled else 0.0)
        
        x = self.settings.value("window_x", 100, type=int)
        y = self.settings.value("window_y", 100, type=int)
        self.move(x, y)

    def save_settings(self):
        self.settings.setValue("pixel_scale", self.pixel_scale)
        self.settings.setValue("drag_enabled", self.drag_enabled)
        self.settings.setValue("wandering_enabled", self.wandering_enabled)
        self.settings.setValue("sound_enabled", self.sound_enabled)
        
        vol = int(self.audio_output.volume() * 100)
        self.settings.setValue("volume", vol if vol > 0 else 50) 
        
        self.settings.setValue("window_x", self.pos().x())
        self.settings.setValue("window_y", self.pos().y())
        self.settings.sync()

    def closeEvent(self, event):
        self.save_settings()
        event.accept()

    def setup_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        
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
        
        settings_action = tray_menu.addAction("Settings")
        settings_action.triggered.connect(self.open_settings_dialog)
        tray_menu.addSeparator()
        
        self.wander_action = tray_menu.addAction("Toggle Wandering")
        self.wander_action.triggered.connect(self.toggle_wandering)
        self.sound_action = tray_menu.addAction("Toggle Sound")
        self.sound_action.triggered.connect(self.toggle_sound)
        self.drag_action = tray_menu.addAction("Disable Dragging" if self.drag_enabled else "Enable Dragging")
        self.drag_action.triggered.connect(self.toggle_dragging)
        tray_menu.addSeparator()
        
        hide_action = tray_menu.addAction("Hide/Show")
        hide_action.triggered.connect(self.toggle_visibility)
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_app)
        
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_visibility()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
    
    def toggle_dragging(self):
        self.drag_enabled = not self.drag_enabled
        if self.drag_enabled:
            self.drag_action.setText("Disable Dragging")
        else:
            self.drag_action.setText("Enable Dragging")

        self.save_settings()

    def toggle_wandering(self):
        self.wandering_enabled = not self.wandering_enabled
        if not self.wandering_enabled:
            self.move_timer.stop()
            self.state_timer.stop()
            self.state = 'idle'        
            self.wandering = False   
            self.go_idle(skip_special=True)
        else:
            self.state_timer.start(random.randint(3000, 8000))

    def toggle_sound(self):
        self.sound_enabled = not self.sound_enabled
        if self.sound_enabled:
            vol = self.settings.value("volume", 50, type=int)
            self.audio_output.setVolume(vol / 100.0)
        else:
            self.audio_output.setVolume(0.0)

    def quit_app(self):
        self.save_settings()
        QApplication.quit()

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_settings_from_dialog(dialog)

    def apply_settings_from_dialog(self, dialog):
        self.audio_output.setVolume(dialog.volume_slider.value() / 100.0)
        
        old_scale = self.pixel_scale
        self.pixel_scale = dialog.scale_spinbox.value()
        if self.pixel_scale != old_scale:
            self.apply_scale()

        self.walk_speed = dialog.speed_slider.value()
        self.wandering_enabled = dialog.wander_checkbox.isChecked()
        if not self.wandering_enabled:
            self.move_timer.stop()
            self.state_timer.stop()
            self.state = 'idle'
            self.wandering = False
            self.go_idle(skip_special=True)
        else:
            if not self.state_timer.isActive():
                self.state_timer.start(random.randint(3000, 8000))
        
        self.sound_enabled = dialog.sound_checkbox.isChecked()
        if not self.sound_enabled:
            self.audio_output.setVolume(0.0)
            
        self.save_settings()

    def decide_next_state(self):
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
        # changed all of the if,elif toby fox undertale code ahh crap to a percentage system,
        # following PDPEngine philosophy o algo
        self.state = 'idle'
        self.wandering = False
        self.idle_pos = self.pos()
        self.base_pos = self.pos()
        self.move_timer.stop()
        
        if skip_special:
            self.set_media(SPRITES['idle'])
            self.state_timer.start(random.randint(3000, 8000))
            return
        
        weights = [behavior[2] for behavior in IDLE_BEHAVIORS]
        sprite_key, sound_key, _percent = random.choices(IDLE_BEHAVIORS, weights=weights, k=1)[0]
        
        if sprite_key in SPRITES:
            self.set_media(SPRITES[sprite_key])
        else:
            self.set_media(SPRITES['idle'])
        
        if sound_key:
            self.play_sound(sound_key)
        
        self.state_timer.start(random.randint(3000, 8000))

    def start_wander(self):
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

        if dist < 4:
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
        if self.is_dragging:
            return 
        if self.state == 'walking':
            return
        if self.petting_cooldown_active:
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

                total_movement = 0
                for i in range(1, len(self.mouse_history)):
                    total_movement += abs(self.mouse_history[i] - self.mouse_history[i-1])

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
        if not self.drag_enabled:
            return

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
        # nietzsche spoke of this.
        # no he didnt
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
        
        version = QLabel("Version 2.1.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(version)
        
        desc = QLabel("a custom-made desktop pet engine that only shows the goat PINK \nCreated by nothavoc, 2026.")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #cccccc; margin-top: 20px; font-size: 14px;")
        layout.addWidget(desc)
        
        github_url = "https://github.com/NotHavocc/PinkDesktopPet/releases/latest"
        
        link_label = QLabel(f'<a href="{github_url}" style="color: #ff8a90; text-decoration: none;">Check for Updates on GitHub</a>')
        link_label.setTextFormat(Qt.TextFormat.RichText)
        link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        link_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link_label.setStyleSheet("""
            QLabel {
                margin-top: 15px;
                font-size: 14px;
                background: transparent;
            }
            QLabel:hover {
                color: #a73c5c;
                text-decoration: underline;
            }
        """)
        link_label.linkActivated.connect(self.open_github_link)
        layout.addWidget(link_label)
        
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

    def save_and_close(self):
        if self.parent():
            self.parent().walk_speed = self.speed_slider.value()
            self.parent().save_settings()
        self.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = FloatingMediaWindow()
    window.show()
    sys.exit(app.exec())