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
                             QSlider, QDoubleSpinBox, QCheckBox, QPushButton, QGroupBox)
from PyQt6.QtCore import Qt, QSize, QTimer, QPoint, QUrl, QSettings
from PyQt6.QtGui import QMovie, QPixmap, QImageReader, QIcon, QColor
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

BASE_DIR = Path(__file__).parent.resolve()

SPRITES = {
    'idle':       str(BASE_DIR / 'sprites' / 'idle.png'),
    'concert':    str(BASE_DIR / 'sprites' / 'concert.gif'),
    'laugh':      str(BASE_DIR / 'sprites' / 'laugh.gif'),
    'laugh2':     str(BASE_DIR / 'sprites' / 'laugh2.gif'),
    'crying':     str(BASE_DIR / 'sprites' / 'crying.gif'),
    'overjoyed':  str(BASE_DIR / 'sprites' / 'overjoyed.gif'),
    'run':        str(BASE_DIR / 'sprites' / 'run.gif'),
    'left':       str(BASE_DIR / 'sprites' / 'walkleft.gif'),
    'right':      str(BASE_DIR / 'sprites' / 'walkright.gif'),
    'up':         str(BASE_DIR / 'sprites' / 'walkup.gif'),
    'down':       str(BASE_DIR / 'sprites' / 'walkdown.gif'),
}

