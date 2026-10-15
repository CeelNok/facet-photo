"""Main window: library, photo grid, filter sidebar (labels and people), AI analysis and folder sorting."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from collections import Counter
from copy import deepcopy

from PySide6.QtCore import QItemSelectionModel, QObject, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDockWidget, QFileDialog, QFrame, QScrollArea, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMenu, QMessageBox, QProgressBar, QPushButton, QSizePolicy, QSlider, QSplitter, QToolButton, QVBoxLayout,
    QWidget,
)

from facet import APP_NAME, __version__, organizer
from facet.analyzer import AnalyzeJob
from facet.dialogs import LabelEditDialog, LabelsDialog, OrganizeDialog, PersonDialog, SettingsDialog, face_icon
from facet.faces import FACES_OK, FaceIndex, FaceScanJob, box_iou
from facet.facespanel import FacesPanel
from facet.grid import PhotoDelegate, PhotoGrid
from facet.i18n import tr
from facet.imaging import HEIF_OK, RAW_OK, crop_face
from facet.jev_client import JevClient, JevError
from facet.library import LibraryPanel
from facet.sidebar import Section, Sidebar
from facet.models import PhotoFilter, PhotoModel, PhotoRole
from facet.scanner import Photo, load_paths, natural_key, scan_folder
from facet.storage import (
    PALETTE, Label, ScoreDB, Settings, cache_dir, faces_dir, load_labels, norm_dir, path_key, save_labels,
)
from facet.thumbs import ThumbLoader
from facet.viewer import ViewerWindow

SPECIAL_ALL, SPECIAL_UNANALYZED, SPECIAL_UNLABELED = "all", "unanalyzed", "unlabeled"


def special_names() -> dict[str, str]:
    return {SPECIAL_ALL: tr("All photos"), SPECIAL_UNANALYZED: tr("Not analysed"),
            SPECIAL_UNLABELED: tr("No labels")}


COUNT_ROLE = Qt.ItemDataRole.UserRole + 5


class _LabelItem(QListWidgetItem):
    """Sidebar entry ordered by number of matches (most first, empty ones last, “add” row at the very end)."""

    def _key(self):
        kind, _ = self.data(Qt.ItemDataRole.UserRole)
        if kind != "label":
            return (2, 0, "")
        n = self.data(COUNT_ROLE) or 0
        return (0 if n else 1, -n, (self.data(Qt.ItemDataRole.UserRole + 6) or "").casefold())

    def __lt__(self, other) -> bool:
        return self._key() < other._key()


class _LoadRelay(QObject):
    done = Signal(int, list, int)  # load token, photos, missing files


def _dot(color: str, size: int = 12) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pm)


def label_icon(l: Label, size: int = 12) -> QIcon:
    if l.is_person and l.faces:
        return face_icon(l.faces[-1], 40)
    return _dot(l.color, size)


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, db: ScoreDB) -> None:
        super().__init__()
        self.settings = settings
        self.db = db
        self.all_labels = load_labels()  # every label; self.labels = the ones that apply to the current view
        self.labels = [l for l in self.all_labels if not l.folder_only]
        self._migrate_label_scopes()
        self.source: tuple[str, object] | None = None  # ("folder", path) | ("collection", id) | ("recent", None)
        self._load_token = 0
        self.analyze_job: AnalyzeJob | None = None
        self.org_job: organizer.OrganizeJob | None = None
        self.last_op = None
        self.viewer: ViewerWindow | None = None
        self.errors: list[str] = []
        self.face_index = FaceIndex(db) if FACES_OK else None
        self.face_job: FaceScanJob | None = None
        self.setWindowTitle(APP_NAME)
        self.resize(1320, 860)
        self.setAcceptDrops(True)

        self.thumbs = ThumbLoader(str(cache_dir() / "thumbs"), settings.get("thumb_threads"))
        self.model = PhotoModel(self.thumbs, lambda: self.labels)
        self.proxy = PhotoFilter(lambda: self.labels)
        self.proxy.setSourceModel(self.model)
        self.grid = PhotoGrid()
        self.delegate = PhotoDelegate(self.grid, self.model, lambda: self.labels)
        self.grid.setItemDelegate(self.delegate)
        self.grid.setModel(self.proxy)
        self.grid.loader = self.thumbs
        self.grid.open_requested.connect(self.open_viewer)
        self.grid.label_key.connect(self._label_key)
        self.grid.clear_key.connect(lambda: self.take_off(self.labels, scope_hint=True))
        self.grid.customContextMenuRequested.connect(self._context_menu)
        self.grid.selectionModel().selectionChanged.connect(lambda *_: self._update_status())
        # grid on top, faces strip below; the gap between them can be dragged
        self.center = QSplitter(Qt.Orientation.Vertical)
        self.center.setObjectName("center")
        self.center.setChildrenCollapsible(False)
        self.center.setHandleWidth(8)
        self.center.addWidget(self.grid)
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 8, 0)
        wl.addWidget(self.center)
        self.setCentralWidget(wrap)

        self._relay = _LoadRelay()
        self._relay.done.connect(self._on_loaded)

        # Debounced work: nothing runs on a timer while the app is idle.
        self._commit_timer = QTimer(self, singleShot=True, interval=1500, timeout=self.db.commit)
        self._refresh_timer = QTimer(self, singleShot=True, interval=400,
                                     timeout=lambda: self._refresh_filters(refilter=self.proxy.uses_labels))
        self._search_timer = QTimer(self, singleShot=True, interval=250, timeout=self._apply_search)
        self._faces_timer = QTimer(self, singleShot=True, interval=500, timeout=self._refresh_faces)

        self._build_actions()
        self._build_toolbar()
        self._build_sidebar()
        self._build_faces()
        self._build_statusbar()
        self._build_menus()
        self._rebuild_filter_list()
        self.delegate.side = settings.get("grid_size")

        geo = settings._q.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self.sidebar.restore()
        sizes = settings._q.value("center/sizes")
        try:
            self.center.setSizes([int(x) for x in sizes] if sizes else [700, 190])
        except (TypeError, ValueError):
            self.center.setSizes([700, 190])
        QTimer.singleShot(0, self._fit_to_screen)
        QTimer.singleShot(0, self._restore_last_source)

    def _fit_to_screen(self) -> None:
        """Keep the whole window (status bar, faces strip) on screen, e.g. after moving to a smaller display."""
        scr = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        frame = self.frameGeometry()
        extra_w, extra_h = frame.width() - self.width(), frame.height() - self.height()
        w = min(self.width(), scr.width() - extra_w)
        h = min(self.height(), scr.height() - extra_h)
        if (w, h) != (self.width(), self.height()):
            self.resize(w, h)
        frame = self.frameGeometry()
        x = min(max(frame.x(), scr.x()), scr.right() - frame.width() + 1)
        y = min(max(frame.y(), scr.y()), scr.bottom() - frame.height() + 1)
        if (x, y) != (frame.x(), frame.y()):
            self.move(x, y)

    # ================================================================== UI construction

    def _act(self, text: str, slot, shortcut=None, tip: str | None = None) -> QAction:
        a = QAction(text, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setToolTip(tip)
        return a

    def _build_actions(self) -> None:
        self.a_open = self._act(tr("Add folder…"), self.choose_folder, QKeySequence.StandardKey.Open)
        self.a_rescan = self._act(tr("Refresh"), self.reload, "F5")
        self.a_recursive = self._act(tr("Subfolders"), self._recursive_toggled,
                                     tip=tr("Also load photos from the open folder's subfolders"))
        self.a_recursive.setCheckable(True)
        self.a_an_sel = self._act(tr("Analyse selected photos"),
                                  lambda: self.analyze_photos(self.selected_photos()), "Ctrl+E")
        self.a_an_view = self._act(tr("Analyse filtered view"), lambda: self.analyze_photos(self.visible_photos()))
        self.a_an_all = self._act(tr("All unanalysed photos"), lambda: self.analyze_photos(self.model.photos))
        self.a_an_force = self._act(tr("Re-analyse selected (all labels)"),
                                    lambda: self.analyze_photos(self.selected_photos(), force=True))
        self.a_stop = self._act(tr("Stop"), self.stop_jobs)
        self.a_stop.setEnabled(False)
        self.a_labels = self._act(tr("Labels…"), self.edit_labels, "Ctrl+L")
        self.a_new_label = self._act(tr("New filter / label…"), self.add_label, "Ctrl+Shift+L")
        self.a_mark_face = self._act(tr("Mark a face…"), self.mark_face, "Ctrl+Shift+F")
        self.a_organize = self._act(tr("Sort into folders…"), self.organize, "Ctrl+M")
        self.a_undo = self._act(tr("Undo sorting"), self.undo_organize, QKeySequence.StandardKey.Undo)
        self.a_undo.setEnabled(False)
        self.a_settings = self._act(tr("Settings…"), self.open_settings, QKeySequence.StandardKey.Preferences)
        self.a_select_all = self._act(tr("Select all"), self.grid.selectAll, QKeySequence.StandardKey.SelectAll)
        self.a_select_none = self._act(tr("Select none"), self.grid.clearSelection, "Ctrl+Shift+A")
        self.a_view = self._act(tr("Open in viewer"), self.open_viewer)
        self.a_new_coll = self._act(tr("New collection…"), lambda: self.library.new_collection())
        self.a_sel_to_coll = self._act(tr("Selected photos to a new collection…"),
                                       self.selection_to_new_collection, "Ctrl+N")

    def _build_toolbar(self) -> None:
        tb = self.addToolBar(tr("Toolbar"))
        tb.setObjectName("toolbar")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        tb.addAction(self.a_open)
        tb.addSeparator()
        an = QToolButton()
        an.setText("✦  " + tr("Analyse with Jev"))
        an.setObjectName("primary")
        an.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        m = QMenu(an)
        for a in (self.a_an_sel, self.a_an_view, self.a_an_all, self.a_an_force):
            m.addAction(a)
        an.setMenu(m)
        an.clicked.connect(self._analyze_default)
        an.setToolTip(tr("Analyses the selected photos, or the unanalysed photos of the filtered view"))
        tb.addWidget(an)
        tb.addAction(self._toolbar_mirror(self.a_stop))  # shown only while something runs
        tb.addSeparator()
        off = QToolButton()
        off.setText(tr("Remove labels"))
        off.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        off.setToolTip(tr("Remove labels from the selected photos (no selection: from the whole view)"))
        self.off_menu = QMenu(off)
        self.off_menu.aboutToShow.connect(lambda: self._fill_takeoff_menu(self.off_menu))
        off.setMenu(self.off_menu)
        tb.addWidget(off)
        tb.addAction(self.a_mark_face)
        tb.addAction(self.a_organize)
        tb.addAction(self._toolbar_mirror(self.a_undo))  # shown only when there is something to undo
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search file names…"))
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(180)
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        tb.addWidget(self.search)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(90, 360)
        self.size_slider.setFixedWidth(100)
        self.size_slider.setValue(self.settings.get("grid_size"))
        self.size_slider.setToolTip(tr("Thumbnail size"))
        self.size_slider.valueChanged.connect(self._grid_size)
        tb.addWidget(self.size_slider)
        gear = QToolButton()
        gear.setObjectName("gear")
        gear.setText("⚙  " + tr("Settings"))
        gear.setToolTip(tr("API key, language, faces, performance"))
        gear.clicked.connect(self.open_settings)
        tb.addWidget(gear)

    def _toolbar_mirror(self, action: QAction) -> QAction:
        """Toolbar copy of an action that is only visible while the original is enabled (menus keep theirs)."""
        mirror = QAction(action.text(), self)
        mirror.triggered.connect(action.trigger)
        mirror.setVisible(action.isEnabled())
        action.enabledChanged.connect(mirror.setVisible)
        return mirror

    def _make_label_list(self) -> QListWidget:
        lst = QListWidget()
        lst.setIconSize(QSize(20, 20))
        lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lst.itemClicked.connect(self._filter_clicked)
        lst.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        lst.customContextMenuRequested.connect(lambda pos, lst=lst: self._filter_menu(lst, pos))
        lst.setToolTip(tr("Click: only these (✓) · Alt/Option-click: exclude (✕)\n"
                          "Right-click: edit, remove from photos, delete"))
        return lst

    def _build_sidebar(self) -> None:
        """Left side: Folders, Collections, Filters, Labels, People and View – each folds and resizes."""
        self.library = LibraryPanel(self.db, self)
        self.library.open_folder.connect(self.open_folder)
        self.library.open_collection.connect(self.open_collection)
        self.library.open_recent.connect(self.open_recent)
        self.library.add_folder_requested.connect(self.choose_folder)
        self.library.add_selected_to.connect(self.add_selection_to_collection)
        self.library.collections_changed.connect(self._collections_changed)
        self.library.reveal.connect(self.reveal)

        self.special_list = QListWidget()
        for key, name in special_names().items():
            it = QListWidgetItem(name)
            it.setData(Qt.ItemDataRole.UserRole, ("special", key))
            self.special_list.addItem(it)
        self.special_list.itemClicked.connect(self._filter_clicked)
        self.special_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.filter_list = self._make_label_list()
        self.people_list = self._make_label_list()

        self.match = QComboBox()
        self.match.addItems([tr("Any checked label"), tr("All checked labels")])
        self.match.currentIndexChanged.connect(self._match_changed)
        self.type_box = QComboBox()
        self.type_box.addItem(tr("All file types"), "all")
        self.type_box.addItem(tr("RAW only"), "raw")
        self.type_box.addItem(tr("No RAW (JPEG, HEIC…)"), "nonraw")
        self.type_box.currentIndexChanged.connect(self._type_changed)
        self.sort_box = QComboBox()
        self.sort_box.currentIndexChanged.connect(lambda _i: self._apply_sort())
        clear = QPushButton(tr("Clear filters"))
        clear.clicked.connect(self.clear_filters)
        sel = QPushButton(tr("Select visible photos"))
        sel.clicked.connect(self.grid.selectAll)
        view = QWidget()
        vl = QVBoxLayout(view)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(6)
        self.subfolders_box = QCheckBox(tr("Include subfolders"))
        self.subfolders_box.setToolTip(tr("Also load photos from the open folder's subfolders"))
        self.subfolders_box.clicked.connect(lambda on: (self.a_recursive.setChecked(on), self._recursive_toggled()))
        self.a_recursive.toggled.connect(self.subfolders_box.setChecked)
        self.a_recursive.changed.connect(lambda: self.subfolders_box.setEnabled(self.a_recursive.isEnabled()))
        for wdg in (self.subfolders_box, self.match, self.type_box, QLabel(tr("Sort by:")), self.sort_box, clear, sel):
            vl.addWidget(wdg)
        vl.addStretch(1)
        view_scroll = QScrollArea()
        view_scroll.setWidget(view)
        view_scroll.setWidgetResizable(True)
        view_scroll.setFrameShape(QFrame.Shape.NoFrame)
        view_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        sb = Sidebar(self.settings)
        sb.add(Section("folders", tr("Folders"), self.library.folders, "+", tr("Add a folder to the library"),
                       self.choose_folder), 110)
        sb.add(Section("collections", tr("Collections"), self.library.colls, "+", tr("New collection"),
                       lambda: self.library.new_collection()), 110)
        sb.add(Section("filters", tr("Filters"), self.special_list, min_open=130), 150)
        sb.add(Section("labels", tr("Labels"), self.filter_list, tr("+ New filter"), tr("Add a new filter"),
                       self.add_label, min_open=160), 300)
        sb.add(Section("people", tr("People"), self.people_list, tr("+ Mark a face"),
                       tr("Mark a face on the current photo"), self.mark_face, min_open=120), 180)
        sb.add(Section("view", tr("View"), view_scroll, min_open=150), 260)
        self.sidebar = sb

        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(8, 4, 4, 8)
        hl.addWidget(sb, 1)
        settings_btn = QPushButton("⚙  " + tr("Settings"))
        settings_btn.setObjectName("settingsBtn")
        settings_btn.setToolTip(tr("API key, language, faces, performance"))
        settings_btn.clicked.connect(self.open_settings)
        hl.addWidget(settings_btn)
        dock = QDockWidget(tr("Library"), self)
        dock.setObjectName("sidebarDock")
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setTitleBarWidget(QWidget())
        dock.setWidget(holder)
        dock.setMinimumWidth(270)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.sidebar_dock = dock

    def _build_faces(self) -> None:
        self.faces_panel = FacesPanel(collapsed=self.settings._q.value("faces_collapsed", "false") in ("true", True))
        self.faces_panel.collapsed_changed.connect(lambda c: self.settings._q.setValue("faces_collapsed", c))
        self.faces_panel.activated.connect(self._face_group_clicked)
        self.faces_panel.name_requested.connect(self._name_face_group)
        self.faces_panel.name_jev_requested.connect(lambda k, i: self._name_face_group(k, i, jev=True))
        self.faces_panel.ignore_requested.connect(self._ignore_face_group)
        self.faces_panel.jev_requested.connect(
            lambda pid: self.find_person_with_jev(next(l for l in self.labels if l.id == pid)))
        self.faces_panel.collapsed_changed.connect(self._faces_collapsed)
        self.faces_panel.scan_requested.connect(lambda: self.start_face_scan(self.visible_photos(), manual=True))
        if not FACES_OK:
            self.faces_panel.scan_btn.setEnabled(False)
            self.faces_panel.set_status(tr("Face recognition is not available (OpenCV missing)."))
        self.center.addWidget(self.faces_panel)

    def _faces_collapsed(self, collapsed: bool) -> None:
        if not collapsed and self.center.count() > 1:
            sizes = self.center.sizes()
            if sizes[1] < 170:
                total = sum(sizes)
                self.center.setSizes([total - 190, 190])

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        self.count_label = QLabel()
        sb.addPermanentWidget(self.progress)
        sb.addPermanentWidget(self.count_label)
        if not RAW_OK:
            sb.showMessage(tr("Warning: rawpy is not installed, RAW files cannot be loaded."))

    def _build_menus(self) -> None:
        mb = self.menuBar()
        f = mb.addMenu(tr("File"))
        for a in (self.a_open, self.a_new_coll, self.a_sel_to_coll, self.a_rescan, self.a_recursive):
            f.addAction(a)
        f.addSeparator()
        f.addAction(self.a_settings)
        f.addAction(self._act(tr("Quit"), self.close, QKeySequence.StandardKey.Quit))
        e = mb.addMenu(tr("Edit"))
        for a in (self.a_undo, self.a_select_all, self.a_select_none):
            e.addAction(a)
        k = mb.addMenu(tr("Photos"))
        for a in (self.a_view, self.a_an_sel, self.a_an_view, self.a_an_all, self.a_an_force, self.a_stop):
            k.addAction(a)
        k.addSeparator()
        tm = k.addMenu(tr("Remove labels"))
        tm.aboutToShow.connect(lambda: self._fill_takeoff_menu(tm))
        k.addAction(self.a_new_label)
        k.addAction(self.a_mark_face)
        k.addAction(self.a_labels)
        k.addAction(self.a_organize)
        h = mb.addMenu(tr("Help"))
        h.addAction(self._act(tr("TypeSafe documentation"), lambda: QDesktopServices.openUrl(
            QUrl("https://docs.typesafe.ai/introduction"))))
        h.addAction(self._act(tr("About {app}", app=APP_NAME), self._about))

    # ================================================================== sources: folders, collections, recent

    def _restore_last_source(self) -> None:
        last = str(self.settings._q.value("last_source", "") or "")
        kind, _, ident = last.partition(":")
        if kind == "folder" and os.path.isdir(ident):
            self.open_folder(ident)
        elif kind == "collection" and ident.isdigit() and self.db.collection_name(int(ident)):
            self.open_collection(int(ident))
        elif kind == "recent":
            self.open_recent()

    def choose_folder(self) -> None:
        start = self._base_dir() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, tr("Add a folder to the library"), start)
        if d:
            self.open_folder(d)

    def open_folder(self, folder: str) -> None:
        if not folder or not os.path.isdir(folder):
            return
        folder = os.path.abspath(folder)
        self.db.add_folder(folder)
        recursive = self.db.folder_recursive(folder)
        self.a_recursive.setEnabled(True)
        self.a_recursive.setChecked(recursive)
        self.library.refresh()
        self._load(("folder", folder), os.path.basename(folder.rstrip("/\\")) or folder,
                   lambda: (scan_folder(folder, recursive), 0))

    def open_collection(self, cid: int) -> None:
        paths = self.db.collection_paths(cid)
        self.a_recursive.setEnabled(False)
        self._load(("collection", cid), self.db.collection_name(cid), lambda: load_paths(paths))

    def open_recent(self) -> None:
        paths = self.db.recent_paths()
        self.a_recursive.setEnabled(False)
        i = self.sort_box.findData("order")  # newest first, like a history list
        if i >= 0:
            self.sort_box.blockSignals(True)
            self.sort_box.setCurrentIndex(i)
            self.sort_box.blockSignals(False)
        self._load(("recent", None), tr("Recently opened photos"), lambda: load_paths(paths))

    def reload(self) -> None:
        if not self.source:
            return
        kind, ident = self.source
        if kind == "folder":
            self.open_folder(ident)
        elif kind == "collection":
            self.open_collection(ident)
        else:
            self.open_recent()

    def _recursive_toggled(self) -> None:
        if self.source and self.source[0] == "folder":
            self.db.update_folder(self.source[1], recursive=self.a_recursive.isChecked())
            self.db.commit()
            self.reload()

    def _load(self, source: tuple[str, object], title: str, fn) -> None:
        self._load_token += 1
        token = self._load_token
        if source != self.source:
            self.grid.clearSelection()
        self.source = source
        kind, ident = source
        self.settings._q.setValue("last_source", f"{kind}:{ident}" if ident is not None else kind)
        self.library.set_active(kind, ident)
        self.setWindowTitle(f"{title} – {APP_NAME}")
        self.statusBar().showMessage(tr("Loading…"))
        relay = self._relay

        def work():
            photos, missing = fn()
            relay.done.emit(token, photos, missing)

        threading.Thread(target=work, name="load", daemon=True).start()

    def _on_loaded(self, token: int, photos: list[Photo], missing: int) -> None:
        if token != self._load_token:
            return
        keep = {p.key for p in self.selected_photos()}
        active = self._active_labels(photos)
        if [l.id for l in active] != [l.id for l in self.labels]:
            self.labels = active
            self.proxy.include &= {l.id for l in active}
            self.proxy.exclude &= {l.id for l in active}
            self._rebuild_filter_list()
        self._load_scores(photos)
        self.thumbs.clear_memory()
        self.model.set_photos(self._sorted(photos))
        self._refresh_filters()
        self._select_keys(keep)
        kind, ident = self.source
        if kind == "folder":
            self.db.update_folder(ident, count=len(photos))
            self.library.refresh()
        self._refresh_faces()
        if FACES_OK and self.settings.get("auto_faces"):
            self.start_face_scan(photos)
        msg = tr("Photos loaded: {n}", n=len(photos))
        if missing:
            msg += tr(" · {n} files not found (moved or deleted)", n=missing)
        self.statusBar().showMessage(msg, 6000)

    def _base_dir(self) -> str:
        if self.source and self.source[0] == "folder":
            return self.source[1]
        dirs = {os.path.dirname(p.path) for p in self.model.photos}
        try:
            return os.path.commonpath(list(dirs)) if dirs else ""
        except ValueError:
            return next(iter(dirs))

    def _load_scores(self, photos: list[Photo]) -> None:
        by_id = {l.id: l for l in self.labels}
        scores, manual = self.db.load_for({p.key for p in photos})
        for p in photos:
            p.scores = {
                lid: v for lid, v, qh, fs in scores.get(p.key, ())
                if lid in by_id and fs == p.fsig
                and (qh == by_id[lid].qhash or (qh == "local" and by_id[lid].is_person))
            }
            p.manual = {lid: v for lid, v in manual.get(p.key, {}).items() if lid in by_id}

    # ================================================================== collections

    def _collections_changed(self) -> None:
        if self.source and self.source[0] in ("collection", "recent"):
            if self.source[0] == "collection" and not self.db.collection_name(self.source[1]):
                self.model.set_photos([])
                self.source = None
                self.setWindowTitle(APP_NAME)
                self._refresh_filters()
            else:
                self.reload()

    def add_selection_to_collection(self, cid: int) -> None:
        photos = self.selected_photos()
        if not photos:
            QMessageBox.information(self, tr("Collection"), tr("Select some photos in the grid first."))
            return
        n = self.db.add_to_collection(cid, [p.path for p in photos])
        self.library.refresh()
        self.statusBar().showMessage(tr("Added {n} photos to {name}", n=n, name=self.db.collection_name(cid)), 4000)
        if self.source == ("collection", cid):
            self.reload()

    def selection_to_new_collection(self) -> None:
        photos = self.selected_photos()
        if not photos:
            QMessageBox.information(self, tr("Collection"), tr("Select some photos in the grid first."))
            return
        cid = self.library.new_collection([p.path for p in photos])
        if cid is not None:
            self.statusBar().showMessage(tr("New collection with {n} photos", n=len(photos)), 4000)

    def remove_from_collection(self, photos: list[Photo]) -> None:
        if not self.source or self.source[0] != "collection":
            return
        self.db.remove_from_collection(self.source[1], [p.key for p in photos])
        self.model.remove_keys({p.key for p in photos})
        self.library.refresh()
        self._refresh_filters()

    def note_viewed(self, photo: Photo) -> None:
        """Called by the viewer: remembers the photo in “Recently opened photos”."""
        self.db.add_recent(photo.path)
        self._commit_timer.start()

    # ================================================================== sorting & filtering

    def _rebuild_sort_box(self) -> None:
        cur = self.sort_box.currentData()
        self.sort_box.blockSignals(True)
        self.sort_box.clear()
        self.sort_box.addItem(tr("Name"), "name")
        self.sort_box.addItem(tr("Date (newest first)"), "date_desc")
        self.sort_box.addItem(tr("Date (oldest first)"), "date_asc")
        self.sort_box.addItem(tr("File size (largest first)"), "size")
        self.sort_box.addItem(tr("Added / opened order"), "order")
        for l in self.labels:
            self.sort_box.addItem(tr("{name} – probability", name=l.name), "score:" + l.id)
        i = self.sort_box.findData(cur)
        self.sort_box.setCurrentIndex(i if i >= 0 else 0)
        self.sort_box.blockSignals(False)

    def _sorted(self, photos: list[Photo]) -> list[Photo]:
        mode = self.sort_box.currentData() or "name"
        if mode == "order":
            return list(photos)
        if mode == "date_desc":
            return sorted(photos, key=lambda p: p.mtime_ns, reverse=True)
        if mode == "date_asc":
            return sorted(photos, key=lambda p: p.mtime_ns)
        if mode == "size":
            return sorted(photos, key=lambda p: p.size, reverse=True)
        if mode.startswith("score:"):
            lid = mode[6:]
            return sorted(photos, key=lambda p: -(p.manual.get(lid, p.scores.get(lid, -1.0))))
        return sorted(photos, key=lambda p: natural_key(p.name))

    def _apply_sort(self) -> None:
        if (self.sort_box.currentData() == "order") and self.source:
            self.reload()  # source order lives in the folder/collection, not in the current list
            return
        keep = {p.key for p in self.selected_photos()}
        self.model.set_photos(self._sorted(self.model.photos))
        self.proxy.refilter()
        self._select_keys(keep)
        self._update_status()

    def _rebuild_filter_list(self) -> None:
        self._rebuild_sort_box()
        self.filter_list.clear()
        self.people_list.clear()
        for i, l in enumerate(self.labels):
            it = _LabelItem(label_icon(l), l.name)
            it.setData(Qt.ItemDataRole.UserRole, ("label", l.id))
            it.setData(Qt.ItemDataRole.UserRole + 6, l.name)
            if l.is_person:
                tip = tr("Person · {n} reference faces", n=len(l.faces))
            else:
                tip = l.instructions()
                if l.builtin:
                    tip += "\n" + tr("Built-in label – used in every folder")
                elif l.folder_only:
                    tip += "\n" + tr("Only in: {folders}", folders=", ".join(
                        os.path.basename(f.rstrip("/\\")) or f for f in l.folders))
            tip += tr("\nThreshold: {t}%", t=f"{l.threshold * 100:.0f}")
            if i < 9:
                tip += tr("\nShortcut for selected photos: {k}", k=i + 1)
            it.setToolTip(tip)
            (self.people_list if l.is_person else self.filter_list).addItem(it)
        add = _LabelItem("＋  " + tr("Add new filter…"))
        add.setData(Qt.ItemDataRole.UserRole, ("add", "label"))
        add.setForeground(QColor(self.palette().color(self.palette().ColorRole.Link)))
        self.filter_list.addItem(add)
        addp = _LabelItem("＋  " + tr("Mark a face to add a person…"))
        addp.setData(Qt.ItemDataRole.UserRole, ("add", "person"))
        addp.setForeground(QColor(self.palette().color(self.palette().ColorRole.Link)))
        self.people_list.addItem(addp)
        self._refresh_filters()

    def _filter_clicked(self, it: QListWidgetItem) -> None:
        kind, key = it.data(Qt.ItemDataRole.UserRole) or (None, None)
        alt = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier)
        if kind == "add":
            it.listWidget().clearSelection()
            self.add_label() if key == "label" else self.mark_face()
            return
        if kind == "special":
            self.proxy.include.clear()
            self.proxy.exclude.clear()
            self.proxy.special = None if key == SPECIAL_ALL else key
        elif kind == "label":
            self.proxy.special = None
            if alt:
                self._toggle_exclude(key)
            elif key in self.proxy.include:
                self.proxy.include.discard(key)
            else:
                self.proxy.exclude.discard(key)
                self.proxy.include.add(key)
        self._refresh_filters()

    def _toggle_exclude(self, key: str) -> None:
        if key in self.proxy.exclude:
            self.proxy.exclude.discard(key)
        else:
            self.proxy.include.discard(key)
            self.proxy.exclude.add(key)

    def _filter_menu(self, lst: QListWidget, pos) -> None:
        it = lst.itemAt(pos)
        m = QMenu(self)
        if not it or (it.data(Qt.ItemDataRole.UserRole) or ("",))[0] != "label":
            m.addAction(self.a_mark_face if lst is self.people_list else self.a_new_label)
            m.exec(lst.mapToGlobal(pos))
            return
        key = it.data(Qt.ItemDataRole.UserRole)[1]
        label = next((l for l in self.labels if l.id == key), None)
        if label is None:
            return
        m.addAction(tr("Only these (✓)"), lambda: (self.proxy.exclude.discard(key), self.proxy.include.add(key),
                                                   self._refresh_filters()))
        m.addAction(tr("Exclude (✕)"), lambda: (self.proxy.include.discard(key), self.proxy.exclude.add(key),
                                                self._refresh_filters()))
        m.addAction(tr("Clear condition"), lambda: (self.proxy.include.discard(key), self.proxy.exclude.discard(key),
                                                    self._refresh_filters()))
        m.addSeparator()
        n_sel = len(self.selected_photos())
        a = m.addAction(tr("Remove “{name}” from selected photos ({n})", name=label.name, n=n_sel),
                        lambda: self.take_off([label], photos=self.selected_photos()))
        a.setEnabled(n_sel > 0)
        m.addAction(tr("Remove “{name}” from all photos in view ({n})", name=label.name, n=self.proxy.rowCount()),
                    lambda: self.take_off([label], photos=self.visible_photos(), confirm=True))
        if label.is_person:
            m.addAction(tr("Also search for {name} with Jev AI (side views, small faces)…", name=label.name),
                        lambda: self.find_person_with_jev(label))
        m.addSeparator()
        m.addAction(tr("Edit…"), lambda: self.edit_label(label))
        here = self._folder_of_view_in(label)
        if here and len(label.folders) > 1:
            m.addAction(tr("Remove from this folder ({folder})", folder=os.path.basename(here.rstrip("/\\")) or here),
                        lambda: self.remove_label_from_folder(label, here))
        if not label.builtin:
            m.addAction(tr("Delete person…") if label.is_person else tr("Delete label (filter)…"),
                        lambda: self.delete_label(label))
        m.exec(lst.mapToGlobal(pos))

    def _match_changed(self, i: int) -> None:
        self.proxy.match_all = i == 1
        self._refresh_filters()

    def _type_changed(self, _i: int) -> None:
        self.proxy.type_filter = self.type_box.currentData()
        self._refresh_filters()

    def _apply_search(self) -> None:
        self.proxy.text = self.search.text().strip().lower()
        self._refresh_filters()

    def clear_filters(self) -> None:
        self.proxy.key_filter = None
        self.faces_panel.active = None
        self.faces_panel.list.clearSelection()
        self.proxy.include.clear()
        self.proxy.exclude.clear()
        self.proxy.special = None
        self.type_box.setCurrentIndex(0)
        self.search.clear()
        self.proxy.text = ""
        self._refresh_filters()

    def _refresh_filters(self, refilter: bool = True) -> None:
        """Recount labels, update the sidebar and re-apply the filter (debounced by callers)."""
        photos = self.model.photos
        counts = Counter()
        unanalyzed = unlabeled = 0
        for p in photos:
            any_label = False
            for l in self.labels:
                if p.has(l):
                    counts[l.id] += 1
                    any_label = True
            if not any_label:
                unlabeled += 1
            if p.missing(self.labels):
                unanalyzed += 1
        special_counts = {SPECIAL_ALL: len(photos), SPECIAL_UNANALYZED: unanalyzed, SPECIAL_UNLABELED: unlabeled}
        names = special_names()
        for i in range(self.special_list.count()):
            it = self.special_list.item(i)
            key = it.data(Qt.ItemDataRole.UserRole)[1]
            active = (self.proxy.special == key) or (key == SPECIAL_ALL and not self.proxy.uses_labels)
            it.setText(f"{'● ' if active else ''}{names[key]}  ({special_counts[key]})")
        label_names = {l.id: l.name for l in self.labels}
        for lst in (self.filter_list, self.people_list):
            for i in range(lst.count()):
                it = lst.item(i)
                kind, key = it.data(Qt.ItemDataRole.UserRole)
                if kind != "label":
                    continue
                mark = "✓ " if key in self.proxy.include else "✕ " if key in self.proxy.exclude else ""
                it.setText(f"{mark}{label_names.get(key, '?')}  ({counts[key]})")
                it.setData(COUNT_ROLE, counts[key])
                it.setForeground(self.palette().color(
                    self.palette().ColorRole.Text if counts[key] else self.palette().ColorRole.PlaceholderText))
                f = it.font()
                f.setBold(bool(mark))
                it.setFont(f)
            lst.sortItems()
        if refilter:
            self.proxy.refilter()  # persistent indexes keep the selection of rows that stay visible
        self._update_status()

    def _select_keys(self, keys: set[str]) -> None:
        if not keys:
            return
        sm = self.grid.selectionModel()
        sm.clearSelection()
        for row in range(self.proxy.rowCount()):
            idx = self.proxy.index(row, 0)
            if idx.data(PhotoRole).key in keys:
                sm.select(idx, QItemSelectionModel.SelectionFlag.Select)

    def _update_status(self) -> None:
        n_sel = len(self.grid.selectionModel().selectedIndexes())
        self.count_label.setText(tr("{total} photos · {visible} visible · {sel} selected",
                                    total=len(self.model.photos), visible=self.proxy.rowCount(), sel=n_sel))

    def _grid_size(self, v: int) -> None:
        self.settings.set("grid_size", v)
        self.grid.set_cell_side(v)

    # ================================================================== selection helpers

    def selected_photos(self) -> list[Photo]:
        rows = sorted(i.row() for i in self.grid.selectionModel().selectedIndexes())
        return [self.proxy.index(r, 0).data(PhotoRole) for r in rows]

    def visible_photos(self) -> list[Photo]:
        return [self.proxy.index(r, 0).data(PhotoRole) for r in range(self.proxy.rowCount())]

    # ================================================================== viewer, faces & manual labels

    def open_viewer(self, face_mode: bool = False) -> None:
        photos = self.visible_photos()
        if not photos:
            return
        cur = self.grid.currentIndex()
        sel = self.grid.selectionModel().selectedIndexes()
        start = cur.row() if cur.isValid() and cur in sel else (sel[0].row() if sel else max(0, cur.row()))
        if self.viewer is not None:
            self.viewer.close()
        self.viewer = ViewerWindow(self, photos, start)
        self.viewer.closed.connect(self._viewer_closed)
        self.viewer.showMaximized()
        if face_mode:
            self.viewer.face_btn.setChecked(True)

    def mark_face(self) -> None:
        if self.viewer is not None:
            self.viewer.face_btn.setChecked(True)
            self.viewer.activateWindow()
            return
        if not self.visible_photos():
            QMessageBox.information(self, tr("Mark a face"), tr("Open a folder first."))
            return
        if not self.selected_photos():
            QMessageBox.information(self, tr("Mark a face"),
                                    tr("Select a photo of the person first, then drag a box around their face."))
            return
        self.open_viewer(face_mode=True)

    def add_face(self, photo: Photo, rect: tuple, parent=None) -> None:
        """A face was marked in the viewer: name it and use it to find this person everywhere."""
        try:
            jpeg = crop_face(photo.path, rect)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(parent or self, tr("Mark a face"), tr("Could not cut out the face: {e}", e=e))
            return
        match_id = self._detected_face_at(photo, rect)
        people = [l for l in self.labels if l.is_person]
        dlg = PersonDialog(jpeg, people, parent or self, show_search=match_id is None)
        if not dlg.exec():
            return
        person = self._assign_faces_to(dlg.person_name(), [match_id] if match_id is not None else [], [jpeg])
        self.set_manual([photo], person, 1)  # it is certainly on the photo it was marked on
        if dlg.search_now.isChecked():
            self.find_person_with_jev(person)

    def _detected_face_at(self, photo: Photo, rect: tuple) -> int | None:
        """Id of the locally detected face that best overlaps the marked box (scans the photo if needed)."""
        if not FACES_OK:
            return None
        if self.db.scanned({photo.key}).get(photo.key) != photo.fsig:
            from facet.faces import FaceEngine

            try:
                faces = FaceEngine().scan(photo.path)
            except Exception:  # noqa: BLE001
                faces = []
            self._on_face_result(photo.key, photo.path, photo.fsig, faces)
        best, best_iou = None, 0.15
        for fid, x0, y0, x1, y1, _person, _cluster in self.db.faces_on(photo.key):
            rx0, rx1 = sorted((rect[0], rect[2]))
            ry0, ry1 = sorted((rect[1], rect[3]))
            iou = box_iou((x0, y0, x1, y1), (rx0, ry0, rx1, ry1))
            if iou > best_iou:
                best, best_iou = fid, iou
        return best

    def _viewer_closed(self, key: str) -> None:
        self.viewer = None
        self.db.commit()
        for row in range(self.proxy.rowCount()):
            idx = self.proxy.index(row, 0)
            if idx.data(PhotoRole).key == key:
                self.grid.setCurrentIndex(idx)
                self.grid.scrollTo(idx)
                break
        if self.source and self.source[0] == "recent":
            self.reload()
        self.activateWindow()

    def set_manual(self, photos: list[Photo], label, value: int | None) -> None:
        """value: 1 = put the label on, 0 = take it off, None = back to the AI's decision."""
        self.db.set_manual_many([p.key for p in photos], label.id, value)
        for p in photos:
            if value is None:
                p.manual.pop(label.id, None)
            else:
                p.manual[label.id] = value
            self.model.touch(p.key)
        if self.viewer is not None:
            self.viewer.refresh_panel()
        self._commit_timer.start()
        self._refresh_timer.start()

    def _scope(self, scope_hint: bool) -> list[Photo]:
        """Selected photos; without a selection, offer the whole current view."""
        sel = self.selected_photos()
        if sel or not scope_hint:
            return sel
        vis = self.visible_photos()
        if not vis:
            return []
        ok = QMessageBox.question(self, tr("Remove labels"),
                                  tr("No photos are selected. Apply to all {n} photos in the view?", n=len(vis)))
        return vis if ok == QMessageBox.StandardButton.Yes else []

    def take_off(self, labels, photos: list[Photo] | None = None, scope_hint: bool = False,
                 confirm: bool = False) -> None:
        """Take labels off photos (a manual “no” that the AI will not override)."""
        photos = self._scope(scope_hint) if photos is None else photos
        if not photos or not labels:
            return
        if len(photos) > 1:  # never take labels off many photos without asking
            names = ", ".join(l.name for l in labels) if len(labels) <= 3 else tr("all {n} labels", n=len(labels))
            if QMessageBox.question(
                    self, tr("Remove labels"),
                    tr("Remove {names} from {n} photos?\nThe AI will not add them back. You can undo this with "
                       "Remove labels → Clear manual changes.", names=names, n=len(photos))) \
                    != QMessageBox.StandardButton.Yes:
                return
        for l in labels:
            self.set_manual(photos, l, 0)
        what = labels[0].name if len(labels) == 1 else tr("All labels")
        self.statusBar().showMessage(tr("{what} removed from {n} photos", what=what, n=len(photos)), 4000)

    def back_to_ai(self, photos: list[Photo]) -> None:
        for l in self.labels:
            self.set_manual(photos, l, None)
        self.statusBar().showMessage(tr("Manual changes cleared on {n} photos (the AI decides again)",
                                        n=len(photos)), 4000)

    def clear_ai_results(self, photos: list[Photo]) -> None:
        if not photos:
            return
        if QMessageBox.question(
                self, tr("Clear AI results"),
                tr("AI results and manual labels of {n} photos will be cleared and they become “not analysed” "
                   "again.\n(Re-analysing calls the API again.) Continue?", n=len(photos))) \
                != QMessageBox.StandardButton.Yes:
            return
        ids = [l.id for l in self.labels]
        keys = [p.key for p in photos]
        self.db.delete_scores(keys, ids)
        for lid in ids:
            self.db.set_manual_many(keys, lid, None)
        for p in photos:
            p.scores.clear()
            p.manual.clear()
            self.model.touch(p.key)
        self.db.commit()
        self._refresh_filters()

    def _fill_takeoff_menu(self, m: QMenu, photos: list[Photo] | None = None) -> None:
        m.clear()
        sel = self.selected_photos() if photos is None else photos
        if sel:
            head = m.addAction(tr("Selected photos: {n}", n=len(sel)))
        else:
            head = m.addAction(tr("No selection – all {n} photos in view", n=self.proxy.rowCount()))
        head.setEnabled(False)

        def run(fn):
            ps = sel or self._scope(True)
            if ps:
                fn(ps)

        m.addAction(tr("Remove all labels   (Backspace)"),
                    lambda: run(lambda ps: self.take_off(self.labels, photos=ps)))
        sub = m.addMenu(tr("Remove one label"))
        for l in self.labels:
            sub.addAction(label_icon(l), l.name, lambda l=l: run(lambda ps: self.take_off([l], photos=ps)))
        m.addSeparator()
        m.addAction(tr("Clear manual changes (back to the AI's decision)"), lambda: run(self.back_to_ai))
        m.addAction(tr("Clear AI results (can be re-analysed)"), lambda: run(self.clear_ai_results))

    def _label_key(self, n: int) -> None:
        if n >= len(self.labels):
            return
        photos = self.selected_photos()
        if not photos:
            return
        l = self.labels[n]
        value = 0 if all(p.has(l) for p in photos) else 1
        self.set_manual(photos, l, value)
        msg = tr("“{name}” added to {n} photos") if value else tr("“{name}” removed from {n} photos")
        self.statusBar().showMessage(msg.format(name=l.name, n=len(photos)), 3000)

    def _context_menu(self, pos) -> None:
        photos = self.selected_photos()
        if not photos:
            return
        m = QMenu(self)
        m.addAction(self.a_view)
        m.addAction(tr("Mark a face on this photo…"), lambda: self.open_viewer(face_mode=True))
        m.addSeparator()
        m.addAction(self.a_an_sel)
        m.addAction(self.a_an_force)
        add = m.addMenu(tr("Add label"))
        for l in self.labels:
            add.addAction(label_icon(l), l.name, lambda l=l: self.set_manual(photos, l, 1))
        add.addSeparator()
        add.addAction(tr("New label…"), self.add_label)
        off = m.addMenu(tr("Remove labels"))
        self._fill_takeoff_menu(off, photos)
        m.addSeparator()
        coll = m.addMenu(tr("Add to collection"))
        for cid, name, _n in self.db.collections():
            coll.addAction(name, lambda cid=cid: self.add_selection_to_collection(cid))
        coll.addSeparator()
        coll.addAction(tr("New collection from selection…"), self.selection_to_new_collection)
        if self.source and self.source[0] == "collection":
            m.addAction(tr("Remove from collection (file is kept)"), lambda: self.remove_from_collection(photos))
        m.addSeparator()
        m.addAction(self.a_organize)
        m.addAction(tr("Show in file manager"), lambda: self.reveal(photos[0].path))
        m.exec(self.grid.viewport().mapToGlobal(pos))

    @staticmethod
    def reveal(path: str) -> None:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        elif sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    # ================================================================== AI analysis

    def _analyze_default(self) -> None:
        sel = self.selected_photos()
        self.analyze_photos(sel if len(sel) > 0 else self.visible_photos())

    def analyze_photos(self, photos: list[Photo], force: bool = False, only: list[Label] | None = None) -> None:
        if self.analyze_job is not None:
            QMessageBox.information(self, tr("Analysis"), tr("An analysis is already running."))
            return
        if not photos:
            QMessageBox.information(self, tr("Analysis"), tr("No selected or visible photos."))
            return
        if not self.labels:
            QMessageBox.information(self, tr("Analysis"), tr("Add at least one label first."))
            self.add_label()
            return
        key = self.settings.api_key()
        if not key:
            QMessageBox.information(self, tr("Analysis"), tr("Enter your TypeSafe API key in Settings."))
            self.open_settings()
            key = self.settings.api_key()
            if not key:
                return
        tasks = []
        for p in photos:
            if only is not None:  # e.g. ask Jev about a person where local face recognition found nothing
                missing = [l for l in only if not p.has(l) and l.id not in p.manual]
            else:
                missing = [l for l in self.labels if l.applies(p.path)] if force else p.missing(self.labels)
            if missing:
                tasks.append((p.path, p.key, p.fsig, missing))
        if not tasks and only is not None:
            QMessageBox.information(self, tr("Analysis"), tr("Nothing to check – the person is already on every "
                                                             "photo of this view."))
            return
        if not tasks:
            hidden = [p for p in photos if any(v == 0 for v in p.manual.values())]
            if hidden:
                ok = QMessageBox.question(
                    self, tr("Analysis"),
                    tr("These photos are already analysed. On {n} of them labels were removed by hand, so the AI's "
                       "labels are hidden there.\n\nShow the AI's labels again on these {n} photos?", n=len(hidden)))
                if ok == QMessageBox.StandardButton.Yes:
                    self.back_to_ai(hidden)
            else:
                QMessageBox.information(self, tr("Analysis"), tr("These photos are already analysed for every label."))
            return
        if len(tasks) > 1:
            q = sum(len(t[3]) for t in tasks)
            people = sum(1 for t in tasks for l in t[3] if l.is_person)
            extra = tr("\nPeople are compared using their reference faces, which adds image tokens.") if people else ""
            ok = QMessageBox.question(
                self, tr("Analyse with Jev"),
                tr("Analyse {n} photos ({q} questions, one API call per photo, {px} px images)?",
                   n=len(tasks), q=q, px=self.settings.get("ai_max_side")) + extra,
            )
            if ok != QMessageBox.StandardButton.Yes:
                return
        try:
            client = JevClient(key, self.settings.get("model"))
        except JevError as e:
            QMessageBox.warning(self, tr("Analysis"), str(e))
            return
        self.errors = []
        job = AnalyzeJob(client, tasks, self.settings.get("ai_max_side"), self.settings.get("concurrency"))
        job.result.connect(self._on_result)
        job.failed.connect(lambda k, msg: self.errors.append(f"{os.path.basename(k)}: {msg}"))
        job.progress.connect(self._on_progress)
        job.finished.connect(self._on_analyze_done)
        self.analyze_job = job
        self.a_stop.setEnabled(True)
        self.progress.setRange(0, len(tasks))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        job.start()

    def _on_result(self, key: str, fsig: str, values: dict) -> None:
        self.db.put_scores(key, fsig, values)
        p = self.model.photo_by_key(key)
        if p is not None and p.fsig == fsig:
            p.scores.update({lid: v for lid, (v, _qh) in values.items()})
            self.model.touch(key)
            if self.viewer is not None and self.viewer.current.key == key:
                self.viewer.refresh_panel()
        self._commit_timer.start()
        self._refresh_timer.start()

    def _on_progress(self, done: int, total: int, tokens: int) -> None:
        self.progress.setValue(done)
        err = tr(" · {n} errors", n=len(self.errors)) if self.errors else ""
        self.statusBar().showMessage(tr("Analysing: {done}/{total}", done=done, total=total) + err +
                                     tr(" · {t} input tokens", t=f"{tokens:,}".replace(",", " ")))

    def _on_analyze_done(self, cancelled: bool, message: str) -> None:
        self.analyze_job = None
        self.a_stop.setEnabled(self.org_job is not None)
        self.progress.setVisible(False)
        self.db.commit()
        self._refresh_filters()
        self.statusBar().showMessage(message, 15000)
        if self.errors:
            self._show_errors(tr("Analysis errors"), self.errors)

    def stop_jobs(self) -> None:
        if self.analyze_job is not None:
            self.analyze_job.cancel()
            self.statusBar().showMessage(tr("Stopping… (requests in progress will still finish)"))
        if self.org_job is not None:
            self.org_job.cancel()

    def _show_errors(self, title: str, errors: list[str]) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(title)
        box.setText(tr("{n} errors occurred.", n=len(errors)))
        box.setDetailedText("\n".join(errors[:500]))
        box.exec()

    def on_theme_changed(self) -> None:
        self._rebuild_filter_list()
        self._refresh_faces()
        self.grid.viewport().update()

    # ================================================================== automatic faces (local)

    def start_face_scan(self, photos: list[Photo], manual: bool = False) -> None:
        if not FACES_OK:
            return
        done = self.db.scanned({p.key for p in photos})
        tasks = [(p.key, p.path, p.fsig) for p in photos if done.get(p.key) != p.fsig]
        if not tasks:
            if manual:
                self.faces_panel.set_status(tr("All photos in this view are scanned."))
            return
        if self.face_job is not None:
            self.face_job.cancel()
        job = FaceScanJob(tasks)
        job.result.connect(self._on_face_result)
        job.progress.connect(lambda d, t: self.faces_panel.set_status(tr("Finding faces… {d}/{t}", d=d, t=t)))
        job.finished.connect(lambda job=job: self._on_face_done(job))
        self.face_job = job
        self.faces_panel.scan_btn.setEnabled(False)
        job.start()

    def _on_face_result(self, key: str, path: str, fsig: str, faces: list) -> None:
        self.face_index.ensure()
        old = [r[0] for r in self.db.faces_on(key)]
        if old:
            self.face_index.forget_keys(old)
        ids = self.db.store_faces(key, path, fsig, faces)
        self.face_index.add(ids, faces)
        people = [l.id for l in self.labels if l.is_person]
        self.db.refresh_person_scores(people, [key])
        p = self.model.photo_by_key(key)
        if p is not None and people:
            self._load_scores([p])
            self.model.touch(key)
        self._commit_timer.start()
        self._faces_timer.start()
        if people:
            self._refresh_timer.start()

    def _on_face_done(self, job) -> None:
        if job is self.face_job:
            self.face_job = None
            self.faces_panel.scan_btn.setEnabled(True)
            self.faces_panel.set_status("")
        self.db.commit()
        self._refresh_faces()

    def _face_groups(self) -> tuple[list[dict], dict]:
        """Groups of faces on the loaded photos: named people first, then unnamed groups by size."""
        keys = {p.key for p in self.model.photos}
        rows = self.db.face_rows(keys) if keys else []
        people = {l.id: l for l in self.labels if l.is_person}
        groups: dict[tuple, dict] = {}
        for fid, key, person, cluster, hidden, score in rows:
            if hidden:
                continue
            if person and person in people:
                gk = ("person", person)
            elif cluster is not None:
                gk = ("cluster", cluster)
            else:
                continue
            g = groups.setdefault(gk, {"keys": set(), "best": (-1.0, fid), "ids": []})
            g["keys"].add(key)
            g["ids"].append(fid)
            if score > g["best"][0]:
                g["best"] = (score, fid)
        out = []
        for (kind, ident), g in groups.items():
            out.append({"kind": kind, "id": ident, "count": len(g["keys"]), "best": g["best"][1],
                        "name": people[ident].name if kind == "person" else "",
                        "color": people[ident].color if kind == "person" else None})
        out.sort(key=lambda g: (g["kind"] != "person", -g["count"]))
        return out, groups

    def _refresh_faces(self) -> None:
        groups, _ = self._face_groups()
        for g in groups:
            row = self.db.face_detail(g["best"])
            g["thumb"] = row[5] if row else None
        self.faces_panel.set_groups(groups)

    def _face_group_clicked(self, kind: str, ident) -> None:
        if kind == "person":
            self.proxy.key_filter = None
            self.proxy.special = None
            if self.faces_panel.active is None:
                self.proxy.include.discard(ident)
            else:
                self.proxy.include = {ident}
                self.proxy.exclude.discard(ident)
        else:
            if self.faces_panel.active is None:
                self.proxy.key_filter = None
            else:
                _, groups = self._face_groups()
                self.proxy.key_filter = set(groups.get((kind, ident), {}).get("keys", set()))
        self._refresh_filters()

    def _name_face_group(self, kind: str, ident, jev: bool = False) -> None:
        if kind == "person":
            label = next((l for l in self.labels if l.id == ident), None)
            if label:
                self.edit_label(label)
            return
        _, groups = self._face_groups()
        g = groups.get((kind, ident))
        if not g:
            return
        best = self.db.face_detail(g["best"][1])
        people = [l for l in self.labels if l.is_person]
        dlg = PersonDialog(best[5] or b"", people, self, show_search=False)
        dlg.search_now.setChecked(jev)
        if not dlg.exec():
            return
        person = self._assign_faces_to(dlg.person_name(), g["ids"])
        if dlg.search_now.isChecked():
            self.find_person_with_jev(person)

    def _assign_faces_to(self, name: str, face_ids: list[int], ref_crops: list[bytes] | None = None) -> Label:
        """Give faces a person (new or existing by name) and mark that person on every scanned photo."""
        people = [l for l in self.labels if l.is_person]
        existing = next((l for l in people if l.name.casefold() == name.casefold()), None)
        if existing is None:
            used = {l.color for l in self.labels}
            color = next((c for c in PALETTE if c not in used), PALETTE[len(self.labels) % len(PALETTE)])
            person = Label(name, "", 0.6, color, kind="person", faces=[], scope="")
        else:
            person = deepcopy(existing)
        # reference face crops (used as the person's picture and for Jev on photos without a face scan)
        crops = list(ref_crops or [])
        if len(person.faces) < 3:
            for fid in face_ids[: 3 - len(person.faces)]:
                d = self.db.face_detail(fid)
                if d:
                    try:
                        crops.append(crop_face(d[0], (d[1], d[2], d[3], d[4])))
                    except Exception:  # noqa: BLE001
                        pass
        for c in crops:
            fname = f"{uuid.uuid4().hex}.jpg"
            (faces_dir() / fname).write_bytes(c)
            person.faces.append(fname)
        if existing is None:
            labels = self.labels + [person]
        else:
            labels = [person if l.id == existing.id else l for l in self.labels]
        if face_ids and self.face_index is not None:
            self.face_index.name_faces(face_ids, person.id)
        self.db.refresh_person_scores([person.id])
        self.db.commit()
        self._set_labels(labels)
        n = sum(1 for p in self.model.photos if p.has(person))
        self.statusBar().showMessage(tr("{name} found on {n} photos in this view", name=person.name, n=n), 6000)
        return person

    def find_person_with_jev(self, label: Label) -> None:
        """Local recognition is very reliable for frontal faces; Jev compares the reference faces on the rest."""
        if not label.faces:
            QMessageBox.information(self, tr("Analysis"), tr("{name} has no reference face yet.", name=label.name))
            return
        self.analyze_photos(self.visible_photos(), only=[label])

    def _ignore_face_group(self, kind: str, ident) -> None:
        if kind == "person":
            label = next((l for l in self.labels if l.id == ident), None)
            if label and QMessageBox.question(
                    self, tr("Forget the name"),
                    tr("Forget the name “{name}”? Its faces become unnamed again; the person label is deleted.",
                       name=label.name)) == QMessageBox.StandardButton.Yes:
                self._set_labels([l for l in self.labels if l.id != ident])
            return
        _, groups = self._face_groups()
        g = groups.get((kind, ident))
        if g:
            self.face_index.hide(g["ids"])
            self.db.commit()
            self.proxy.key_filter = None
            self._refresh_filters()
            self._refresh_faces()

    # ================================================================== labels & settings

    def _new_label_scope(self) -> str:
        """New labels belong to the folder that is open (for a collection: the folder its photos share)."""
        if self.source and self.source[0] == "folder":
            return self.source[1]
        return self._base_dir()

    def add_label(self) -> None:
        if not self.source:
            QMessageBox.information(self, tr("New filter / label"),
                                    tr("Open a folder first – new labels belong to the folder they are made in."))
            return
        dlg = LabelEditDialog(None, [l.color for l in self.labels], self)
        if dlg.exec():
            folder = self._new_label_scope()
            dlg.label.scope, dlg.label.folders = "folder", [folder]
            self._set_labels(self.labels + [dlg.label])
            self.statusBar().showMessage(
                tr("New label “{name}” for the folder {folder}. Only this one question is sent for photos that were "
                   "already analysed.", name=dlg.label.name, folder=os.path.basename(folder) or folder), 8000)

    def edit_label(self, label) -> None:
        scores = [p.scores[label.id] for p in self.model.photos if label.id in p.scores]
        dlg = LabelEditDialog(label, [l.color for l in self.labels if l.id != label.id], self,
                              scores=scores, total=len(self.model.photos))
        if dlg.exec():
            self._set_labels([dlg.label if l.id == label.id else l for l in self.labels])

    def delete_label(self, label) -> None:
        text = (tr("Delete the person “{name}”?\nTheir reference faces, AI results and manual decisions are "
                   "deleted too. Image files are not changed.", name=label.name) if label.is_person else
                tr("Delete the label “{name}”?\nIts AI results and manual decisions are deleted too. "
                   "Image files are not changed.", name=label.name))
        if QMessageBox.question(self, tr("Delete"), text) == QMessageBox.StandardButton.Yes:
            self._set_labels([l for l in self.labels if l.id != label.id])

    def edit_labels(self) -> None:
        dlg = LabelsDialog(self.labels, self)
        if dlg.exec():
            self._set_labels(dlg.labels)

    def _active_labels(self, photos: list[Photo]) -> list[Label]:
        """Built-ins and people everywhere; folder labels only where the view has photos from that folder."""
        dirs = {norm_dir(os.path.dirname(p.path)) for p in photos}
        folder = norm_dir(self.source[1]) if self.source and self.source[0] == "folder" else None
        out = []
        for l in self.all_labels:
            if not l.folder_only:
                out.append(l)
                continue
            for f in map(norm_dir, l.folders):
                if folder and (folder == f or folder.startswith(f + os.sep) or f.startswith(folder + os.sep)) \
                        or any(d == f or d.startswith(f + os.sep) for d in dirs):
                    out.append(l)
                    break
        return out

    def _folder_of_view_in(self, label) -> str | None:
        """The label folder that the current folder view belongs to (for “remove from this folder”)."""
        if not label.folder_only or not self.source or self.source[0] != "folder":
            return None
        cur = norm_dir(self.source[1])
        return next((f for f in label.folders if cur == norm_dir(f) or cur.startswith(norm_dir(f) + os.sep)), None)

    def remove_label_from_folder(self, label, folder: str) -> None:
        if QMessageBox.question(
                self, tr("Remove from this folder"),
                tr("Stop using “{name}” in {folder}? It stays in its other folders.", name=label.name,
                   folder=os.path.basename(folder.rstrip("/\\")) or folder)) != QMessageBox.StandardButton.Yes:
            return
        new = deepcopy(label)
        new.folders = [f for f in label.folders if f != folder]
        self._set_labels([new if l.id == label.id else l for l in self.labels])

    def _migrate_label_scopes(self) -> None:
        """Labels from older versions applied everywhere; tie them to the folder(s) where they were used."""
        changed = False
        last = str(self.settings._q.value("last_source", "") or "")
        fallback = last[7:] if last.startswith("folder:") else ""
        library = [p for p, _c, _r in self.db.folders()]
        lib_norm = {norm_dir(p): p for p in library}

        def owning_folder(d: str) -> str:
            nd = norm_dir(d)
            best = max((f for f in lib_norm if nd == f or nd.startswith(f + os.sep)), key=len, default=None)
            return lib_norm[best] if best else d

        for l in self.all_labels:
            if l.builtin or l.kind == "person":
                continue
            # 0.4 could tie a label to a common parent (e.g. the Desktop) – redo those from the actual results
            too_wide = l.folder_only and any(
                norm_dir(f) not in lib_norm and sum(x.startswith(norm_dir(f) + os.sep) for x in lib_norm) > 1
                for f in l.folders)
            if l.scope is not None and not too_wide:
                continue
            changed = True
            dirs = {os.path.dirname(r[0]) for r in self.db.con.execute(
                "SELECT path FROM scores WHERE label_id=? UNION SELECT path FROM manual WHERE label_id=?",
                (l.id, l.id))}
            folders = sorted({owning_folder(d) for d in dirs}) or ([fallback] if fallback else [])
            if folders:
                l.scope, l.folders = "folder", folders
            else:
                l.scope, l.folders = "", []
        if changed:
            save_labels(self.all_labels)
            self.labels = [l for l in self.all_labels if not l.folder_only]

    def _set_labels(self, labels) -> None:
        """``labels`` is the edited list of labels of the current view; labels of other folders are kept."""
        shown = {l.id for l in self.labels}
        for l in labels:
            if l.scope is None:  # created in the labels table
                if l.is_person:
                    l.scope = ""
                else:
                    l.scope, l.folders = "folder", [self._new_label_scope()]
        kept_builtins = [l for l in self.labels if l.builtin and l.id not in {x.id for x in labels}]
        new_all = labels + kept_builtins + [l for l in self.all_labels if l.id not in shown]
        from facet.storage import ensure_builtins

        new_all = ensure_builtins(new_all)
        old_ids = {l.id for l in self.all_labels}
        old_faces = {f for l in self.all_labels for f in l.faces}
        self.all_labels = new_all
        save_labels(self.all_labels)
        self.labels = self._active_labels(self.model.photos)
        for lid in old_ids - {l.id for l in self.all_labels}:
            if self.face_index is not None and self.face_index.loaded:
                self.face_index.unname(lid)
            self.db.drop_label(lid)
        self.db.commit()
        for f in old_faces - {f for l in self.all_labels for f in l.faces}:
            try:
                (faces_dir() / f).unlink()  # reference faces that no person uses any more (Facet's own files)
            except OSError:
                pass
        self.proxy.include &= {l.id for l in self.labels}
        self.proxy.exclude &= {l.id for l in self.labels}
        self._load_scores(self.model.photos)  # edited questions / new faces invalidate their old scores
        self._rebuild_filter_list()
        self.model.touch_all()
        self._faces_timer.start()
        if self.viewer is not None:
            self.viewer.refresh_panel()

    def open_settings(self) -> None:
        SettingsDialog(self.settings, str(cache_dir() / "thumbs"), self).exec()

    def _about(self) -> None:
        QMessageBox.about(
            self, APP_NAME,
            f"<b>{APP_NAME} {__version__}</b><br>" + tr("AI photo culling and sorting with TypeSafe Jev.") +
            "<br><br>" + tr("RAW support: {raw} · HEIC support: {heic}",
                            raw=tr("yes") if RAW_OK else tr("no"), heic=tr("yes") if HEIF_OK else tr("no")),
        )

    # ================================================================== organize

    def organize(self) -> None:
        if not self.model.photos or self.org_job is not None:
            return
        sel = self.selected_photos()
        counts = {"selected": len(sel), "filtered": self.proxy.rowCount(), "all": len(self.model.photos)}
        dlg = OrganizeDialog(counts, self._base_dir() or os.path.expanduser("~"), "selected" if sel else "filtered",
                             self)
        if not dlg.exec():
            return
        cfg = dlg.config()
        photos = {"selected": sel, "filtered": self.visible_photos(), "all": list(self.model.photos)}[cfg["scope"]]
        if not photos:
            QMessageBox.information(self, tr("Sorting"), tr("There are no photos in the chosen scope."))
            return
        if cfg["by_label"]:
            ops = organizer.plan_by_labels(photos, self.labels, cfg["base"], cfg["move"], cfg["unlabeled"],
                                           cfg["sidecars"])
        else:
            ops = organizer.plan_to_folder(photos, cfg["target"], cfg["sidecars"])
        if not ops:
            QMessageBox.information(self, tr("Sorting"), tr("Nothing to sort – the chosen photos have no labels."))
            return
        prim = [o for o in ops if o.primary]
        per_dir = Counter(o.dst_dir for o in prim)
        lines = [tr("• {folder}: {n} photos", folder=os.path.basename(d) or d, n=n) for d, n in per_dir.most_common(15)]
        if len(per_dir) > 15:
            lines.append(tr("• … and {n} more folders", n=len(per_dir) - 15))
        side = len(ops) - len(prim)
        text = (tr("Move: {n} photos", n=len(prim)) if cfg["move"] else tr("Copy: {n} photos", n=len(prim)))
        if side:
            text += tr(" + {n} companion files", n=side)
        text += tr("\nTarget: {dir}", dir=os.path.dirname(next(iter(per_dir)))) + "\n\n" + "\n".join(lines)
        if QMessageBox.question(self, tr("Confirm sorting"), text) != QMessageBox.StandardButton.Yes:
            return
        job = organizer.OrganizeJob(ops, cfg["move"])
        job.progress.connect(lambda d, t: (self.progress.setRange(0, t), self.progress.setValue(d)))
        job.finished.connect(lambda done, errs: self._on_organized(job, done, errs))
        self.org_job = job
        self.a_stop.setEnabled(True)
        self.progress.setVisible(True)
        job.start()

    def _on_organized(self, job, done: list, errors: list) -> None:
        self.org_job = None
        self.a_stop.setEnabled(self.analyze_job is not None)
        self.progress.setVisible(False)
        for op in done:
            if op.primary:
                if job.move:
                    self.db.rename(path_key(op.src), path_key(op.dst), op.dst)
                else:
                    self.db.duplicate(path_key(op.src), path_key(op.dst))
        self.db.commit()
        if done:
            self.last_op = (done, job.move, job.created_dirs)
            self.a_undo.setEnabled(True)
        n = sum(1 for o in done if o.primary)
        msg = tr("Moved: {n} photos", n=n) if job.move else tr("Copied: {n} photos", n=n)
        if errors:
            msg += tr(", {n} errors", n=len(errors))
        self.statusBar().showMessage(msg, 15000)
        if job.move:
            self.reload()
        self.library.refresh()
        if errors:
            self._show_errors(tr("Sorting errors"), errors)

    def undo_organize(self) -> None:
        if not self.last_op or self.org_job is not None:
            return
        done, moved, created = self.last_op
        n = sum(1 for o in done if o.primary)
        text = (tr("Move {n} photos back to where they were?", n=n) if moved else
                tr("The {n} copies that were made will go to the Trash. Continue?", n=len(done)))
        if QMessageBox.question(self, tr("Undo"), text) != QMessageBox.StandardButton.Yes:
            return
        errors = organizer.undo(done, moved, created)
        for op in done:
            if op.primary:
                if moved:
                    self.db.rename(path_key(op.dst), path_key(op.src), op.src)
                else:
                    self.db.remove(path_key(op.dst))
        self.db.commit()
        self.last_op = None
        self.a_undo.setEnabled(False)
        self.reload()
        self.library.refresh()
        if errors:
            self._show_errors(tr("Undo errors"), errors)
        else:
            self.statusBar().showMessage(tr("Undone."), 5000)

    # ================================================================== window events

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls() and e.source() is None:  # from Finder / Explorer, not our own grid
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        dirs = [p for p in paths if os.path.isdir(p)]
        if dirs:
            for d in dirs[1:]:
                self.db.add_folder(os.path.abspath(d))
            self.open_folder(dirs[0])
            return
        files = [p for p in paths if os.path.isfile(p)]
        if files and self.source and self.source[0] == "collection":
            self.db.add_to_collection(self.source[1], files)
            self.library.refresh()
            self.reload()
        elif files:
            self.open_folder(os.path.dirname(files[0]))

    def closeEvent(self, e) -> None:
        if self.org_job is not None:
            QMessageBox.information(self, APP_NAME, tr("Please wait until sorting the files has finished."))
            e.ignore()
            return
        if self.analyze_job is not None:
            self.analyze_job.cancel()
        if self.face_job is not None:
            self.face_job.cancel()
        if self.viewer is not None:
            self.viewer.close()
        self.settings._q.setValue("geometry", self.saveGeometry())
        self.sidebar.save()
        self.settings._q.setValue("center/sizes", self.center.sizes())
        for t in (self._faces_timer, self._refresh_timer, self._search_timer, self._commit_timer):
            t.stop()  # no delayed work may touch the database after it is closed
        self.thumbs.shutdown()
        self.db.close()
        super().closeEvent(e)
