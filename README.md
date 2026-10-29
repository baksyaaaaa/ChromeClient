# Chrome Client

A personal Minecraft Java Edition launcher with a Modrinth-style look. Python + PySide6 (Qt).

## Files
- `launcher.py` - the launcher
- `pvp_packs.py` - builds the PvP color texture packs
- `sounds.py` - the creamy UI sounds
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

## Sign in (one-time setup)
Microsoft only lets Minecraft sign-ins through for apps registered with them, so you need your
own free app registration once. After that, signing in is one click and you stay signed in.

1. Go to https://portal.azure.com -> **Microsoft Entra ID** -> **App registrations** -> **New registration**.
2. Name it anything. Supported account types: **Personal Microsoft accounts only**.
3. Redirect URI: platform **Mobile and desktop applications**, value `http://localhost:3000/callback`.
4. Open **Authentication** and turn **Allow public client flows** on. Save.
5. Copy the **Application (client) ID** and paste it into the launcher: **Settings -> Azure client ID**.
6. **Request Minecraft API access** for your app at https://aka.ms/AppRegInfo. Microsoft approves
   these by hand and it can take a few days. Until then sign-in says the app isn't approved.
   Demo mode works meanwhile.
7. Click **Sign in** (bottom-left). Your browser opens, you log in, and the launcher picks it up on
   its own. No copying URLs.

You need to own Minecraft: Java Edition on the account you sign in with.

## PvP color packs
The packs are built on your PC from the Minecraft version you have installed (so run that version
once first). They recolor obsidian, crying obsidian, respawn anchor, glowstone, end crystal, totem,
ender pearl, golden apples, fire overlay, crosshair, sun, moon, clouds and the End sky.

Vanilla can't change the overworld sky color from a resource pack, so each pack also ships
OptiFine-style sky/fog colormaps for mods that read them. Without one, the overworld sky gradient
stays vanilla.

Make the zips without opening the launcher: `python pvp_packs.py 1.21.4 all`

## Notes
- Config lives in `~/.simple_mc_launcher/config.json`.
- Mods are installed to `<game folder>/mods`. Tick **Fabric** on the Play page to load them.
- Sounds use `winsound` (Windows), `afplay` (Mac) or `paplay`/`aplay`/`ffplay` (Linux).
