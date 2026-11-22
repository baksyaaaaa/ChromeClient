# Chrome Client

## Quick start (Windows)
1. Unzip this folder anywhere.
2. Double-click **setup.bat**. It installs the newest version of everything the launcher needs, makes a desktop shortcut and opens the launcher.
   (No Python yet? It installs Python for you with winget, or opens the download page if winget isn't available. Windows may show an "Install CPython now?" question: answer Y.)
   Windows SmartScreen may warn about setup.bat because the file isn't signed: click "More info", then "Run anyway".
3. Open it any time from the desktop shortcut, or double-click `start_chrome_client.pyw`.
4. To sign in with Microsoft you need your own Azure Application ID (Settings page, steps below). Demo mode works without one.

---

# Chrome Client

A personal Minecraft Java Edition launcher with a Modrinth-style look. Python + PySide6 (Qt).

## Files
- `launcher.py` - the launcher
- `pvp_packs.py` - builds the PvP color texture packs
- `sounds.py` - the creamy UI sounds
- `mods_sync.py` - sets aside mods that don't fit the version you launch
- `library.py` - lists your mods and texture packs and turns them on/off
- `requirements.txt`
- `start_chrome_client.pyw` - double-click to open with no terminal window
- `make_shortcut.bat` / `make_shortcut.py` - puts a Chrome Client shortcut (with icon) on your Desktop
- `chrome_client.ico` - the icon

Keep all the `.py` files in the same folder.

## Run
First time only: `pip install -r requirements.txt`

Then either double-click `start_chrome_client.pyw` (no terminal window), or double-click
`make_shortcut.bat` once to get a **Chrome Client** icon on your Desktop and use that.
(For debugging you can still run `python launcher.py` to see errors in a terminal.
If the app fails to start, the error is saved to `~/.simple_mc_launcher/crash.log`.)
You need Java installed.

## What's in it
- **Play** - pick a version, Fabric on/off, PvP pack (buttons: Pink / Green / Blue / Orange / Cherry Blossom)
- **Mods** - search Modrinth and install Fabric mods in one click (required dependencies like
  Fabric API are installed too, and every download is checksum-verified)
- **Texture packs** - search Modrinth for texture packs and install them in one click.
- **Library** - your installed mods (**My mods**) and texture packs (**My texture packs**) with an on/off switch each. Turning a mod off
  renames it to `.jar.disabled` (nothing is deleted). The launcher also
  checks what your mods need: it switches on mods you turned off that others depend on, and downloads missing ones
  from Modrinth (when you add a mod, turn one on, press **Install missing dependencies**, or press Play with Fabric).
  Turning off a mod that others need asks first. Each row also has a **Delete** button (asks first) for mods and texture packs. Texture packs are switched in `options.txt`, so close the
  game first. **Add texture pack...** copies a .zip into your resourcepacks folder, and 
- **Appearance** - make it yours. Background can be a solid color, a **gradient** (2 or 3 colors, any
  angle) or **your own picture**; "Darken" keeps text readable and "Glass cards" controls how see-through
  the cards and sidebar are. Color and gradient presets (Sunset, Ocean, Aurora, Cherry, Midnight, Mint...),
  plus custom colors for everything. Applies instantly and is remembered. Pictures you add are saved
  in `~/.simple_mc_launcher/backgrounds` (you add them once, then just click the one you want) and are
  never part of the project.
- **Settings** - RAM slider, game folder, Azure client ID, demo mode, UI sounds. In **Sounds** you can pick a
  different sound for each action (click, checkbox, dropdown, Play, success, error): the creamy default or your
  own library. **Add sounds...** takes as many wav/mp3/ogg/flac files as you like (up to 3 seconds each). Clicks
  change pitch a little every time (switch it off with the checkbox). Sounds stay on your PC only and are never
  uploaded with the project.
- Sign in with Microsoft from the bottom-left of the sidebar

## Mods and versions
Mods only work on the Minecraft version they were made for, but every version shares one `mods`
folder. When you press Play with **Fabric** ticked, the launcher reads each mod and moves the ones
that don't fit that version into `mods_disabled` (nothing is deleted). Switch back and they return.
Mods it can't read (not Fabric mods, damaged files) are never touched.

## Switching PvP packs while playing
Pressing **Play** builds all five color packs (the first launch of a version takes a few seconds).
Only the one you picked is switched on. You can change it without restarting:

- **Anywhere, no mod needed:** in game press Esc -> Options -> Resource Packs, and move a
  "Chrome Client PvP ..." pack to the right-hand (enabled) list. Resources reload right away.
- **Press O (needs the small Chrome Client mod):** a menu pops up with a button per color.
  It doesn't open while you're typing in chat. Build the mod from the `chrome-client-mod` folder
  (see the README inside it), then in the launcher go to **Mods -> Add mod file...** and pick the jar.
  Also tick **Fabric** on the Play page, and install **Fabric API** from the Mods list.

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

## PvP packs
The packs are built on your PC from the Minecraft version you have installed (so run that version
once first). They recolor obsidian, crying obsidian, respawn anchor, glowstone, end crystal, totem,
ender pearl, golden apples, fire overlay, crosshair, sun, moon, clouds and the End sky.

**Cherry Blossom** is its own style rather than a hue swap: soft pastel rose colors, with little pink and white
petals scattered over obsidian, glowstone, respawn anchors, end crystals, clouds and the End sky, and a crosshair with
four tiny petals in the corners (the middle stays clear). On top of that it turns **every oak, jungle, acacia, dark oak
and mangrove leaf in the world blossom pink** (vanilla reads leaf colors from a colormap, so no mod is needed), and it
has a detailed sakura blossom as its pack icon. It can't make petals fall in the air - that needs a mod.

All colors also tint the hotbar selection box, the XP bar and the hit particles (crits, damage).

Vanilla can't change the overworld sky color from a resource pack, so each pack also ships
OptiFine-style sky/fog colormaps for mods that read them. Without one, the overworld sky gradient
stays vanilla.

Make the zips without opening the launcher: `python pvp_packs.py 1.21.4 all`

## Notes
- Config lives in `~/.simple_mc_launcher/config.json`.
- Mods are installed to `<game folder>/mods`. Tick **Fabric** on the Play page to load them.
- Sounds use `winsound` (Windows), `afplay` (Mac) or `paplay`/`aplay`/`ffplay` (Linux).

## Performance (Settings page)
- **Entity culling** - the launcher installs the Entity Culling mod for you (Fabric on) so entities you can't see aren't drawn.
- The PvP color packs were removed; the launcher deletes any it made earlier.

## Discord Rich Presence (Settings > Discord)
Shows "In the launcher" / "Playing Minecraft <version>" on your Discord profile, with an elapsed timer. All the text is yours to edit
(`{version}` and `{loader}` get filled in). One-time setup: create an app at discord.com/developers, copy its **Application ID** into
Settings, and upload a picture named `logo` under Rich Presence > Art Assets. Needs the Discord desktop app open. Needs `discord_rpc.py`
next to `launcher.py`. It never shows your username or folders.

## Bundled mods
Jars placed in `bundled_mods/` (Chrome Client and YT Music) are copied into your mods folder automatically every time you launch with Fabric, replacing older copies of the same mod.

## Auto-updating Chrome Client and YT Music
On every launch with Fabric on (Minecraft 1.21.11) the launcher checks the newest GitHub Release of `baksyaaaaa/ChromeMod` and `baksyaaaaa/MusicMod`. It downloads a jar only when the release is new, puts it in the mods folder and removes the older copy. Offline or no release yet: it just launches.
