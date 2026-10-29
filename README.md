# Chrome Client

A personal Minecraft Java Edition launcher with a Modrinth-style look. Python + PySide6 (Qt).

## Files
- `launcher.py` - the launcher
- `pvp_packs.py` - builds the PvP color texture packs
- `sounds.py` - the UI sounds
- `requirements.txt`

Keep all three `.py` files in the same folder.

## Run
```
pip install -r requirements.txt
python launcher.py
```
You need Java installed.

## What's in it
- **Play** - pick a version, Fabric on/off, PvP pack (Pink / Green / Blue / Orange / Red)
- **Mods** - search Modrinth and install Fabric mods in one click (required dependencies like
  Fabric API are installed too, and every download is checksum-verified)
- **Appearance** - recolor everything: background, cards/sidebar, accent and text. Presets
  (Classic, Green, Pink, Blue, Orange, Red, Purple) or pick any color / paste a hex code.
  Applies instantly and is remembered.
- **Settings** - RAM slider, game folder, Azure client ID, demo mode, UI sounds, and a custom click sound
  (pick any wav/mp3/ogg/flac; it's kept on your PC only and never uploaded with the project)
- Sign in with Microsoft from the bottom-left of the sidebar