AUDIO = {
    'laugh':   str(BASE_DIR / 'audio' / 'laugh.wav'),
    'laugh2':  str(BASE_DIR / 'audio' / 'laugh2.wav'),
    'gasp':    str(BASE_DIR / 'audio' / 'gasp.wav'),
    'sad':     str(BASE_DIR / 'audio' / 'sad.wav'),
    'trip':    str(BASE_DIR / 'audio' / 'trip.wav'),
}

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
        layout.addWidget(self.label)

        self.movie = None
        self.original_size = QSize()
        self.current_native_size = QSize()
        self.size_locked = False
        self.pixel_scale = 1.0
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
        self.setup_system_tray()

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
        self.wandering_enabled = self.settings.value("wandering_enabled", True, type=bool)
        self.sound_enabled = self.settings.value("sound_enabled", True, type=bool)
        
        volume = self.settings.value("volume", 50, type=int)
        self.audio_output.setVolume(volume / 100.0 if self.sound_enabled else 0.0)
        
        x = self.settings.value("window_x", 100, type=int)
        y = self.settings.value("window_y", 100, type=int)
        self.move(x, y)

    def save_settings(self):
        self.settings.setValue("pixel_scale", self.pixel_scale)
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
        if self.is_dragging:
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
        self.move_timer.stop()
        
        if skip_special:
            self.set_media(SPRITES['idle'])
            self.state_timer.start(random.randint(3000, 8000))
            return
        
        special_sprite = random.randint(1,8)
         
        if special_sprite in (1, 2, 3):
            self.set_media(SPRITES['idle'])
        elif special_sprite == 4:
            self.set_media(SPRITES['concert'])
        elif special_sprite == 5:
            self.set_media(SPRITES['laugh'])
            self.play_sound('laugh')
        elif special_sprite == 6:
            self.set_media(SPRITES['laugh2'])
            self.play_sound('laugh2')
        elif special_sprite == 7:
            self.set_media(SPRITES['crying'])
            self.play_sound('sad')
        elif special_sprite == 8:
            self.set_media(SPRITES['overjoyed'])
        else:
            print("error")

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

        speed = 2
        step_x = current.x() + int(speed * dx / dist)
        step_y = current.y() + int(speed * dy / dist)
        self.move(step_x, step_y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.state_timer.stop()
            
            grab_sound = random.randint(1,2)
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
        if event.buttons() == Qt.MouseButton.LeftButton:
            move = event.globalPosition().toPoint() - self.drag_pos
            self.move(self.pos() + move)
            self.drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False      
            self.go_idle(skip_special=True)
    

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet("""
            QDialog {
                background-color: #f0f0f0;
                color: #000000;
            }
            QGroupBox {
                background-color: #f0f0f0;
                color: #000000;
                font-weight: bold;
                border: 2px solid #999999;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #000000;
            }
            QLabel {
                color: #000000;
                background-color: transparent;
            }
            QSlider::groove:horizontal {
                border: 1px solid #999999;
                height: 4px;
                background: #ffffff;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #0066cc;
                border: 1px solid #004499;
                width: 12px;
                margin: -4px 0;
                border-radius: 2px;
            }
            QSpinBox {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #999999;
                padding: 2px;
            }
            QCheckBox {
                color: #000000;
                background-color: transparent;
            }
            QPushButton {
                background-color: #e0e0e0;
                color: #000000;
                border: 1px solid #999999;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
        """)

        self.setWindowTitle("Pink Desktop Pet Settings, mew~!")
        self.setFixedSize(350, 450)
        
        self.setWindowFlags(
            Qt.WindowType.Dialog | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), Qt.GlobalColor.white)
        self.setPalette(palette)
        
        layout = QVBoxLayout(self)
        
        volume_group = QGroupBox("Audio")
        volume_layout = QFormLayout()
        
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        
        if parent and hasattr(parent, 'audio_output'):
            self.volume_slider.setValue(int(parent.audio_output.volume() * 100))
        
        self.volume_label = QLabel(f"{self.volume_slider.value()}%")
        self.volume_slider.valueChanged.connect(
            lambda v: self.volume_label.setText(f"{v}%")
        )
        
        volume_layout.addRow("Volume:", self.volume_slider)
        volume_layout.addRow("", self.volume_label)
        
        self.sound_checkbox = QCheckBox("Enable Sound Effects")
        self.sound_checkbox.setChecked(True)
        if parent:
            self.sound_checkbox.setChecked(parent.sound_enabled)
        volume_layout.addRow("", self.sound_checkbox)
        
        volume_group.setLayout(volume_layout)
        layout.addWidget(volume_group)

        appearance_group = QGroupBox("Appearance")
        appearance_layout = QFormLayout()
        
        self.scale_spinbox = QDoubleSpinBox()
        self.scale_spinbox.setRange(0.1, 10.0)
        self.scale_spinbox.setDecimals(1)
        self.scale_spinbox.setSingleStep(0.5)
        self.scale_spinbox.setValue(1.0) 
        
        appearance_layout.addRow("Sprite Scale:", self.scale_spinbox)
        appearance_group.setLayout(appearance_layout)
        layout.addWidget(appearance_group)

        behavior_group = QGroupBox("Behavior")
        behavior_layout = QFormLayout()
        
        self.wander_checkbox = QCheckBox("Enable Wandering")
        self.wander_checkbox.setChecked(True)
        if parent:
            self.wander_checkbox.setChecked(parent.wandering_enabled)
        
        behavior_layout.addRow("", self.wander_checkbox)
        behavior_group.setLayout(behavior_layout)
        layout.addWidget(behavior_group)

        info_label = QLabel("created by nothavoc, 2026.")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        layout.addStretch()

        button_layout = QVBoxLayout()
        
        self.save_button = QPushButton("Save and Close")
        self.save_button.clicked.connect(self.save_and_close)
        button_layout.addWidget(self.save_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)

    def on_wander_changed(self, state):
        if self.parent():
            self.parent().wandering_enabled = bool(state)
            if not self.parent().wandering_enabled:
                self.parent().move_timer.stop()
                self.parent().state_timer.stop()
                self.parent().state = 'idle'
                self.parent().wandering = False
                self.parent().go_idle(skip_special=True)
            else:
                if not self.parent().state_timer.isActive():
                    self.parent().state_timer.start(random.randint(3000, 8000))

    def on_sound_changed(self, state):
        if self.parent():
            self.parent().sound_enabled = bool(state)
            if not self.parent().sound_enabled:
                self.parent().audio_output.setVolume(0.0)
            else:
                vol = self.parent().settings.value("volume", 50, type=int)
                self.parent().audio_output.setVolume(vol / 100.0)

    def on_volume_changed(self, value):
        self.volume_label.setText(f"{value}%")
        if self.parent() and self.parent().sound_enabled:
            self.parent().audio_output.setVolume(value / 100.0)

    def on_scale_changed(self, value):
        if self.parent():
            self.parent().pixel_scale = float(value)
            self.parent().apply_scale()

    def save_and_close(self):
        if self.parent():
            self.parent().save_settings()
        self.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = FloatingMediaWindow()
    window.show()
    sys.exit(app.exec())