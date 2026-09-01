# Homebrew
eval "$(/opt/homebrew/bin/brew shellenv zsh)"

# Python
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"

# OrbStack
source ~/.orbstack/shell/init.zsh 2>/dev/null || :
