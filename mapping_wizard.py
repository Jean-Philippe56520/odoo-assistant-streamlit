import re, unicodedata
import pandas as pd
from rapidfuzz import fuzz, process

try:
    from .console_utils import H, OK, WARN, DIM, ask_choice, ask_yes_no
    from .odoo_client import find_or_create_tag
except ImportError:
    from console_utils import H, OK, WARN, DIM, ask_choice, ask_yes_no
    from odoo_client import find_or_create_tag


def norm(s: str) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


SUGGESTIONS = {
    "name": ["societe","raisonsociale","enseigne","nom","client","prospect","entreprise","etablissement","company","lead"],
    "tag_ids": ["etiquette","etiquettes","tag","tags","source","origine","evenement","salon","campagne","labels"],
    "seller_col": ["vendeur","commercial","sales","owner","assigne","attribue","responsable"],
    "partner_name": ["societe","raisonsociale","enseigne","entreprise","company"],
    "contact_name": ["contact","interlocuteur","nomcontact","responsable"],
    "email_from": ["email","e-mail","mail","courriel"],
    "phone": ["tel","telephone","téléphone","fixe","phone"],
    "mobile": ["mobile","gsm","portable","cell"],
    "website": ["site","siteweb","url","website"],
    "street": ["adresse","adresse1","rue","street","address"],
    "street2": ["adresse2","complement","address2"],
    "zip": ["cp","codepostal","postal","zip"],
    "city": ["ville","commune","city"],
    "country_id": ["pays","country"],
    "date_deadline": ["echeance","deadline","cloture"],
}

NOTE_HINTS = set(map(norm, [
    "commentaire","commentaires","notes","note","remarque","infos","besoin",
    "comment","comments","details","need","interest"
]))


def autosuggest_mapping(columns):
    cols_norm = {c: norm(c) for c in columns}
    mapping, confidence = {}, {}

    for field, keys in SUGGESTIONS.items():
        best, best_score = None, 0
        for col_raw, col_n in cols_norm.items():
            for k in keys:
                if col_n == k:
                    score = 100
                elif k in col_n:
                    score = 70
                else:
                    score = 0
                if score > best_score:
                    best_score = score
                    best = col_raw
        if best_score >= 70:
            mapping[field] = best
            confidence[field] = "haute" if best_score == 100 else "moyenne"

    note_cols = [c for c, cn in cols_norm.items() if any(h in cn for h in NOTE_HINTS)]
    return mapping, confidence, note_cols


def run_mapping_wizard(columns):
    suggested, conf, _note_cols = autosuggest_mapping(columns)

    print(H("\n🤖✨ AUTO-SUGGESTIONS Détectées"))
    for f, col in suggested.items():
        level = conf.get(f)
        badge = "🟢" if level == "haute" else "🟡"
        print(f"  {badge} {f}  →  {OK(col)}  {DIM(f'(confiance {level})')}")

    mapping = {}

    mapping["name"] = ask_choice(
        "📝 Choisis la colonne pour le Titre de la piste (obligatoire).",
        columns, suggested.get("name"), allow_none=False
    )

    if suggested.get("tag_ids"):
        use_col = ask_yes_no(f"🏷️  J'ai repéré une colonne étiquette '{suggested['tag_ids']}'. Utiliser ?")
    else:
        use_col = False

    if use_col:
        mapping["tag_ids"] = suggested["tag_ids"]
        mapping["tag_fixed"] = None
    else:
        col = ask_choice(
            "🏷️  Choisis une colonne pour les Étiquettes (ou 0 pour valeur fixe).",
            columns, suggested.get("tag_ids"), allow_none=True
        )
        if col:
            mapping["tag_ids"] = col
            mapping["tag_fixed"] = None
        else:
            fixed = input("Entre la valeur fixe d’étiquette (obligatoire) : ").strip()
            mapping["tag_ids"] = None
            mapping["tag_fixed"] = fixed

    essentials = [
        ("partner_name", "Nom de la société / enseigne"),
        ("contact_name", "Nom du contact / interlocuteur"),
        ("email_from", "Email"),
        ("phone", "Téléphone"),
        ("mobile", "Mobile"),
        ("website", "Site web"),
        ("street", "Adresse (ligne 1)"),
        ("street2", "Adresse (ligne 2)"),
        ("zip", "Code postal"),
        ("city", "Ville"),
        ("country_id", "Pays"),
        ("date_deadline", "Date de clôture prévue"),
    ]

    print(H("\n📌 Mapping des champs commerciaux (facultatifs)"))
    for f, label in essentials:
        mapping[f] = ask_choice(
            f"👉 Colonne pour {label} ?",
            columns, suggested.get(f), allow_none=True
        )

    mapping["use_seller_col"] = False
    mapping["seller_col"] = None
    if suggested.get("seller_col"):
        if ask_yes_no(
            f"🧑‍💼 J'ai détecté une colonne vendeur '{suggested['seller_col']}'. "
            f"Tu veux l'utiliser pour affecter chaque piste ?",
            default_yes=True
        ):
            mapping["use_seller_col"] = True
            mapping["seller_col"] = suggested["seller_col"]

    notes_cfg = []
    return mapping, notes_cfg


