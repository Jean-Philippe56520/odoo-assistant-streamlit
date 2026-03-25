from colorama import init, Fore, Style

init(autoreset=True)

def H(txt):   # Header
    return Fore.CYAN + Style.BRIGHT + txt + Style.RESET_ALL

def OK(txt):  # Success
    return Fore.GREEN + Style.BRIGHT + txt + Style.RESET_ALL

def WARN(txt):
    return Fore.YELLOW + Style.BRIGHT + txt + Style.RESET_ALL

def ERR(txt):
    return Fore.RED + Style.BRIGHT + txt + Style.RESET_ALL

def DIM(txt):
    return Style.DIM + txt + Style.RESET_ALL


def ask_choice(prompt, columns, suggested=None, allow_none=True):
    cols = list(columns)
    print("\n" + H(prompt))
    if suggested:
        print(DIM(f"Suggestion détectée : {suggested}"))
    for i, c in enumerate(cols, 1):
        print(f"  {Fore.MAGENTA}{i}.{Style.RESET_ALL} {c}")
    if allow_none:
        print(f"  {Fore.MAGENTA}0.{Style.RESET_ALL} (laisser vide)")

    while True:
        raw = input("> ").strip()
        if raw == "" and suggested:
            return suggested
        if allow_none and raw == "0":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(cols):
            return cols[int(raw) - 1]
        if raw in cols:
            return raw
        print(WARN("Choix invalide. Réessaie 🙂"))


def ask_yes_no(prompt, default_yes=True):
    hint = "[O/n]" if default_yes else "[o/N]"
    while True:
        raw = input(f"{prompt} {DIM(hint)} ").strip().lower()
        if raw == "":
            return default_yes
        if raw in ("o","oui","y","yes"):
            return True
        if raw in ("n","non","no"):
            return False
        print(WARN("Réponds par oui/non."))
