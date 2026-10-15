"""Dialogs: labels editor, quick label / person editor, face naming, settings, sort-into-folders."""

from __future__ import annotations

import os
import shutil
from copy import deepcopy

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListView, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QRadioButton, QSlider, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from facet.i18n import LANGUAGES, language, tr
from facet.jev_client import JevClient, JevError
from facet.storage import MAX_REF_FACES, PALETTE, Label, Settings, faces_dir


def face_icon(name: str, size: int = 64) -> QIcon:
    pm = QPixmap(str(faces_dir() / name))
    if pm.isNull():
        return QIcon()
    return QIcon(pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation))


# --------------------------------------------------------------------------- labels table


class LabelsDialog(QDialog):
    def __init__(self, labels: list[Label], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Labels"))
        self.resize(900, 440)
        self.labels = deepcopy(labels)

        info = QLabel(tr(
            "Every label is a yes/no question for Jev. Refer to the image as <code>`photo`</code>. "
            "Jev returns a 0–100% probability; the label is applied when it reaches the threshold. "
            "Thresholds can be changed later without re-analysing. Labels 1–9 can also be toggled "
            "with the number keys. People (👤) are created by marking a face in the viewer."
        ))
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.RichText)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr("Name"), tr("Question for Jev (English works best)"),
                                              tr("Threshold %"), tr("Color")])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(0, 180)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.cellDoubleClicked.connect(self._cell_dbl)
        for l in self.labels:
            self._add_row(l)

        btns = QHBoxLayout()
        for text, fn in [(tr("New label"), self._new), (tr("Delete"), self._delete), ("↑", lambda: self._move(-1)),
                         ("↓", lambda: self._move(1))]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            btns.addWidget(b)
        btns.addStretch(1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(info)
        lay.addWidget(self.table, 1)
        lay.addLayout(btns)
        lay.addWidget(bb)

    def _add_row(self, l: Label, row: int | None = None) -> None:
        r = self.table.rowCount() if row is None else row
        self.table.insertRow(r)
        name = QTableWidgetItem(l.name)
        name.setData(Qt.ItemDataRole.UserRole, l)  # keeps id, kind, scope and reference faces
        if l.builtin:
            name.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            name.setToolTip(tr("Built-in label – used in every folder"))
        elif l.folder_only:
            name.setToolTip(tr("Only in: {folders}", folders=", ".join(l.folders)))
        if l.is_person and l.faces:
            name.setIcon(face_icon(l.faces[-1], 32))
        self.table.setItem(r, 0, name)
        if l.is_person:
            q = QTableWidgetItem(tr("👤 Person · {n} reference faces", n=len(l.faces)))
            q.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        else:
            q = QTableWidgetItem(l.question)
            if l.builtin:
                q.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.table.setItem(r, 1, q)
        spin = QSpinBox()
        spin.setRange(1, 99)
        spin.setSuffix(" %")
        spin.setValue(round(l.threshold * 100))
        self.table.setCellWidget(r, 2, spin)
        c = QTableWidgetItem("      ")
        c.setBackground(QColor(l.color))
        c.setData(Qt.ItemDataRole.UserRole, l.color)
        c.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.table.setItem(r, 3, c)

    def _cell_dbl(self, r: int, c: int) -> None:
        if c == 3:
            it = self.table.item(r, 3)
            col = QColorDialog.getColor(QColor(it.data(Qt.ItemDataRole.UserRole)), self, tr("Label color"))
            if col.isValid():
                it.setBackground(col)
                it.setData(Qt.ItemDataRole.UserRole, col.name())

    def _rows(self) -> list[Label]:
        out = []
        for r in range(self.table.rowCount()):
            name = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            if not name:
                continue
            orig: Label | None = self.table.item(r, 0).data(Qt.ItemDataRole.UserRole)
            l = deepcopy(orig) if orig else Label(name, "")
            if not l.builtin:
                l.name = name
            if not l.is_person and not l.builtin:
                l.question = self.table.item(r, 1).text().strip() if self.table.item(r, 1) else ""
            l.threshold = self.table.cellWidget(r, 2).value() / 100
            l.color = self.table.item(r, 3).data(Qt.ItemDataRole.UserRole)
            out.append(l)
        return out

    def _new(self) -> None:
        n = self.table.rowCount()
        self._add_row(Label(tr("New label"), "Is there ... in `photo`?", 0.5, PALETTE[n % len(PALETTE)]))
        self.table.editItem(self.table.item(n, 0))

    def _delete(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        builtin = [r for r in rows if (self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) or Label("", "")).builtin]
        if builtin:
            QMessageBox.information(self, tr("Labels"), tr("Built-in labels cannot be deleted – they are used in "
                                                           "every folder. You can change their threshold."))
        for r in rows:
            if r not in builtin:
                self.table.removeRow(r)

    def _move(self, d: int) -> None:
        r = self.table.currentRow()
        labels = self._rows()
        if not (0 <= r < len(labels)) or not (0 <= r + d < len(labels)):
            return
        labels[r], labels[r + d] = labels[r + d], labels[r]
        self._reload(labels)
        self.table.selectRow(r + d)

    def _reload(self, labels: list[Label]) -> None:
        self.table.setRowCount(0)
        for l in labels:
            self._add_row(l)

    def _accept(self) -> None:
        self.labels = self._rows()
        self.accept()


# --------------------------------------------------------------------------- quick label / person editor


class LabelEditDialog(QDialog):
    """Behind the sidebar's “+ New filter” button; also edits one label or person."""

    def __init__(self, label: Label | None, used_colors: list[str], parent=None,
                 scores: list[float] | None = None, total: int = 0) -> None:
        super().__init__(parent)
        person = label is not None and label.is_person
        self.scores = scores or []
        self.total = total
        self.orig_question = label.question if label else ""
        if label is None:
            self.setWindowTitle(tr("New filter / label"))
        else:
            self.setWindowTitle(tr("Edit person") if person else tr("Edit label"))
        self.setMinimumWidth(500)
        free = [c for c in PALETTE if c not in used_colors] or PALETTE
        self.label = deepcopy(label) if label else Label("", "", 0.5, free[0])
        self.removed_faces: list[str] = []

        self.name = QLineEdit(self.label.name)
        self.name.setPlaceholderText(tr("e.g. Dog in the photo"))
        self.question = QLineEdit(self.label.question)
        self.question.setPlaceholderText(tr("e.g. Is there a dog in `photo`?  (left empty: built from the name)"))
        self.thr = QSpinBox()
        self.thr.setRange(1, 99)
        self.thr.setSuffix(" %")
        self.thr.setValue(round(self.label.threshold * 100))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 99)
        self.slider.setValue(self.thr.value())
        self.slider.valueChanged.connect(self.thr.setValue)
        self.thr.valueChanged.connect(self.slider.setValue)
        self.thr.valueChanged.connect(self._preview)
        thr_row = QHBoxLayout()
        thr_row.addWidget(self.slider, 1)
        thr_row.addWidget(self.thr)
        self.preview = QLabel()
        self.preview.setObjectName("muted")
        self.preview.setWordWrap(True)
        self.tip = QLabel(tr("Tip: English yes/no questions about `photo` work best, e.g. “Are the bride and "
                             "groom kissing in `photo`?”"))
        self.tip.setWordWrap(True)
        self.tip.setStyleSheet("color:#d97706")
        self.question.textChanged.connect(self._preview)
        self.color_btn = QPushButton()
        self.color_btn.setFixedWidth(60)
        self.color_btn.clicked.connect(self._pick)
        self._set_color(self.label.color)

        builtin = bool(label is not None and label.builtin)
        form = QFormLayout()
        form.addRow(tr("Name:"), self.name)
        if builtin:
            self.name.setReadOnly(True)
            note = QLabel(tr("Built-in label – used in every folder. Its question is fixed; the threshold and colour "
                             "can be changed."))
            note.setWordWrap(True)
            note.setObjectName("muted")
            form.addRow("", note)
        elif not person:
            form.addRow(tr("Question for Jev:"), self.question)
            form.addRow("", self.tip)
        form.addRow(tr("Threshold:"), thr_row)
        form.addRow("", self.preview)
        form.addRow(tr("Color:"), self.color_btn)
        lay = QVBoxLayout(self)
        lay.addLayout(form)

        if person:
            self.faces = QListWidget()
            self.faces.setViewMode(QListView.ViewMode.IconMode)
            self.faces.setIconSize(QSize(72, 72))
            self.faces.setFixedHeight(110)
            self.faces.setMovement(QListView.Movement.Static)
            self.faces.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            for f in self.label.faces:
                it = QListWidgetItem(face_icon(f, 72), "")
                it.setData(Qt.ItemDataRole.UserRole, f)
                self.faces.addItem(it)
            rm = QPushButton(tr("Remove selected faces"))
            rm.clicked.connect(self._remove_faces)
            lay.addWidget(QLabel(tr("<b>Reference faces</b> – the newest {n} are sent to Jev. Add more by marking "
                                    "this person's face on other photos (different angles help).",
                                    n=MAX_REF_FACES)))
            lay.addWidget(self.faces)
            lay.addWidget(rm)
            hint = tr("Changing the reference faces re-checks this person on the next analysis.")
        else:
            hint = tr("Jev answers this yes/no question for every photo. English questions are the most accurate; "
                      "refer to the image as <code>`photo`</code>. For a new label only this one question is sent "
                      "for photos that were already analysed.")
        h = QLabel(hint)
        h.setWordWrap(True)
        h.setTextFormat(Qt.TextFormat.RichText)
        h.setStyleSheet("color:gray")
        lay.addWidget(h)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Add") if label is None else tr("Save"))
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._preview()

    def _preview(self, *_a) -> None:
        q = self.question.text().strip()
        foreign = any(ch in "áéíóöőúüűÁÉÍÓÖŐÚÜŰ" for ch in q) or (q and "`photo`" not in q)
        self.tip.setVisible(bool(foreign) and not self.label.is_person and not self.label.builtin)
        if not self.scores:
            self.preview.setText(tr("No AI results for this label in the current view yet."))
            return
        if q != self.orig_question:
            self.preview.setText(tr("The question changed – it will be re-checked on the next analysis "
                                    "(only this one question is sent)."))
            return
        thr = self.thr.value() / 100
        n = sum(1 for v in self.scores if v >= thr)
        self.preview.setText(tr("With this threshold: {n} of {total} photos · highest AI score: {top}%",
                                n=n, total=self.total, top=round(max(self.scores) * 100)))

    def _remove_faces(self) -> None:
        sel = self.faces.selectedItems()
        if len(sel) >= self.faces.count():
            QMessageBox.information(self, tr("Reference faces"), tr("A person needs at least one reference face."))
            return
        for it in sel:
            self.removed_faces.append(it.data(Qt.ItemDataRole.UserRole))
            self.faces.takeItem(self.faces.row(it))

    def _set_color(self, c: str) -> None:
        self.label.color = c
        self.color_btn.setStyleSheet(f"background:{c}; border-radius:4px; min-height:18px")

    def _pick(self) -> None:
        col = QColorDialog.getColor(QColor(self.label.color), self, tr("Label color"))
        if col.isValid():
            self._set_color(col.name())

    def _accept(self) -> None:
        if not self.name.text().strip():
            self.name.setFocus()
            return
        if not self.label.builtin:
            self.label.name = self.name.text().strip()
        if not self.label.is_person and not self.label.builtin:
            self.label.question = self.question.text().strip()
        else:
            self.label.faces = [f for f in self.label.faces if f not in self.removed_faces]
        self.label.threshold = self.thr.value() / 100
        self.accept()