def notes_wizard(columns, note_cols):
    print(H("\n🗒️ NOTES INTERNES — choix rapide"))

    if note_cols:
        print(DIM("Colonnes candidates détectées :"))
        for c in note_cols:
            print(f"   • {c}")
    else:
        print(DIM("Aucune colonne candidate détectée automatiquement."))

    print("\nQue veux-tu faire ?")
    print("  1. ✅ Accepter les suggestions")
    print("  2. ✍️ Choisir manuellement")
    print("  3. 🚫 Pas de notes")

    while True:
        raw = input("> ").strip()
        if raw in ("1","2","3"):
            break
        print(WARN("Choix invalide (1/2/3)."))

    notes_cfg = []

    if raw == "3":
        return notes_cfg

    if raw == "1":
        if not note_cols:
            print(WARN("Pas de suggestions, on passe en manuel."))
            raw = "2"
        else:
            print(OK("✅ Suggestions acceptées."))
            for col in note_cols:
                label = input(f"Label à afficher pour '{col}' (laisser vide pour brut) : ").strip()
                notes_cfg.append((col, label))
            return notes_cfg

    print(H("\n✍️ Sélection manuelle des colonnes Notes"))
    while True:
        print("\nSélectionne une ou plusieurs colonnes pour Notes (ex: 5 10). 0 pour arrêter.")
        for i, c in enumerate(columns, 1):
            print(f"  {i}. {c}")
        print("  0. (terminer)")

        raw2 = input("> ").strip()
        if raw2 == "0" or raw2 == "":
            break

        parts = re.split(r"[,\s;|]+", raw2)
        nums = []
        ok_flag = True
        for p in parts:
            if not p:
                continue
            if not p.isdigit():
                ok_flag = False
                break
            n = int(p)
            if n < 1 or n > len(columns):
                ok_flag = False
                break
            nums.append(n)

        if not ok_flag or not nums:
            print(WARN("Choix invalide. Exemple : 5 10"))
            continue

        seen = set()
        for n in nums:
            if n in seen:
                continue
            seen.add(n)
            col = columns[n - 1]
            label = input(f"Label à afficher pour '{col}' (laisser vide pour brut) : ").strip()
            notes_cfg.append((col, label))

    return notes_cfg


def preview_row_full(df, row_idx, mapping, notes_cfg, seller_name=None):
    row = df.iloc[row_idx].to_dict()
    d = {}
    d["Titre"] = str(row.get(mapping.get("name"), "")).strip()

    if mapping.get("tag_fixed"):
        d["Étiquette"] = mapping["tag_fixed"]
    else:
        tag_col = mapping.get("tag_ids")
        raw_tag = str(row.get(tag_col, "")).strip() if tag_col else ""
        if raw_tag:
            d["Étiquette"] = raw_tag

    field_labels = {
        "partner_name": "Société",
        "contact_name": "Contact",
        "email_from": "Email",
        "phone": "Téléphone",
        "mobile": "Mobile",
        "website": "Site web",
        "street": "Adresse 1",
        "street2": "Adresse 2",
        "zip": "Code postal",
        "city": "Ville",
        "country_id": "Pays",
        "date_deadline": "Échéance",
    }

    for f, lab in field_labels.items():
        col = mapping.get(f)
        if col:
            v = row.get(col)
            if pd.notna(v) and str(v).strip():
                d[lab] = str(v).strip()

    notes_parts = []
    for col, label in notes_cfg:
        v = row.get(col)
        if pd.notna(v) and str(v).strip():
            lbl = label.strip() if label else col
            notes_parts.append(f"📌 {lbl}\n{str(v).strip()}")

    if notes_parts:
        d["Notes"] = "\n\n\n".join(notes_parts)

    if seller_name:
        d["Vendeur"] = seller_name

    return {k: v for k, v in d.items() if v}


def print_preview_block(title, df, mapping, notes_cfg):
    print(H(f"\n{title} — 3 premières lignes"))
    for i in range(min(3, len(df))):
        prev = preview_row_full(df, i, mapping, notes_cfg)
        print(f"\nLigne {i+1}:")
        for k, v in prev.items():
            if k == "Notes":
                print(f"  🗒️  {k}:\n{v}")
            else:
                print(f"  • {k}: {v}")
