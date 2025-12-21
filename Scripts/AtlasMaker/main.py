import sys
import json
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QFileDialog,
    QVBoxLayout, QHBoxLayout, QInputDialog
)
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor
from PyQt5.QtCore import Qt, QRectF, QPointF


def snap(n, grid):
    return round(n / grid) * grid if grid > 1 else n


class ImageView(QWidget):
    def __init__(self):
        super().__init__()
        self.pixmap = None

        self.scale = 1.0
        self.offset = QPointF(0, 0)

        self.panning = False
        self.pan_start = QPointF()

        self.start = None
        self.current = None

        self.rects = {}
        self.grid = 16

    # ---------------------
    # Coordinate transforms
    # ---------------------
    def image_to_screen(self, p):
        return QPointF(
            p.x() * self.scale + self.offset.x(),
            p.y() * self.scale + self.offset.y()
        )

    def screen_to_image(self, p):
        return QPointF(
            (p.x() - self.offset.x()) / self.scale,
            (p.y() - self.offset.y()) / self.scale
        )
        
    def load(self, pixmap):
        self.pixmap = pixmap
        self.rects.clear()
        self.scale = 1.0
        self.offset = QPointF(0, 0)
        self.update()

    # ---------------------
    # Zoom toward cursor
    # ---------------------
    def wheelEvent(self, event):
        if not self.pixmap:
            return

        old_scale = self.scale
        mouse = QPointF(event.x(), event.y())
        mouse_img = self.screen_to_image(mouse)

        delta = event.angleDelta().y()
        if delta > 0:
            self.scale *= 1.13
        else:
            self.scale /= 1.13

        self.scale = max(0.2, min(10.0, self.scale))

        # adjust offset so zoom focuses at pointer
        mouse_new_screen = QPointF(
            mouse_img.x() * self.scale,
            mouse_img.y() * self.scale
        )
        self.offset += (mouse - (mouse_new_screen + self.offset))

        self.update()

    # ---------------------
    # Mouse events
    # ---------------------
    def mousePressEvent(self, event):
        if not self.pixmap:
            return

        if event.button() == Qt.MiddleButton:
            self.panning = True
            self.pan_start = QPointF(event.x(), event.y())
            return

        if event.button() == Qt.LeftButton:
            self.start = self.screen_to_image(event.pos())
            self.current = self.start

    def mouseMoveEvent(self, event):
        if self.panning:
            delta = QPointF(event.x(), event.y()) - self.pan_start
            self.offset += delta
            self.pan_start = QPointF(event.x(), event.y())
            self.update()
            return

        if not self.start:
            return

        pos = self.screen_to_image(event.pos())

        # SHIFT = square
        if QApplication.keyboardModifiers() & Qt.ShiftModifier:
            dx = pos.x() - self.start.x()
            dy = pos.y() - self.start.y()
            size = max(abs(dx), abs(dy))
            pos = QPointF(
                self.start.x() + (size if dx >= 0 else -size),
                self.start.y() + (size if dy >= 0 else -size)
            )

        # Snap to grid
        pos = QPointF(
            snap(pos.x(), self.grid),
            snap(pos.y(), self.grid)
        )

        self.current = pos
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.panning = False
            return

        if not self.start or not self.current:
            return

        rect = self.make_rect(self.start, self.current)

        name, ok = QInputDialog.getText(self, "Sprite Name", "Enter name:")
        if ok and name:
            self.rects[name] = rect

        self.start = None
        self.current = None
        self.update()

    def make_rect(self, p1, p2):
        return QRectF(
            min(p1.x(), p2.x()),
            min(p1.y(), p2.y()),
            abs(p2.x() - p1.x()),
            abs(p2.y() - p1.y())
        )

    # ---------------------
    # Painting
    # ---------------------
    def paintEvent(self, event):
        if not self.pixmap:
            return

        painter = QPainter(self)

        # Draw image with offset + scale
        w = self.pixmap.width() * self.scale
        h = self.pixmap.height() * self.scale
        painter.drawPixmap(int(self.offset.x()), int(self.offset.y()),
                           int(w), int(h), self.pixmap)

        # Draw grid
        if self.grid > 1:
            painter.setPen(QPen(QColor(60, 60, 60), 1))

            # Determine visible area in image coordinates
            w = self.width()
            h = self.height()

            top_left_img = self.screen_to_image(QPointF(0, 0))
            bottom_right_img = self.screen_to_image(QPointF(w, h))

            # Compute grid-aligned start positions
            start_x = int(top_left_img.x() // self.grid * self.grid)
            end_x = int(bottom_right_img.x() + self.grid)

            start_y = int(top_left_img.y() // self.grid * self.grid)
            end_y = int(bottom_right_img.y() + self.grid)

            # Vertical lines
            x = start_x
            while x <= end_x:
                p1 = self.image_to_screen(QPointF(x, top_left_img.y()))
                p2 = self.image_to_screen(QPointF(x, bottom_right_img.y()))
                painter.drawLine(p1, p2)
                x += self.grid

            # Horizontal lines
            y = start_y
            while y <= end_y:
                p1 = self.image_to_screen(QPointF(top_left_img.x(), y))
                p2 = self.image_to_screen(QPointF(bottom_right_img.x(), y))
                painter.drawLine(p1, p2)
                y += self.grid

        # Green pen for rectangles
        painter.setPen(QPen(QColor(0, 255, 0), 2))

        # Draw saved rects
        for rect in self.rects.values():
            r = QRectF(
                rect.x() * self.scale + self.offset.x(),
                rect.y() * self.scale + self.offset.y(),
                rect.width() * self.scale,
                rect.height() * self.scale,
            )
            painter.drawRect(r)

        # Draw active drag rect
        if self.start and self.current:
            rect = self.make_rect(self.start, self.current)
            r = QRectF(
                rect.x() * self.scale + self.offset.x(),
                rect.y() * self.scale + self.offset.y(),
                rect.width() * self.scale,
                rect.height() * self.scale,
            )
            painter.drawRect(r)


class AtlasMaker(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Atlas Maker")

        self.image_view = ImageView()

        load_btn = QPushButton("Load Image")
        load_btn.clicked.connect(self.load_image)

        export_btn = QPushButton("Export JSON")
        export_btn.clicked.connect(self.export_json)

        grid_btn = QPushButton("Set Grid Size")
        grid_btn.clicked.connect(self.set_grid)

        top = QHBoxLayout()
        top.addWidget(load_btn)
        top.addWidget(export_btn)
        top.addWidget(grid_btn)

        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(self.image_view)
        self.setLayout(layout)

    def load_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load", "", "Images (*.png *.jpg)")
        if path:
            self.image_view.load(QPixmap(path))

    def export_json(self):
        atlas = {"sprites": {}}

        for name, rect in self.image_view.rects.items():
            atlas["sprites"][name] = {
                "x": int(rect.x()),
                "y": int(rect.y()),
                "w": int(rect.width()),
                "h": int(rect.height())
            }

        path, _ = QFileDialog.getSaveFileName(self, "Save", "", "JSON (*.json)")
        if path:
            with open(path, "w") as f:
                json.dump(atlas, f, indent=4)

    def set_grid(self):
        val, ok = QInputDialog.getInt(self, "Grid Size", "Enter size:", value=self.image_view.grid)
        if ok:
            self.image_view.grid = max(1, val)


app = QApplication(sys.argv)
window = AtlasMaker()
window.resize(900, 700)
window.show()
sys.exit(app.exec_())
