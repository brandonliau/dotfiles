set -e

DOTFILES="$HOME/.dotfiles"
ZEN_INI="$HOME/Library/Application Support/zen/profiles.ini"
ZEN_PROFILE_PATH=$(awk -F= '/^\[Install/{f=1} f && /^Default=/{print $2; exit}' "$ZEN_INI")

cp "$DOTFILES/zsh/.zshrc" "$HOME/.zshrc"
cp "$DOTFILES/zsh/.zprofile" "$HOME/.zprofile"
cp "$DOTFILES/vscode/settings.json" "$HOME/Library/Application Support/Code/User/settings.json"
cp "$DOTFILES/vscode/keybindings.json" "$HOME/Library/Application Support/Code/User/keybindings.json"
cp "$DOTFILES/ghostty/config.ghostty" "$HOME/Library/Application Support/com.mitchellh.ghostty/config.ghostty"
cp "$DOTFILES/zen/zen-keyboard-shortcuts.json" "$HOME/Library/Application Support/zen/$ZEN_PROFILE_PATH/zen-keyboard-shortcuts.json"
cp "$DOTFILES/zen/zen-themes.json" "$HOME/Library/Application Support/zen/$ZEN_PROFILE_PATH/zen-themes.json"
cp "$DOTFILES/zen/prefs.js" "$HOME/Library/Application Support/zen/$ZEN_PROFILE_PATH/prefs.js"
