#!/usr/bin/env python3
"""
Update the Zen mods (themes) you already have installed. The manifest
(zen-themes.json) lists which files each mod has (chrome.css, preferences.json,
readme.md). Each file is fetched from the mod's own GitHub repo — via the
theme.json on its main branch, found from the manifest's homepage, which is also
where variant source names like userChrome.css are resolved. Only when a file
cannot be retrieved from source does that single file fall back to the URL
recorded in zen-themes.json. Then sync new and removed keys into prefs.js and
regenerate the compiled zen-themes.css.

Usage:
    ./update-zen-mods.py [--dry-run] [--force]

Flags:
    --dry-run  Preview only; download and diff, but write nothing.
    --force    Skip the "is Zen running?" safety check.

The profile is auto-detected from profiles.ini (the profile Zen launches).
"""

import argparse
import fcntl
import json
import os
import shutil
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ZEN_DIR = Path.home() / "Library/Application Support/zen"


# --- Reused helpers ---------------------------------------------------------
# Kept as functions only because each is called from more than one place;
# inlining them would duplicate their bodies.

def http_get(url):
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read()
    except Exception:
        return None


def pref_key(line):
    line = line.strip()
    if line.startswith("user_pref("):
        try:
            return line.split('"', 2)[1]
        except IndexError:
            return None
    return None


def parse_schema(data):
    if data is None:
        return []
    try:
        schema = json.loads(data.decode("utf-8"))
    except Exception:
        return []
    if not isinstance(schema, list):
        return []
    return [entry for entry in schema if isinstance(entry, dict)]


def load_schema(path):
    if not path.is_file():
        return []
    try:
        return parse_schema(path.read_bytes())
    except Exception:
        return []


def collect_schema(entry_lists):
    """Flatten schema entry lists into property -> entry (first definition wins)."""
    schema = {}
    for entries in entry_lists:
        for entry in entries:
            prop = entry.get("property")
            if prop:
                schema.setdefault(prop, entry)
    return schema


