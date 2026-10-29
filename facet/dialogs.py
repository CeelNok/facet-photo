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
    QFrame, QListWidgetItem, QMessageBox, QPushButton, QRadioButton, QScrollArea, QSlider, QSpinBox, QTableWidget,
    QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from facet.i18n import LANGUAGES, language, tr
from facet.ai import DEFAULT_MODELS, KEY_URLS, PROVIDERS, AIError, make_client
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
            "Every label is a yes/no question for the AI. Refer to the image as "
            "<code>`photo`</code>. The AI returns a 0–100% probability; the label is applied when it "
            "reaches the threshold. Thresholds can be changed later without re-analysing. Labels 1–9 "
            "can also be toggled with the number keys. People (👤) are created by marking a face in "
            "the viewer."
        ))
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.RichText)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr("Name"), tr("Question for the AI (English works "
                                                             "best)"),
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
            form.addRow(tr("Question for the AI:"), self.question)
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
            lay.addWidget(QLabel(tr("<b>Reference faces</b> – the newest {n} are sent to the AI. Add "
                                    "more by marking this person's face on other photos (different "
                                    "angles help).",
                                    n=MAX_REF_FACES)))
            lay.addWidget(self.faces)
            lay.addWidget(rm)
            hint = tr("Changing the reference faces re-checks this person on the next analysis.")
        else:
            hint = tr("The AI answers this yes/no question for every photo. English questions are "
                      "the most accurate; refer to the image as <code>`photo`</code>. For a new "
                      "label only this one question is sent for photos that were already analysed.")
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
            self.search_now = QCheckBox(tr("Find this person in the current view now with AI (uses "
                                           "the API)"))
            self.search_now.setChecked(True)
        else:  # local recognition already finds frontal faces; Jev can add side views
            self.search_now = QCheckBox(tr("Also search with AI for side views and small faces (uses "
                                           "the API)"))
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
        self.setMinimumWidth(620)

        self.lang = QComboBox()
        self.lang.addItem(tr("Automatic (system language)"), "")
        for code, name in LANGUAGES.items():
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(settings.get("language") or "")))

        # ---- AI provider
        self.provider = QComboBox()
        for code, name in PROVIDERS.items():
            self.provider.addItem(name, code)
        self.provider.setCurrentIndex(max(0, self.provider.findData(settings.get("provider") or "jev")))
        self.provider.currentIndexChanged.connect(self._sync_provider)
        provider_hint = QLabel(tr(
            "<b>TypeSafe Jev</b>: calibrated yes/no probabilities; can also look for people by their reference "
            "faces.<br><b>OpenAI (ChatGPT)</b>: GPT vision models; good general image understanding, but it does "
            "not compare faces (people are then found by the local face recognition only)."))
        provider_hint.setWordWrap(True)
        provider_hint.setTextFormat(Qt.TextFormat.RichText)
        provider_hint.setObjectName("muted")

        self.keys: dict[str, QLineEdit] = {}
        self.models: dict[str, QComboBox] = {}
        self.boxes: dict[str, QGroupBox] = {}
        for code, name in PROVIDERS.items():
            box = QGroupBox(name)
            form = QFormLayout(box)
            key = QLineEdit(settings.api_key(code))
            key.setEchoMode(QLineEdit.EchoMode.Password)
            key.setPlaceholderText(tr("API key ({url})", url=KEY_URLS[code].replace("https://", "")))
            key.setToolTip(tr("Stored in a private file in Facet's data folder – no keychain, no password prompts."))
            show = QPushButton(tr("Show"))
            show.setCheckable(True)
            show.toggled.connect(lambda on, k=key: k.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
            row = QHBoxLayout()
            row.addWidget(key, 1)
            row.addWidget(show)
            model = QComboBox()
            model.setEditable(True)
            choices = ["jev-latest"] if code == "jev" else ["gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.4", "gpt-5.5"]
            model.addItems(choices)
            model.setCurrentText(settings.get("model" if code == "jev" else "openai_model") or DEFAULT_MODELS[code])
            if code == "openai":
                model.setToolTip(tr("gpt-5.4-mini: good balance of quality and price · gpt-5.4-nano: cheapest · "
                                    "gpt-5.4 / gpt-5.5: most accurate, more expensive"))
            test = QPushButton(tr("Test connection"))
            test.clicked.connect(lambda _c=False, c=code: self._test(c))
            form.addRow(tr("API key:"), row)
            form.addRow(tr("Model:"), model)
            form.addRow("", test)
            self.keys[code], self.models[code], self.boxes[code] = key, model, box

        # ---- performance
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
        perf = QGroupBox(tr("Performance"))
        pf = QFormLayout(perf)
        pf.addRow(tr("Parallel AI requests:"), self.conc)
        pf.addRow(tr("Image size sent to AI:"), self.ai_side)
        pf.addRow(tr("Thumbnail threads:"), self.threads)
        hint = QLabel(tr("A smaller AI image means fewer tokens and faster uploads; 1024 px is enough for most "
                         "labels. Blur detection and recognising people in group shots are more accurate with "
                         "larger images. Language and thumbnail threads apply after a restart; fewer threads "
                         "use less energy."))
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        pf.addRow(hint)

        # ---- faces
        faces = QGroupBox(tr("Faces"))
        ff = QVBoxLayout(faces)
        self.auto_faces = QCheckBox(tr("Find faces automatically when a folder opens (on this computer, free)"))
        self.auto_faces.setChecked(settings.get("auto_faces"))
        warn = QLabel(tr("⚠ Face recognition is not 100% accurate: people can be missed, two people can be mixed "
                         "up, or one person can be split into several groups. Always check the results."))
        warn.setWordWrap(True)
        warn.setStyleSheet("color:#d97706")
        ff.addWidget(self.auto_faces)
        ff.addWidget(warn)

        clear = QPushButton(tr("Clear thumbnail cache ({mb} MB)", mb=f"{self._cache_mb():.0f}"))
        clear.clicked.connect(lambda: self._clear_cache(clear))

        top = QFormLayout()
        top.addRow(tr("Language:"), self.lang)
        top.addRow(tr("AI for analysis:"), self.provider)
        top.addRow("", provider_hint)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.addLayout(top)
        for code in PROVIDERS:
            lay.addWidget(self.boxes[code])
        lay.addWidget(perf)
        lay.addWidget(faces)
        lay.addWidget(clear)
        scroll = QScrollArea()
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.addWidget(scroll, 1)
        outer.addWidget(bb)
        self.resize(660, 760)
        self._sync_provider()

    def _sync_provider(self) -> None:
        current = self.provider.currentData()
        for code, box in self.boxes.items():
            box.setTitle(PROVIDERS[code] + ("  ✓ " + tr("in use") if code == current else ""))

    def _test(self, code: str) -> None:
        class _Tmp:  # settings view with the values typed in the dialog
            def __init__(s, d):
                s.d = d

            def get(s, k):
                return {"provider": code, "model": self.models["jev"].currentText().strip(),
                        "openai_model": self.models["openai"].currentText().strip()}.get(k)

            def api_key(s, p=None):
                return self.keys[p or code].text().strip()

        try:
            model = make_client(_Tmp(self), code).test()
            QMessageBox.information(self, tr("Connection"), tr("Connected. Model: {m}", m=model))
        except AIError as e:
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
        for code, key in self.keys.items():
            self.settings.set_api_key(key.text(), code)
        self.settings.set("provider", self.provider.currentData())
        self.settings.set("language", self.lang.currentData())
        self.settings.set("model", self.models["jev"].currentText().strip() or DEFAULT_MODELS["jev"])
        self.settings.set("openai_model", self.models["openai"].currentText().strip() or DEFAULT_MODELS["openai"])
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


# --------------------------------------------------------------------------- batch rename


class RenameDialog(QDialog):
    """Rename many photos at once: name pattern or find & replace, with a live old → new preview."""

    TOKEN_TIPS = {
        "{name}": "Original name (without extension)",
        "{n}": "Running number (start and digits below)",
        "{date}": "Capture date from EXIF, e.g. 2025-12-24",
        "{time}": "Capture time from EXIF, e.g. 18-30-05",
        "{folder}": "Name of the photo's folder",
        "{label}": "First label on the photo",
    }

    def __init__(self, photos: list, label_of=None, parent=None) -> None:
        super().__init__(parent)
        from PySide6.QtCore import QTimer

        from facet.renamer import RenameConfig

        self.setWindowTitle(tr("Rename photos"))
        self.resize(820, 680)
        self.photos = photos
        self.label_of = label_of
        self.times: dict = {}
        self.plan = None
        self._cfg_cls = RenameConfig

        self.by_pattern = QRadioButton(tr("Name pattern"))
        self.by_replace = QRadioButton(tr("Find and replace"))
        self.by_pattern.setChecked(True)
        g = QButtonGroup(self)
        g.addButton(self.by_pattern)
        g.addButton(self.by_replace)

        self.pattern = QLineEdit("{name}")
        self.pattern.setPlaceholderText(tr("e.g. Wedding_{date}_{n}"))
        tokens = QHBoxLayout()
        tokens.setSpacing(4)
        for tok, tip in self.TOKEN_TIPS.items():
            b = QPushButton(tok)
            b.setToolTip(tr(tip))
            b.clicked.connect(lambda _c=False, t=tok: (self.pattern.insert(t), self.pattern.setFocus()))
            tokens.addWidget(b)
        tokens.addStretch(1)
        self.start = QSpinBox()
        self.start.setRange(0, 9_999_999)
        self.start.setValue(1)
        self.digits = QSpinBox()
        self.digits.setRange(1, 8)
        self.digits.setValue(3)
        self.order = QComboBox()
        self.order.addItem(tr("Grid order"), "grid")
        self.order.addItem(tr("Capture time"), "time")
        self.order.addItem(tr("File name"), "name")
        num = QHBoxLayout()
        for lbl, w in ((tr("Start at"), self.start), (tr("Digits"), self.digits), (tr("Number in"), self.order)):
            num.addWidget(QLabel(lbl))
            num.addWidget(w)
        num.addStretch(1)
        pat_box = QGroupBox()
        pf = QVBoxLayout(pat_box)
        pf.addWidget(self.pattern)
        pf.addLayout(tokens)
        pf.addLayout(num)

        self.find = QLineEdit()
        self.find.setPlaceholderText(tr("Find"))
        self.replace = QLineEdit()
        self.replace.setPlaceholderText(tr("Replace with"))
        self.regex = QCheckBox(tr("Regular expression"))
        self.case = QCheckBox(tr("Match case"))
        rep_box = QGroupBox()
        rf = QHBoxLayout(rep_box)
        for w in (self.find, self.replace, self.regex, self.case):
            rf.addWidget(w)

        self.lower_ext = QCheckBox(tr("Lowercase extensions (.JPG → .jpg)"))
        self.companions = QCheckBox(tr("Rename companion files too (.xmp, .aae, RAW+JPEG pairs)"))
        self.companions.setChecked(True)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("Current name"), tr("New name"), ""])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.summary = QLabel()
        self.summary.setWordWrap(True)

        self.bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Rename"))
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("{n} photos selected", n=len(photos))))
        lay.addWidget(self.by_pattern)
        lay.addWidget(pat_box)
        lay.addWidget(self.by_replace)
        lay.addWidget(rep_box)
        lay.addWidget(self.lower_ext)
        lay.addWidget(self.companions)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.summary)
        lay.addWidget(self.bb)

        self._timer = QTimer(self, singleShot=True, interval=150, timeout=self.refresh)
        for w in (self.pattern, self.find, self.replace):
            w.textChanged.connect(lambda _t: self._timer.start())
        for w in (self.start, self.digits):
            w.valueChanged.connect(lambda _v: self._timer.start())
        self.order.currentIndexChanged.connect(lambda _i: self._timer.start())
        for w in (self.by_pattern, self.by_replace, self.regex, self.case, self.lower_ext, self.companions):
            w.toggled.connect(lambda _o: self._timer.start())
        self.by_pattern.toggled.connect(lambda on: (pat_box.setEnabled(on), rep_box.setEnabled(not on)))
        rep_box.setEnabled(False)
        self.refresh()

    def config(self):
        return self._cfg_cls(
            mode="pattern" if self.by_pattern.isChecked() else "replace",
            pattern=self.pattern.text(), start=self.start.value(), digits=self.digits.value(),
            order=self.order.currentData(), find=self.find.text(), replace=self.replace.text(),
            regex=self.regex.isChecked(), case_sensitive=self.case.isChecked(),
            lower_ext=self.lower_ext.isChecked(), companions=self.companions.isChecked())

    def _ensure_times(self, cfg) -> None:
        uses_time = cfg.mode == "pattern" and any(t in cfg.pattern for t in
                                                 ("{date}", "{time}", "{year}", "{month}", "{day}"))
        if (uses_time or cfg.order == "time") and not self.times:
            from PySide6.QtWidgets import QApplication

            from facet.renamer import capture_time

            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self.times = {p.key: capture_time(p.path) for p in self.photos}
            finally:
                QApplication.restoreOverrideCursor()

    def refresh(self) -> None:
        from facet.renamer import build_plan

        cfg = self.config()
        self._ensure_times(cfg)
        self.plan = build_plan(self.photos, cfg, self.times, self.label_of)
        rows = self.plan.rows
        shown = rows[:3000]
        self.table.setRowCount(len(shown))
        warn = QColor("#e5484d")
        muted = self.palette().color(self.palette().ColorRole.PlaceholderText)
        for i, r in enumerate(shown):
            old = QTableWidgetItem(os.path.basename(r.src) + ("" if r.primary else "  " + tr("(companion)")))
            new = QTableWidgetItem(os.path.basename(r.dst))
            mark = {"ok": "✓", "same": "–", "conflict": "⚠", "invalid": "⚠"}[r.status]
            st = QTableWidgetItem(mark)
            if r.status in ("conflict", "invalid"):
                for it in (old, new, st):
                    it.setForeground(warn)
                st.setToolTip(tr(r.note) if r.note else "")
            elif r.status == "same" or not r.primary:
                for it in (old, new):
                    it.setForeground(muted)
            self.table.setItem(i, 0, old)
            self.table.setItem(i, 1, new)
            self.table.setItem(i, 2, st)
        ok = self.bb.button(QDialogButtonBox.StandardButton.Ok)
        if self.plan.error:
            self.summary.setText(tr("Invalid regular expression: {e}", e=self.plan.error))
            self.summary.setStyleSheet("color:#e5484d")
            ok.setEnabled(False)
            return
        n_changes, n_problems = len(self.plan.changes), len(self.plan.problems)
        if n_problems:
            self.summary.setText(tr("{n} name conflicts – change the pattern so every file gets its own name.",
                                    n=n_problems))
            self.summary.setStyleSheet("color:#e5484d")
        else:
            self.summary.setText(tr("{n} files will be renamed. You can undo this afterwards.", n=n_changes))
            self.summary.setStyleSheet("")
        ok.setEnabled(n_changes > 0 and not n_problems)
