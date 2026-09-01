set -e

DOTFILES="$HOME/.dotfiles"
ZEN_INI="$HOME/Library/Application Support/zen/profiles.ini"
ZEN_PROFILE_PATH=$(awk -F= '/^\[Install/{f=1} f && /^Default=/{print $2; exit}' "$ZEN_INI")

cp "$HOME/.zshrc" "$DOTFILES/zsh/.zshrc"
cp "$HOME/.zprofile" "$DOTFILES/zsh/.zprofile"
cp "$HOME/Library/Application Support/Code/User/settings.json" "$DOTFILES/vscode/settings.json"
cp "$HOME/Library/Application Support/Code/User/keybindings.json" "$DOTFILES/vscode/keybindings.json"
cp "$HOME/Library/Application Support/com.mitchellh.ghostty/config.ghostty" "$DOTFILES/ghostty/config.ghostty"
cp "$HOME/Library/Application Support/zen/$ZEN_PROFILE_PATH/zen-keyboard-shortcuts.json" "$DOTFILES/zen/zen-keyboard-shortcuts.json"
