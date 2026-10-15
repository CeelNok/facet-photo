<p align="center">
  <img src="facet/assets/facet.png" width="120" alt="Facet logó">
</p>

<h1 align="center">Facet</h1>

<p align="center">
  <b>AI-alapú fotóválogatás és -rendezés fotósoknak – címkék, személyek és mappák pár kattintással.</b><br>
  Natív asztali alkalmazás macOS-re és Windowsra · a <a href="https://docs.typesafe.ai/introduction">TypeSafe JEV</a> modelljével
</p>

<p align="center"><i><a href="README.md">English</a></i></p>

<p align="center">
  <img src="docs/screenshot-light-hu.png" alt="Facet – világos mód" width="900">
</p>

---

## Mit tud?

Megadsz egy mappát (esküvő, nyaralás, fotózás). A Facet gyors rácsban mutatja az összes képet. Az AI minden képet
végignéz a **saját címkéid** szerint („elmosódott”, „csukott szem”, „a pár csókolózik”…), és **felismeri a képeken
szereplő embereket**. Utána szűrsz, nagyítasz, javítasz, és mappákba rendezed a képeket.

| | |
|---|---|
| 🏷 **Címkék** | Öt **beépített címke** mindig, minden mappában ott van: *Elmosódott, Mosolyog valaki, Csukott szem, Túlexponált, Alulexponált*. A **saját címkéid** (**+ Új szűrő**) ahhoz a mappához tartoznak, ahol létrehoztad őket, így egy esküvő „Csók” címkéje nem jelenik meg a nyaralós képeknél. Minden címke egy igen/nem kérdés a JEV-nek; a küszöb utólag, élő előnézettel állítható („12 / 92 kép · legmagasabb pontszám 81%”), újraelemzés nélkül. |
| 👤 **Személyek** | Az arcokat a Facet **a gépeden** automatikusan megtalálja és csoportosítja. Egy csoportot elnevezel, és onnantól az új képeken is felismeri az illetőt. Oldalnézethez és kis arcokhoz a JEV is kereshet a referenciaarcokkal. |
| 🔎 **Szűrés és kijelölés** | Címkék és személyek bevonása (✓) vagy kizárása (✕), bármelyik/mindegyik feltétel, elemezetlen, címke nélküli, csak RAW, fájlnév. A találatos címkék vannak felül, és bármely címke valószínűsége szerint rendezhetsz. |
| 📁 **Rendezés mappákba** | Címkénként vagy személyenként külön almappába, vagy mind egy mappába. Másolhatsz vagy áthelyezhetsz, a kísérő fájlok (`.xmp`, `.aae`, RAW+JPEG pár) is mennek. Minden művelet visszavonható; visszavonáskor a másolatok a Kukába kerülnek. |
| 🖼 **Nézegető** | Teljes képernyős nézegető zoommal (görgő, csíptetés, 100%), nyilas lapozással, címkekapcsolókkal és arckijelöléssel. A RAW a beágyazott előnézettel nyílik meg, nagyításkor teljes minőségben hívja elő. |
| 📚 **Könyvtár** | A mappák és a gyűjtemények (több mappán átívelő virtuális albumok) a Lightroomhoz hasonlóan az oldalsávon maradnak, a *Legutóbb megnyitott képekkel* együtt. Az oldalsáv minden része összecsukható és átméretezhető. |
| 🌗 **Modern felület** | Lekerekített, letisztult megjelenés világos és sötét módban (a rendszer szerint), magyarul és angolul. |

## Indítás

```bash
git clone https://github.com/CeelNok/facet-photo.git
```

