"""Hungarian translations (source strings are English)."""

HU = {
    # analyzer / client / organizer / models
    "Analysis stopped: {e}": "Elemzés leállítva: {e}",
    "Analysis finished: {n} photos": "Elemzés kész: {n} kép",
    "Analysis cancelled.": "Elemzés megszakítva.",
    ", {n} errors": ", {n} hiba",
    " · {t} input tokens": " · {t} input token",
    "Unknown error": "Ismeretlen hiba",
    "No API key set.": "Nincs megadva API kulcs.",
    "Network error: {e}": "Hálózati hiba: {e}",
    " (manual)": " (kézi)",
    "a file with this name already exists at the original location": "az eredeti helyen már van ilyen nevű fájl",
    "could not move it to the Trash": "nem sikerült a Kukába helyezni",

    # labels dialog
    "Labels": "Címkék",
    "Every label is a yes/no question for Jev. Refer to the image as <code>`photo`</code>. "
    "Jev returns a 0–100% probability; the label is applied when it reaches the threshold. "
    "Thresholds can be changed later without re-analysing. Labels 1–9 can also be toggled "
    "with the number keys. People (👤) are created by marking a face in the viewer.":
        "Minden címke egy igen/nem kérdés a JEV-nek. A képre <code>`photo`</code> néven hivatkozhatsz. "
        "A JEV 0–100% valószínűséget ad; a címke akkor kerül a képre, ha ez eléri a küszöböt. "
        "A küszöb később is állítható, újraelemzés nélkül. Az 1–9. címke a számbillentyűkkel is "
        "kapcsolható. Személyt (👤) a nézegetőben egy arc kijelölésével hozhatsz létre.",
    "Name": "Név",
    "Question for Jev (English works best)": "Kérdés a JEV-nek (angolul a legpontosabb)",
    "Threshold %": "Küszöb %",
    "Color": "Szín",
    "New label": "Új címke",
    "Delete": "Törlés",
    "👤 Person · {n} reference faces": "👤 Személy · {n} referenciaarc",
    "Label color": "Címke színe",

    # label / person editor
    "New filter / label": "Új szűrő / címke",
    "Edit person": "Személy szerkesztése",
    "Edit label": "Címke szerkesztése",
    "e.g. Dog in the photo": "pl. Kutya van rajta",
    "e.g. Is there a dog in `photo`?  (left empty: built from the name)":
        "pl. Is there a dog in `photo`?  (üresen hagyva a névből készül)",
    "Name:": "Név:",
    "Question for Jev:": "Kérdés a JEV-nek:",
    "Threshold:": "Küszöb:",
    "Color:": "Szín:",
    "Remove selected faces": "Kijelölt arcok eltávolítása",
    "<b>Reference faces</b> – the newest {n} are sent to Jev. Add more by marking this person's face on "
    "other photos (different angles help).":
        "<b>Referenciaarcok</b> – a legújabb {n} megy a JEV-nek. Továbbiakat úgy adhatsz hozzá, hogy más "
        "képeken is kijelölöd az arcát (a különböző szögek segítenek).",
    "Changing the reference faces re-checks this person on the next analysis.":
        "Ha a referenciaarcok változnak, a következő elemzés újra megkeresi ezt a személyt.",
    "Jev answers this yes/no question for every photo. English questions are the most accurate; refer to the "
    "image as <code>`photo`</code>. For a new label only this one question is sent for photos that were already "
    "analysed.":
        "A JEV minden képnél erre az igen/nem kérdésre válaszol. Angol kérdéssel a legpontosabb; a képre "
        "<code>`photo`</code> néven hivatkozz. Új címkénél a már elemzett képekhez csak ez az egy kérdés megy ki.",
    "Add": "Hozzáadás",
    "Save": "Mentés",
    "Reference faces": "Referenciaarcok",
    "A person needs at least one reference face.": "Egy személyhez legalább egy referenciaarc kell.",

    # face naming
    "Who is this?": "Ki ez?",
    "Find this person in the current view now (uses the Jev API)":
        "Keresse meg most ezt a személyt az aktuális nézetben (JEV API-hívás)",
    "Pick an existing person to add another reference face (more angles = better results), or type a new name.":
        "Válassz meglévő személyt, ha újabb referenciaarcot adsz hozzá (több szög = jobb találat), "
        "vagy írj be új nevet.",
    "Save face": "Arc mentése",

    # settings
    "Settings": "Beállítások",
    "TypeSafe API key (console.typesafe.ai/keys)": "TypeSafe API kulcs (console.typesafe.ai/keys)",
    "Show": "Mutat",
    "Test connection": "Kapcsolat tesztelése",
    "Automatic (system language)": "Automatikus (rendszer nyelve)",
    "Clear thumbnail cache ({mb} MB)": "Bélyegkép-gyorsítótár törlése ({mb} MB)",
    "Language:": "Nyelv:",
    "API key:": "API kulcs:",
    "Model:": "Modell:",
    "Parallel AI requests:": "Párhuzamos AI kérések:",
    "Image size sent to AI:": "AI-nak küldött képméret:",
    "Thumbnail threads:": "Bélyegkép-szálak:",
    "A smaller AI image means fewer tokens and faster uploads; 1024 px is enough for most labels. Blur detection "
    "and recognising people in group shots are more accurate with larger images. Language and thumbnail threads "
    "apply after a restart; fewer threads use less energy.":
        "Kisebb AI képméret = kevesebb token és gyorsabb feltöltés; 1024 px a legtöbb címkéhez elég. Az "
        "elmosódás és a csoportképeken lévő személyek felismerése nagyobb mérettel pontosabb. A nyelv és a "
        "bélyegkép-szálak újraindítás után érvényesek; kevesebb szál kevesebb energiát fogyaszt.",
    "Thumbnail cache cleared": "Bélyegkép-gyorsítótár törölve",
    "Connection": "Kapcsolat",
    "Connected. Model: {m}": "Sikeres kapcsolat. Modell: {m}",
    "Error: {e}": "Hiba: {e}",
    "Language": "Nyelv",
    "Restart Facet to switch the language.": "A nyelv a Facet újraindítása után vált át.",

    # organize dialog
    "Sort into folders": "Rendezés mappákba",
    "Selected photos": "Kijelölt képek",
    "All photos in the filtered view": "A szűrt nézet összes képe",
    "All photos": "Összes kép",
    "By label – one subfolder per label or person": "Címkék szerint – címkénként / személyenként külön almappába",
    "All into one folder": "Mind egy mappába",
    "Copy (originals stay)": "Másolás (az eredeti marad)",
    "Move": "Áthelyezés",
    "Sorted": "Rendezett",
    "Selected": "Kiválogatott",
    "Photos without labels into an “Other” folder": "Címke nélküli képek egy „Egyéb” mappába",
    "Include companion files (.xmp, .aae, RAW+JPEG pairs with the same name)":
        "Kísérő fájlok is (.xmp, .aae, azonos nevű RAW+JPEG pár)",
    "When moving, a photo can only go to one place: the first matching label in label order wins. Conflicting "
    "file names get a number (“photo (1).jpg”). This can be undone.":
        "Áthelyezésnél egy kép csak egy helyre kerülhet: a címkék sorrendjében első találat dönt. Ütköző "
        "fájlnévnél sorszámot kap („kép (1).jpg”). A művelet visszavonható.",
    "Browse…": "Tallózás…",
    "What and how?": "Mit és hogyan?",
    "Photos:": "Képek:",
    "   Target (label folders are created in it):": "   Célmappa (ebben jönnek létre a címke-mappák):",
    "   Target folder:": "   Célmappa:",
    "Operation": "Művelet",
    "Next…": "Tovább…",
    "Target folder": "Célmappa",
    "Other": "Egyéb",

    # library panel
    "Folders": "Mappák",
    "Add a folder to the library": "Mappa hozzáadása a könyvtárhoz",
    "Click to open · drop a folder here to add it to the library":
        "Kattintás: megnyitás · ide húzott mappa bekerül a könyvtárba",
    "Collections": "Gyűjtemények",
    "New collection": "Új gyűjtemény",
    "Drag photos from the grid or your file manager onto a collection to add them":
        "Képeket a rácsból vagy a fájlkezelőből egy gyűjteményre húzva adhatsz hozzá",
    "Recently opened photos": "Legutóbb megnyitott képek",
    "Photos you recently opened in the viewer": "A nézegetőben legutóbb megnyitott képek",
    "Open": "Megnyitás",
    "Show in file manager": "Mutatás a fájlkezelőben",
    "Remove from list (files are kept)": "Eltávolítás a listából (a fájlok maradnak)",
    "Collection name:": "A gyűjtemény neve:",
    "Added {n} photos to {name}": "{n} kép hozzáadva: {name}",
    "Add photos": "Képek hozzáadása",
    "Images": "Képek",
    "Rename": "Átnevezés",
    "New name:": "Új név:",
    "Folder": "Mappa",
    "This folder is not available:\n{path}": "A mappa nem érhető el:\n{path}",
    "New collection…": "Új gyűjtemény…",
    "Delete collection": "Gyűjtemény törlése",
    "Delete the collection “{name}”?\nThe image files are not deleted.":
        "Törlöd a(z) „{name}” gyűjteményt?\nA képfájlok nem törlődnek.",
    "Clear list": "Lista ürítése",
    "Add selected photos": "Kijelölt képek hozzáadása",
    "Add photos from files…": "Képek hozzáadása fájlból…",
    "Rename…": "Átnevezés…",
    "Delete collection (photos are kept)": "Gyűjtemény törlése (a képek maradnak)",
    "\n(including subfolders)": "\n(almappákkal)",
    "\nFolder not available (disconnected drive?)": "\nA mappa nem érhető el (leválasztott meghajtó?)",

    # main window
    "All photos": "Összes kép",
    "Not analysed": "Elemezetlen",
    "No labels": "Címke nélküli",
    "Photos loaded: {n}": "Betöltött képek: {n}",
    "Add folder…": "Mappa hozzáadása…",
    "Refresh": "Frissítés",
    "Subfolders": "Almappákkal",
    "Also load photos from the open folder's subfolders": "A megnyitott mappa almappáinak képeit is betölti",
    "Analyse selected photos": "Kijelölt képek elemzése",
    "Analyse filtered view": "Szűrt nézet elemzése",
    "All unanalysed photos": "Az összes elemezetlen kép",
    "Re-analyse selected (all labels)": "Kijelöltek újraelemzése (minden címke)",
    "Stop": "Leállítás",
    "Labels…": "Címkék…",
    "New filter / label…": "Új szűrő / címke…",
    "Mark a face…": "Arc kijelölése…",
    "Sort into folders…": "Rendezés mappákba…",
    "Undo sorting": "Rendezés visszavonása",
    "Settings…": "Beállítások…",
    "Select all": "Mind kijelölése",
    "Select none": "Kijelölés megszüntetése",
    "Open in viewer": "Megnyitás nézegetőben",
    "Selected photos to a new collection…": "Kijelöltek új gyűjteménybe…",
    "Toolbar": "Eszköztár",
    "Analyse with Jev": "Elemzés JEV-vel",
    "Analyses the selected photos, or the unanalysed photos of the filtered view":
        "Kijelölés esetén a kijelölt képeket, különben a szűrt nézet elemezetlen képeit elemzi",
    "Remove labels": "Címke levétele",
    "Remove labels from the selected photos (no selection: from the whole view)":
        "Címkék levétele a kijelölt képekről (kijelölés nélkül: a nézet összes képéről)",
    "Search file names…": "Keresés fájlnévben…",
    "Thumbnail size": "Bélyegkép méret",
    "Library": "Könyvtár",
    "Click: only these (✓) · Alt/Option-click: exclude (✕)\nRight-click: edit, remove from photos, delete":
        "Kattintás: csak ezek (✓) · Alt/Option+kattintás: kizárás (✕)\n"
        "Jobb gomb: szerkesztés, levétel a képekről, törlés",
    "Filters": "Szűrők",
    "Add a new filter": "Új szűrő hozzáadása",
    "+ New filter": "+ Új szűrő",
    "People": "Személyek",
    "Mark a face on the current photo": "Arc kijelölése az aktuális képen",
    "+ Mark a face": "+ Arc kijelölése",
    "Any checked label": "Bármelyik bejelölt címke",
    "All checked labels": "Minden bejelölt címke",
    "All file types": "Minden fájltípus",
    "RAW only": "Csak RAW",
    "No RAW (JPEG, HEIC…)": "RAW nélkül (JPEG, HEIC…)",
    "Sort by:": "Rendezés:",
    "Clear filters": "Szűrők törlése",
    "Select visible photos": "Látható képek kijelölése",
    "Warning: rawpy is not installed, RAW files cannot be loaded.":
        "Figyelem: a rawpy nincs telepítve, RAW fájlok nem tölthetők be.",
    "File": "Fájl",
    "Quit": "Kilépés",
    "Edit": "Szerkesztés",
    "Photos": "Képek",
    "Help": "Súgó",
    "TypeSafe documentation": "TypeSafe dokumentáció",
    "About {app}": "{app} névjegy",
    "Loading…": "Betöltés…",
    " · {n} files not found (moved or deleted)": " · {n} fájl nem található (áthelyezték vagy törölték)",
    "Collection": "Gyűjtemény",
    "Select some photos in the grid first.": "Előbb jelölj ki képeket a rácsban.",
    "New collection with {n} photos": "Új gyűjtemény {n} képpel",
    "Date (newest first)": "Dátum (legújabb elöl)",
    "Date (oldest first)": "Dátum (legrégebbi elöl)",
    "File size (largest first)": "Fájlméret (nagy elöl)",
    "Added / opened order": "Hozzáadás / megnyitás sorrendje",
    "{name} – probability": "{name} – valószínűség",
    "Person · {n} reference faces": "Személy · {n} referenciaarc",
    "\nThreshold: {t}%": "\nKüszöb: {t}%",
    "\nShortcut for selected photos: {k}": "\nGyorsbillentyű a kijelölt képekre: {k}",
    "Add new filter…": "Új szűrő hozzáadása…",
    "Mark a face to add a person…": "Személy felvétele arc kijelölésével…",
    "Only these (✓)": "Csak ezek (✓)",
    "Exclude (✕)": "Kizárás (✕)",
    "Clear condition": "Feltétel törlése",
    "Remove “{name}” from selected photos ({n})": "„{name}” levétele a kijelölt képekről ({n})",
    "Remove “{name}” from all photos in view ({n})": "„{name}” levétele a nézet összes képéről ({n})",
    "Edit…": "Szerkesztés…",
    "Delete person…": "Személy törlése…",
    "Delete label (filter)…": "Címke (szűrő) törlése…",
    "{total} photos · {visible} visible · {sel} selected": "{total} kép · {visible} látható · {sel} kijelölt",
    "Mark a face": "Arc kijelölése",
    "Open a folder first.": "Előbb nyiss meg egy mappát.",
    "Select a photo of the person first, then drag a box around their face.":
        "Jelölj ki egy képet, amelyen az illető szerepel, majd húzz keretet az arca köré.",
    "Could not cut out the face: {e}": "Nem sikerült kivágni az arcot: {e}",
    "No photos are selected. Apply to all {n} photos in the view?":
        "Nincs kijelölt kép. A nézet mind a(z) {n} képére vonatkozzon?",
    "All labels": "Minden címke",
    "{what} removed from {n} photos": "{what} levéve {n} képről",
    "Manual changes cleared on {n} photos (the AI decides again)":
        "Kézi módosítások törölve {n} képen (az AI döntése érvényes)",
    "Clear AI results": "AI-eredmények törlése",
    "AI results and manual labels of {n} photos will be cleared and they become “not analysed” again.\n"
    "(Re-analysing calls the API again.) Continue?":
        "{n} kép AI-eredményei és kézi címkéi törlődnek, a képek újra „elemezetlenek” lesznek.\n"
        "(Újraelemzéskor ismét API-hívás történik.) Folytatod?",
    "Selected photos: {n}": "Kijelölt képek: {n}",
    "No selection – all {n} photos in view": "Nincs kijelölés – a nézet {n} képe",
    "Remove all labels   (Backspace)": "Minden címke levétele   (Backspace)",
    "Remove one label": "Egy címke levétele",
    "Clear manual changes (back to the AI's decision)": "Kézi módosítások törlése (vissza az AI döntésére)",
    "Clear AI results (can be re-analysed)": "AI-eredmények törlése (újraelemezhető)",
    "“{name}” added to {n} photos": "„{name}” rákerült {n} képre",
    "“{name}” removed from {n} photos": "„{name}” lekerült {n} képről",
    "Mark a face on this photo…": "Arc kijelölése ezen a képen…",
    "Add label": "Címke hozzáadása",
    "New label…": "Új címke…",
    "Add to collection": "Hozzáadás gyűjteményhez",
    "New collection from selection…": "Új gyűjtemény a kijelöltekből…",
    "Remove from collection (file is kept)": "Eltávolítás a gyűjteményből (a fájl marad)",
    "Analysis": "Elemzés",
    "An analysis is already running.": "Már fut egy elemzés.",
    "No selected or visible photos.": "Nincs kijelölt vagy látható kép.",
    "Add at least one label first.": "Előbb adj meg legalább egy címkét.",
    "Enter your TypeSafe API key in Settings.": "Add meg a TypeSafe API kulcsodat a beállításokban.",
    "These photos are already analysed for every label.": "Ezek a képek már minden címkére elemezve vannak.",
    "\nPeople are compared using their reference faces, which adds image tokens.":
        "\nA személyeket a referenciaarcaikkal hasonlítja össze, ez plusz képtokent jelent.",
    "Analyse {n} photos ({q} questions, one API call per photo, {px} px images)?":
        "{n} kép elemzése ({q} kérdés, képenként 1 API-hívás, {px} px-es képpel). Indulhat?",
    "Analysing: {done}/{total}": "Elemzés: {done}/{total}",
    " · {n} errors": " · {n} hiba",
    "Analysis errors": "Elemzési hibák",
    "Stopping… (requests in progress will still finish)": "Leállítás… (a folyamatban lévő kérések még befejeződnek)",
    "{n} errors occurred.": "{n} hiba történt.",
    "Delete the person “{name}”?\nTheir reference faces, AI results and manual decisions are deleted too. "
    "Image files are not changed.":
        "Törlöd a(z) „{name}” személyt?\nA referenciaarcai, AI-eredményei és kézi döntései is törlődnek. "
        "A képfájlok nem változnak.",
    "Delete the label “{name}”?\nIts AI results and manual decisions are deleted too. Image files are not "
    "changed.":
        "Törlöd a(z) „{name}” címkét?\nA hozzá tartozó AI-eredmények és kézi döntések is törlődnek. "
        "A képfájlok nem változnak.",
    "AI photo culling and sorting with TypeSafe Jev.": "AI-alapú fotóválogatás és -rendezés a TypeSafe JEV-vel.",
    "RAW support: {raw} · HEIC support: {heic}": "RAW támogatás: {raw} · HEIC támogatás: {heic}",
    "yes": "igen",
    "no": "nem",
    "Sorting": "Rendezés",
    "There are no photos in the chosen scope.": "Nincs kép a kiválasztott körben.",
    "Nothing to sort – the chosen photos have no labels.": "Nincs mit rendezni – a kiválasztott képeken nincs címke.",
    "• {folder}: {n} photos": "• {folder}: {n} kép",
    "• … and {n} more folders": "• … és még {n} mappa",
    "Move: {n} photos": "Áthelyezés: {n} kép",
    "Copy: {n} photos": "Másolás: {n} kép",
    " + {n} companion files": " + {n} kísérő fájl",
    "\nTarget: {dir}": "\nCél: {dir}",
    "Confirm sorting": "Rendezés jóváhagyása",
    "Moved: {n} photos": "Áthelyezve: {n} kép",
    "Copied: {n} photos": "Másolva: {n} kép",
    "Sorting errors": "Rendezési hibák",
    "Move {n} photos back to where they were?": "{n} kép visszahelyezése az eredeti helyére?",
    "The {n} copies that were made will go to the Trash. Continue?":
        "A létrehozott {n} másolat a Kukába kerül. Folytatod?",
    "Undo": "Visszavonás",
    "Undo errors": "Visszavonási hibák",
    "Undone.": "Visszavonva.",
    "Please wait until sorting the files has finished.": "Várd meg, amíg a fájlok rendezése befejeződik.",

    # viewer
    "Facet – viewer": "Facet – nézegető",
    "<b>Labels</b> <span style='color:gray'>(keys 1–9)</span>":
        "<b>Címkék</b> <span style='color:gray'>(1–9 billentyű)</span>",
    "👤  Mark a face  (F)": "👤  Arc kijelölése  (F)",
    "Drag a box around a face and give it a name. Facet will then find this person on your other photos.":
        "Húzz keretet egy arc köré, és nevezd el. A Facet ezután megkeresi ezt a személyt a többi képen is.",
    "Remove all labels  (⌫)": "Összes címke levétele  (⌫)",
    "Back to the AI's decision": "Vissza az AI döntésére",
    "Clear manual changes on this photo": "A kézi módosítások törlése ennél a képnél",
    "Analyze with Jev (this photo)": "Elemzés JEV-vel (ez a kép)",
    "Develop RAW at full quality": "RAW előhívása teljes minőségben",
    "← → browse · scroll / pinch: zoom\ndouble-click or Z: 100% ↔ fit · 0: fit\n"
    "1–9: toggle label · ⌫: remove all labels\nF: mark a face · I: panel · Esc: close":
        "← → lapozás · görgő / csíptetés: zoom\ndupla katt vagy Z: 100% ↔ illesztés · 0: illesztés\n"
        "1–9: címke ki/be · ⌫: összes címke le\nF: arc kijelölése · I: panel · Esc: bezárás",
    "\nDeveloping RAW…": "\nRAW előhívás folyamatban…",
    "Could not load:\n{e}": "Nem sikerült betölteni:\n{e}",
    " · manual": " · kézi",
    "Drag a box around a face…": "Húzz keretet egy arc köré…",

    # automatic faces
    "Stored in a private file in Facet's data folder – no keychain, no password prompts.":
        "A Facet adatmappájában, egy csak számodra olvasható fájlban tárolódik – nincs kulcstartó, nincs jelszókérés.",
    "Find faces automatically when a folder opens (on this computer, free)":
        "Arcok automatikus keresése mappanyitáskor (ezen a gépen, ingyenes)",
    "Faces:": "Arcok:",
    "Faces in this view": "Felismert arcok ebben a nézetben",
    "Find faces": "Arcok keresése",
    "Detect and group faces on the photos of this view (runs on this computer, free, nothing is uploaded)":
        "Megkeresi és csoportosítja az arcokat a nézet képein (ezen a gépen fut, ingyenes, semmi nem töltődik fel)",
    "No faces yet. Press “Find faces” – or they are found automatically after a folder opens (Settings).":
        "Még nincsenek arcok. Nyomd meg az „Arcok keresése” gombot – vagy mappanyitáskor automatikusan "
        "megtalálja őket (Beállítások).",
    "Show these photos": "Ezek a képek",
    "Name this person…": "Személy elnevezése…",
    "Ignore (not a person / not interesting)": "Figyelmen kívül hagyás (nem személy / nem érdekes)",
    "Edit person…": "Személy szerkesztése…",
    "Forget the name (faces become unnamed)": "Név elfelejtése (az arcok névtelenek lesznek)",
    "{name} · on {n} photos\nClick: show these photos · double-click: edit":
        "{name} · {n} képen\nKattintás: ezek a képek · dupla katt: szerkesztés",
    "Unnamed person · on {n} photos\nClick: show these photos · double-click: name":
        "Névtelen személy · {n} képen\nKattintás: ezek a képek · dupla katt: elnevezés",
    "Unnamed": "Névtelen",
    "{name} found on {n} photos in this view": "{name} {n} képen szerepel ebben a nézetben",
    "Face recognition is not available (OpenCV missing).": "Az arcfelismerés nem érhető el (hiányzik az OpenCV).",
    "All photos in this view are scanned.": "A nézet minden képén megtörtént az arckeresés.",
    "Finding faces… {d}/{t}": "Arcok keresése… {d}/{t}",
    "Forget the name": "Név elfelejtése",
    "Forget the name “{name}”? Its faces become unnamed again; the person label is deleted.":
        "Elfelejted a(z) „{name}” nevet? Az arcok újra névtelenek lesznek, a személy-címke törlődik.",

    # safety / layout
    "all {n} labels": "mind a(z) {n} címkét",
    "Remove {names} from {n} photos?\nThe AI will not add them back. You can undo this with Remove labels → "
    "Clear manual changes.":
        "Leveszed: {names} – {n} képről?\nAz AI nem teszi vissza őket. Visszavonás: Címke levétele → Kézi "
        "módosítások törlése.",
    "These photos are already analysed. On {n} of them labels were removed by hand, so the AI's labels are hidden "
    "there.\n\nShow the AI's labels again on these {n} photos?":
        "Ezek a képek már elemezve vannak. Közülük {n} képről kézzel le lettek véve a címkék, ezért ott nem "
        "látszanak az AI címkéi.\n\nMegjelenjenek újra az AI címkéi ezen a(z) {n} képen?",
    "Show / hide faces": "Arcok megjelenítése / elrejtése",

    # label editor preview / people with Jev
    "Tip: English yes/no questions about `photo` work best, e.g. “Are the bride and groom kissing in `photo`?”":
        "Tipp: angol, igen/nem kérdéssel a legpontosabb, pl. „Are the bride and groom kissing in `photo`?”",
    "With this threshold: {n} of {total} photos · highest AI score: {top}%":
        "Ezzel a küszöbbel: {n} / {total} kép · legmagasabb AI-pontszám: {top}%",
    "No AI results for this label in the current view yet.": "Ehhez a címkéhez még nincs AI-eredmény ebben a nézetben.",
    "The question changed – it will be re-checked on the next analysis (only this one question is sent).":
        "A kérdés megváltozott – a következő elemzéskor újra ellenőrzi (csak ez az egy kérdés megy ki).",
    "Also search with Jev AI for side views and small faces (uses the API)":
        "Keresse a JEV AI is (oldalnézet, kis arcok – API-hívással jár)",
    "Also search with Jev AI (side views, small faces)…": "Keresés JEV AI-jal is (oldalnézet, kis arcok)…",
    "View": "Nézet",
    "Also search for {name} with Jev AI (side views, small faces)…":
        "{name} keresése JEV AI-jal is (oldalnézet, kis arcok)…",
    "Nothing to check – the person is already on every photo of this view.":
        "Nincs mit ellenőrizni – a személy már minden képen szerepel ebben a nézetben.",
    "{name} has no reference face yet.": "{name} személynek még nincs referenciaarca.",
    "Name and also search with Jev AI (side views, small faces)…":
        "Elnevezés és keresés JEV AI-jal is (oldalnézet, kis arcok)…",

    # built-in labels (names follow the UI language) and folder labels
    "Blurry": "Elmosódott",
    "Smiling": "Mosolyog valaki",
    "Eyes closed": "Csukott szem",
    "Overexposed": "Túlexponált",
    "Underexposed": "Alulexponált",
    "Built-in label – used in every folder": "Beépített címke – minden mappában szerepel",
    "Built-in labels cannot be deleted – they are used in every folder. You can change their threshold.":
        "A beépített címkék nem törölhetők – minden mappában szerepelnek. A küszöbük állítható.",
    "Built-in label – used in every folder. Its question is fixed; the threshold and colour can be changed.":
        "Beépített címke – minden mappában szerepel. A kérdése rögzített; a küszöb és a szín állítható.",
    "Open a folder first – new labels belong to the folder they are made in.":
        "Előbb nyiss meg egy mappát – az új címke ahhoz a mappához tartozik, ahol létrehozod.",
    "New label “{name}” for the folder {folder}. Only this one question is sent for photos that were already "
    "analysed.":
        "Új címke („{name}”) a(z) {folder} mappához. A már elemzett képekhez csak ez az egy kérdés megy ki.",
    "Only in: {folders}": "Csak itt: {folders}",
    "Remove from this folder ({folder})": "Eltávolítás ebből a mappából ({folder})",
    "Remove from this folder": "Eltávolítás ebből a mappából",
    "Stop using “{name}” in {folder}? It stays in its other folders.":
        "Ne legyen „{name}” a(z) {folder} mappában? A többi mappájában megmarad.",
    "API key, language, faces, performance": "API kulcs, nyelv, arcok, teljesítmény",
    "Include subfolders": "Almappákkal együtt",
}