def main():
    # --- Parse arguments ----------------------------------------------------
    parser = argparse.ArgumentParser(
        description="Update the Zen mods (themes) you already have installed.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only; download and diff, but write nothing.")
    parser.add_argument("--force", action="store_true",
                        help='Skip the "is Zen running?" safety check.')
    args = parser.parse_args()
    dry_run = args.dry_run
    force = args.force

    # --- Resolve the profile Zen launches (from profiles.ini) ---------------
    ini = ZEN_DIR / "profiles.ini"
    profile = None
    section = ""
    for line in ini.read_text().splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section.startswith("[Install") and line.startswith("Default="):
            rel = line[len("Default="):]
            profile = Path(rel) if os.path.isabs(rel) else ZEN_DIR / rel
            break
    if profile is None:
        sys.exit(f"ERROR: could not resolve a profile from {ini}.")

    mods_dir = profile / "chrome" / "zen-themes"
    manifest_path = profile / "zen-themes.json"
    compiled_css = profile / "chrome" / "zen-themes.css"
    prefs_path = profile / "prefs.js"

    # --- Validate before touching anything ----------------------------------
    if not profile.is_dir():
        sys.exit(f"ERROR: profile not found: {profile}")
    if not manifest_path.is_file():
        sys.exit(f"ERROR: manifest not found: {manifest_path}")
    if not prefs_path.is_file():
        sys.exit(f"ERROR: prefs.js not found: {prefs_path}")
    # Zen is running if its .parentlock is held (a non-blocking lock fails).
    if not force:
        lock = profile / ".parentlock"
        running = False
        if lock.exists():
            fd = os.open(lock, os.O_RDWR)
            try:
                fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.lockf(fd, fcntl.LOCK_UN)
            except OSError:
                running = True
            finally:
                os.close(fd)
        if running:
            sys.exit("ERROR: Zen appears to be running. Quit Zen completely, then "
                     "re-run (or pass --force).")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Snapshot the current preferences schema before it is overwritten, so the
    # prefs.js diff is computed in memory and previews correctly under --dry-run.
    old_schema = collect_schema(load_schema(mods_dir / mid / "preferences.json")
                                for mid in manifest)

    # --- Back up the current state ------------------------------------------
    backup = profile / "zen-mods-backup"
    if not dry_run:
        if backup.exists():
            shutil.rmtree(backup)
        shutil.copytree(mods_dir, backup / "zen-themes")
        if compiled_css.is_file():
            shutil.copy2(compiled_css, backup / "zen-themes.css")
        shutil.copy2(prefs_path, backup / "prefs.js")
    print(f"Backup created: {backup}\n")

    # --- Sync each mod's files, source-first with manifest fallback ---------
    print("Updating mod source files...")
    incoming = []  # per-mod incoming preferences schemas -> becomes new_schema
    for mid, mod in manifest.items():
        # The manifest decides which files exist, their canonical local names,
        # and the fallback URL for each.
        manifest_urls = {
            "chrome.css": mod.get("style"),
            "preferences.json": mod.get("preferences"),
            "readme.md": mod.get("readme"),
        }
        homepage = mod.get("homepage")
        link = homepage or \
            f"https://github.com/zen-browser/theme-store/tree/main/themes/{mid}"

        # Turn the homepage into a raw.githubusercontent.com base (handling
        # tree/blob URLs with a branch and subpath), then read the mod's own
        # theme.json to learn where each file actually lives on that branch.
        # This is where variant source names (userChrome.css, subpaths, full-URL
        # readmes) map back to our canonical local filenames. source_files stays
        # empty when there is no usable theme.json.
        source_files = {}
        raw_base = None
        if homepage:
            parsed = urlparse(homepage)
            parts = parsed.path.strip("/").split("/")
            if parsed.netloc == "github.com" and len(parts) >= 2:
                owner, repo = parts[0], parts[1]
                if len(parts) >= 4 and parts[2] in ("tree", "blob"):
                    branch, subpath = parts[3], "/".join(parts[4:])
                else:
                    branch, subpath = "main", ""
                raw_base = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/"
                if subpath:
                    raw_base += subpath.rstrip("/") + "/"
        if raw_base:
            theme_data = http_get(raw_base + "theme.json")
            try:
                theme = json.loads(theme_data.decode("utf-8")) if theme_data else {}
            except Exception:
                theme = {}
            if not isinstance(theme, dict):
                theme = {}
            style = theme.get("style")
            css = style.get("chrome") if isinstance(style, dict) else style
            candidates = {
                "chrome.css": css,
                "preferences.json": theme.get("preferences"),
                "readme.md": theme.get("readme"),
            }
            for name, ref in candidates.items():
                if isinstance(ref, str) and ref:
                    source_files[name] = ref if ref.startswith(("http://", "https://")) \
                        else raw_base + ref

        origins, lines = [], []
        for filename, manifest_url in manifest_urls.items():
            if not manifest_url:
                continue
            # Prefer the mod's own repo; fall back to the manifest copy only when
            # the file can't be retrieved from source.
            data = http_get(source_files.get(filename))
            if data is not None:
                origin = "source"
            else:
                data = http_get(manifest_url)
                origin = "manifest"

            # Make the local copy identical to the incoming file. A failed
            # download leaves the existing file untouched.
            dest = mods_dir / mid / filename
            if data is None:
                status = "failed"
            elif dest.exists() and dest.read_bytes() == data:
                status = "unchanged"
            else:
                status = "updated"
                if not dry_run:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)

            if data is not None:
                origins.append(origin)
            # The incoming preferences.json becomes the "new" schema; on a failed
            # fetch the existing file is left in place, so read that instead.
            if filename == "preferences.json":
                incoming.append(parse_schema(data) if data is not None
                                else load_schema(dest))

            if status == "updated":
                lines.append(f"    ↑ {filename} (updated)")
            elif status == "unchanged":
                lines.append(f"    · {filename} (unchanged)")
            else:
                lines.append(f"    ✗ {filename} (download failed, unchanged)")

        label = "source" if "source" in origins else "manifest"
        print(f"  {mod.get('name', mid)} - {link} [{label}]")
        for line in lines:
            print(line)
    print()
    new_schema = collect_schema(incoming)

    # --- Sync new/removed keys into prefs.js --------------------------------
    print("Merging prefs.js...")
    prefs_text = prefs_path.read_text(encoding="utf-8")
    existing = {k for k in map(pref_key, prefs_text.splitlines()) if k}

    # Diff the previous preferences.json against the incoming one.
    old_props = set(old_schema)
    new_props = set(new_schema)

    # Removed from preferences.json -> drop from prefs.js (only what's actually there).
    removed = sorted((old_props - new_props) & existing)
    # Added to preferences.json -> add to prefs.js only if it carries a default value.
    additions = []
    for prop in sorted(new_props - old_props):
        entry = new_schema[prop]
        if prop in existing or entry.get("defaultValue") is None:
            continue
        additions.append((prop, json.dumps(entry["defaultValue"])))

    for key, literal in additions:
        print(f"  + {key} = {literal}")
    for key in removed:
        print(f"  - {key}")
    if not additions and not removed:
        print("  · no changes to persist for prefs.js")

    if not dry_run and (additions or removed):
        removed_set = set(removed)
        kept = [l for l in prefs_text.splitlines() if pref_key(l) not in removed_set]
        out = "\n".join(kept).rstrip("\n") + "\n"
        out += "".join(f'user_pref("{k}", {lit});\n' for k, lit in additions)
        prefs_path.write_text(out, encoding="utf-8")
    print()

    # --- Regenerate the compiled zen-themes.css -----------------------------
    print("Regenerating zen-themes.css...")
    header = ("/* Zen Mods - Generated by ZenMods.\n"
              f"* FILE GENERATED AT: {datetime.now():%A, %B %-d, %Y at %-I:%M:%S %p}\n"
              "* DO NOT EDIT THIS FILE DIRECTLY!\n"
              "* Your changes will be overwritten.\n"
              "* Instead, go to the preferences and edit the mods there.\n"
              "*/")
    mod_blocks = []
    for mid, mod in manifest.items():
        css_file = mods_dir / mid / "chrome.css"
        if not mod.get("enabled") or not css_file.is_file():
            continue
        css = css_file.read_text(encoding="utf-8").rstrip("\n")
        author = (mod.get("author") or "").lstrip("@")
        mod_blocks.append(f"/* Name: {mod.get('name', '')} */\n"
                          f"/* Description: {mod.get('description', '')} */\n"
                          f"/* Author: @{author} */\n"
                          f"{css}")
    blocks = [header, *mod_blocks, "/* End of Zen Mods */"]
    if not dry_run:
        compiled_css.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    print(f"  ↑ wrote {len(mod_blocks)} mod(s) to zen-themes.css\n")

    if dry_run:
        print("Done. Re-run without --dry-run to apply.")
    else:
        print("Done. Restart Zen to apply the changes.")


if __name__ == "__main__":
    main()