### macOS
1. Klónozd a tárolót (fent), vagy töltsd le ZIP-ként (**Code → Download ZIP**).
2. Kattints duplán a projektmappában a **`Facet.app`**-ra (a Facet logós ikonra).
   Az első indításkor saját Python-környezetet állít be, ez kb. 1–2 perc.
   - Python 3.10+ kell ([python.org](https://www.python.org/downloads/) vagy Homebrew), vagy a [uv](https://docs.astral.sh/uv/).
   - Ha ZIP-ként töltötted le, és a macOS letiltja („ismeretlen fejlesztő”): **Rendszerbeállítások →
     Adatvédelem és biztonság → Megnyitás mindenképp** (egyszer kell). `git clone` esetén ez nem jelentkezik.

### Windows
1. Telepítsd a [Python 3.10+](https://www.python.org/downloads/) verziót, és pipáld be: **„Add python.exe to PATH”**.
2. Kattints duplán a **`Facet.bat`**-ra. Az első indítás mindent telepít, és létrehoz egy logós **Facet**
   parancsikont a mappában. Ezt kitűzheted a Startra vagy a tálcára.

### JEV API kulcs
Kulcsot itt igényelhetsz: <https://console.typesafe.ai/keys>. Utána: **Beállítások → API kulcs → Kapcsolat
tesztelése**. A kulcs a Facet adatmappájában, egy csak számodra olvasható fájlban tárolódik. A Facet nem használja a
rendszer kulcstartóját, ezért soha nem kér jelszót.

## Jó címkék írása

- **Angol kérdés, a képre `` `photo` `` néven hivatkozva.** Ha sima leírást írsz (bármilyen nyelven), a Facet
  „Does `photo` match this description?” kérdéssé alakítja, de a közvetlen angol kérdés pontosabb.
  Példa: *Are the bride and groom kissing in `photo`?*
- **Címkénként egy dolog.** A „szép esküvői kép” helyett: *csók*, *mosolyog*, *csukott szem*.
- **Állítsd be a küszöböt.** Jobb klikk a címkén → *Szerkesztés…* megmutatja, hány kép felel meg az adott
  küszöbbel, és mekkora a legmagasabb pontszám.

## Személyek

- **Automatikusan:** mappanyitáskor a Facet megkeresi az arcokat, és csoportosítja az azonos személyeket. A
  csoportok kerek kis képekként jelennek meg a rács alatti **Felismert arcok** sávban. Kattintásra az illető képei
  látszanak, dupla kattintással elnevezheted.
- **Kézzel:** a nézegetőben **F**, keret az arc köré, majd név.
- **Oldalnézet, kis arcok:** jobb klikk a személyen → *Keresés JEV AI-jal is*. A JEV a referenciaarcokkal azokon a
  képeken keres, ahol a helyi felismerés nem talált.
- A helyi felismerés (OpenCV YuNet + SFace) ingyenes, semmit nem tölt fel, egy CPU-szálon fut, és a Beállításokban
  kikapcsolható.

## Billentyűk

| Billentyű | Rács | Nézegető |
|---|---|---|
| `Szóköz` / `Enter` / dupla katt | nézegető megnyitása | bezárás |
| `1` – `9` | 1–9. címke ki/be a kijelölésen | 1–9. címke ki/be |
| `Backspace` | minden címke levétele (rákérdez) | minden címke levétele |
| `← →` | – | előző / következő |
| `Z` / dupla katt | – | 100% ↔ illesztés |
| `F` | – | arc kijelölése |
| `Cmd/Ctrl + A` / `E` / `M` / `Z` | mind kijelölése / elemzés / rendezés / visszavonás | – |

## Adatvédelem, energia, memória

- **Helyben maradnak a képek:** csak JEV-elemzéskor megy ki egy kicsinyített JPEG (alapból 1024 px). Az
  arcfelismerés soha nem hagyja el a gépet.
- **Takarékos működés:** üresjáratban ~0% CPU. Csak a látható képek töltődnek be. A JPEG DCT-skálázással
  dekódolódik, a RAW-hoz a beágyazott előnézetet használja.
- **Kötött memória:** a memóriában lévő bélyegkép-gyorsítótár legfeljebb ~96 MB, a nézegető egyszerre legfeljebb
  két képet tart a memóriában.

## Önálló alkalmazás készítése

```bash
./build_mac.sh          # → dist/Facet.app
build_windows.bat       # → dist\Facet\Facet.exe (Windowson)
```

## Harmadik féltől származó összetevők

Lásd: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Licenc

A Facet az [MIT licenc](LICENSE) alatt érhető el. A harmadik féltől származó összetevők a saját licencük alá
tartoznak (lásd: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