# --------------------------------------------------------------------------- face naming


class PersonDialog(QDialog):
    """“Who is this?” – shown after a face was marked in the viewer."""

    def __init__(self, face_jpeg: bytes, people: list[Label], parent=None, show_search: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Who is this?"))
        self.setMinimumWidth(520)
        pm = QPixmap()
        pm.loadFromData(face_jpeg)
        img = QLabel()
        img.setPixmap(pm.scaled(180, 180, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation))
        img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name = QComboBox()
        self.name.setEditable(True)
        self.name.addItem("")
        for p in people:
            self.name.addItem(face_icon(p.faces[-1], 32) if p.faces else QIcon(), p.name)
        self.name.lineEdit().setPlaceholderText(tr("Name"))
        self.name.setCurrentIndex(0)
        self.name.setFocus()
        if show_search:  # no local face recognition for this face: Jev is the way to find the person
            self.search_now = QCheckBox(tr("Find this person in the current view now (uses the Jev API)"))
            self.search_now.setChecked(True)
        else:  # local recognition already finds frontal faces; Jev can add side views
            self.search_now = QCheckBox(tr("Also search with Jev AI for side views and small faces (uses the API)"))
            self.search_now.setChecked(False)
        hint = QLabel(tr("Pick an existing person to add another reference face (more angles = better results), "
                         "or type a new name."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:gray")
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Save face"))
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(img)
        lay.addWidget(self.name)
        lay.addWidget(hint)
        lay.addWidget(self.search_now)
        lay.addWidget(bb)

    def _accept(self) -> None:
        if self.name.currentText().strip():
            self.accept()

    def person_name(self) -> str:
        return self.name.currentText().strip()


# --------------------------------------------------------------------------- settings


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, thumb_cache_dir: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Settings"))
        self.settings = settings
        self.thumb_cache_dir = thumb_cache_dir
        self.setMinimumWidth(540)

        self.key = QLineEdit(settings.api_key())
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText(tr("TypeSafe API key (console.typesafe.ai/keys)"))
        self.key.setToolTip(tr("Stored in a private file in Facet's data folder – no keychain, no password prompts."))
        show = QPushButton(tr("Show"))
        show.setCheckable(True)
        show.toggled.connect(lambda on: self.key.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        test = QPushButton(tr("Test connection"))
        test.clicked.connect(self._test)
        key_row = QHBoxLayout()
        key_row.addWidget(self.key, 1)
        key_row.addWidget(show)

        self.lang = QComboBox()
        self.lang.addItem(tr("Automatic (system language)"), "")
        for code, name in LANGUAGES.items():
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(settings.get("language") or "")))
        self.model = QLineEdit(settings.get("model"))
        self.conc = QSpinBox()
        self.conc.setRange(1, 16)
        self.conc.setValue(settings.get("concurrency"))
        self.ai_side = QSpinBox()
        self.ai_side.setRange(320, 1568)
        self.ai_side.setSingleStep(64)
        self.ai_side.setSuffix(" px")
        self.ai_side.setValue(settings.get("ai_max_side"))
        self.threads = QSpinBox()
        self.threads.setRange(1, 8)
        self.threads.setValue(settings.get("thumb_threads"))
        self.auto_faces = QCheckBox(tr("Find faces automatically when a folder opens (on this computer, free)"))
        self.auto_faces.setChecked(settings.get("auto_faces"))

        clear = QPushButton(tr("Clear thumbnail cache ({mb} MB)", mb=f"{self._cache_mb():.0f}"))
        clear.clicked.connect(lambda: self._clear_cache(clear))

        form = QFormLayout()
        form.addRow(tr("Language:"), self.lang)
        form.addRow(tr("API key:"), key_row)
        form.addRow("", test)
        form.addRow(tr("Model:"), self.model)
        form.addRow(tr("Parallel AI requests:"), self.conc)
        form.addRow(tr("Image size sent to AI:"), self.ai_side)
        form.addRow(tr("Thumbnail threads:"), self.threads)
        form.addRow(tr("Faces:"), self.auto_faces)
        hint = QLabel(tr("A smaller AI image means fewer tokens and faster uploads; 1024 px is enough for most "
                         "labels. Blur detection and recognising people in group shots are more accurate with "
                         "larger images. Language and thumbnail threads apply after a restart; fewer threads "
                         "use less energy."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:gray")

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(hint)
        lay.addWidget(clear)
        lay.addWidget(bb)

    def _test(self) -> None:
        try:
            model = JevClient(self.key.text().strip(), self.model.text().strip()).test()
            QMessageBox.information(self, tr("Connection"), tr("Connected. Model: {m}", m=model))
        except JevError as e:
            QMessageBox.warning(self, tr("Connection"), tr("Error: {e}", e=e))

    def _cache_mb(self) -> float:
        total = 0
        for root, _d, files in os.walk(self.thumb_cache_dir):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        return total / 1048576

    def _clear_cache(self, btn) -> None:
        shutil.rmtree(self.thumb_cache_dir, ignore_errors=True)
        os.makedirs(self.thumb_cache_dir, exist_ok=True)
        btn.setText(tr("Thumbnail cache cleared"))
        btn.setEnabled(False)

    def _save(self) -> None:
        old_lang = self.settings.get("language") or ""
        self.settings.set_api_key(self.key.text())
        self.settings.set("language", self.lang.currentData())
        self.settings.set("model", self.model.text().strip() or "jev-latest")
        self.settings.set("concurrency", self.conc.value())
        self.settings.set("ai_max_side", self.ai_side.value())
        self.settings.set("thumb_threads", self.threads.value())
        self.settings.set("auto_faces", self.auto_faces.isChecked())
        if self.lang.currentData() != old_lang:
            QMessageBox.information(self, tr("Language"), tr("Restart Facet to switch the language."))
        self.accept()


# --------------------------------------------------------------------------- organize


class OrganizeDialog(QDialog):
    def __init__(self, counts: dict[str, int], folder: str, default_scope: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Sort into folders"))
        self.setMinimumWidth(580)

        self.scope = QComboBox()
        for key, text in [("selected", tr("Selected photos")), ("filtered", tr("All photos in the filtered view")),
                          ("all", tr("All photos"))]:
            self.scope.addItem(f"{text} ({counts.get(key, 0)})", key)
        self.scope.setCurrentIndex(max(0, self.scope.findData(default_scope)))

        self.by_label = QRadioButton(tr("By label – one subfolder per label or person"))
        self.single = QRadioButton(tr("All into one folder"))
        self.by_label.setChecked(True)
        g1 = QButtonGroup(self)
        g1.addButton(self.by_label)
        g1.addButton(self.single)

        self.copy = QRadioButton(tr("Copy (originals stay)"))
        self.move = QRadioButton(tr("Move"))
        self.copy.setChecked(True)
        g2 = QButtonGroup(self)
        g2.addButton(self.copy)
        g2.addButton(self.move)

        self.base = QLineEdit(os.path.join(folder, tr("Sorted")))
        self.target = QLineEdit(os.path.join(folder, tr("Selected")))
        self.unlabeled = QCheckBox(tr("Photos without labels into an “Other” folder"))
        self.sidecars = QCheckBox(tr("Include companion files (.xmp, .aae, RAW+JPEG pairs with the same name)"))
        self.sidecars.setChecked(True)
        note = QLabel(tr("When moving, a photo can only go to one place: the first matching label in label order "
                         "wins. Conflicting file names get a number (“photo (1).jpg”). This can be undone."))
        note.setWordWrap(True)
        note.setStyleSheet("color:gray")

        def row(edit: QLineEdit) -> QWidget:
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            b = QPushButton(tr("Browse…"))
            b.clicked.connect(lambda: self._browse(edit))
            h.addWidget(edit, 1)
            h.addWidget(b)
            return w

        what = QGroupBox(tr("What and how?"))
        f = QFormLayout(what)
        f.addRow(tr("Photos:"), self.scope)
        f.addRow(self.by_label)
        f.addRow(tr("   Target (label folders are created in it):"), row(self.base))
        f.addRow("   ", self.unlabeled)
        f.addRow(self.single)
        f.addRow(tr("   Target folder:"), row(self.target))
        mode = QGroupBox(tr("Operation"))
        m = QVBoxLayout(mode)
        m.addWidget(self.copy)
        m.addWidget(self.move)
        m.addWidget(self.sidecars)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Next…"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(what)
        lay.addWidget(mode)
        lay.addWidget(note)
        lay.addWidget(bb)

        self.by_label.toggled.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        on = self.by_label.isChecked()
        self.base.parentWidget().setEnabled(on)
        self.unlabeled.setEnabled(on)
        self.target.parentWidget().setEnabled(not on)

    def _browse(self, edit: QLineEdit) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Target folder"), edit.text())
        if d:
            edit.setText(d)

    def config(self) -> dict:
        return {
            "scope": self.scope.currentData(),
            "by_label": self.by_label.isChecked(),
            "move": self.move.isChecked(),
            "base": self.base.text().strip(),
            "target": self.target.text().strip(),
            "unlabeled": tr("Other") if self.unlabeled.isChecked() else None,
            "sidecars": self.sidecars.isChecked(),
        }


__all__ = ["LabelsDialog", "LabelEditDialog", "PersonDialog", "SettingsDialog", "OrganizeDialog", "face_icon",
           "language"]
