import os, re, sys, unicodedata
import pandas as pd
from .config import FILES_DIR, ALLOWED_EXT, FORCE_CREATE, ODOO_DB, ODOO_API_KEY, LEAD_MODEL
from .console_utils import H, OK, WARN, ERR, DIM
from .odoo_client import (
    odoo_connect, find_team_ventes, get_active_sales_users,
    lead_exists, find_or_create_tag
)
from .mapping_wizard import autosuggest_mapping, run_mapping_wizard, notes_wizard, print_preview_block

def pick_file():
    if not os.path.isdir(FILES_DIR):
        print(ERR(f"[ERREUR] Dossier introuvable : {FILES_DIR}"))
        sys.exit(1)

    files = [f for f in os.listdir(FILES_DIR) if f.lower().endswith(ALLOWED_EXT)]
    files.sort()

    if not files:
        print(ERR(f"[ERREUR] Aucun fichier CSV/XLSX trouvé dans {FILES_DIR}"))
        sys.exit(1)

    print(H("\n📂 Fichiers disponibles dans /fichiers :"))
    for i, f in enumerate(files, 1):
        print(f"  {i}. {f}")

    while True:
        raw = input("Choisis un numéro de fichier > ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(files):
            return os.path.join(FILES_DIR, files[int(raw)-1])
        print(WARN("Numéro invalide."))

def load_file(path):
    p = path.lower()
    if p.endswith(".csv"):
        return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    if p.endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    raise ValueError("Format non supporté. CSV ou XLSX.")

def build_vals_from_row(row, mapping, notes_cfg, models, uid, team_id, default_seller_user_id):
    vals = {}
    vals["name"] = str(row.get(mapping["name"], "")).strip() or "Piste sans nom"

    for f in ("partner_name","contact_name","email_from","phone","mobile","website",
              "street","street2","zip","city","country_id","date_deadline"):
        col = mapping.get(f)
        if col:
            v = row.get(col)
            if pd.notna(v) and str(v).strip():
                vals[f] = str(v).strip()

    if team_id:
        vals["team_id"] = team_id

    tags = []
    if mapping.get("tag_fixed"):
        tags.append(find_or_create_tag(models, uid, mapping["tag_fixed"]))
    else:
        tag_col = mapping.get("tag_ids")
        if tag_col:
            raw_tag = row.get(tag_col)
            if pd.notna(raw_tag) and str(raw_tag).strip():
                for p in re.split(r"[;,/|]+", str(raw_tag)):
                    t = p.strip()
                    if t:
                        tags.append(find_or_create_tag(models, uid, t))
    if tags:
        vals["tag_ids"] = [(6, 0, tags)]

    notes_parts = []
    for col, label in notes_cfg:
        v = row.get(col)
        if pd.notna(v) and str(v).strip():
            lbl = label.strip() if label else col
            notes_parts.append(f"📌 {lbl}\n{str(v).strip()}")

    if notes_parts:
        vals["description"] = "\n\n\n".join(notes_parts)

    vals["user_id"] = default_seller_user_id
    return vals


def run_import():
    print(H("\n🛠️  Wizard Import Pistes Odoo — ABM Edition ✨"))

    if not ODOO_API_KEY:
        print(ERR("❌ ODOO_API_KEY manquante."))
        sys.exit(1)

    path = pick_file()
    print(OK(f"\n✅ OK, je travaille sur : {path}"))

    df = load_file(path)
    df.columns = [str(c).strip() for c in df.columns]
    columns = list(df.columns)

    print(H(f"\n📑 Colonnes détectées ({len(columns)})"))
    print(DIM(str(columns)))

    mapping, notes_cfg = run_mapping_wizard(columns)
    print_preview_block("🔍 PREVIEW 1 (champs mappés)", df, mapping, notes_cfg)

    uid, models = odoo_connect()
    team_id = find_team_ventes(models, uid)
    if not team_id:
        print(WARN("⚠️ Équipe 'Ventes' introuvable. team_id ignoré."))

    _, _, note_cols = autosuggest_mapping(columns)
    notes_cfg = notes_wizard(columns, note_cols)

    sales_users = get_active_sales_users(models, uid)
    print(H("\n🧑‍💼 Vendeurs disponibles dans Odoo :"))
    for i, u in enumerate(sales_users, 1):
        print(f"  {i}. {u['name']}")

    raw = input("Choisis le vendeur par défaut (Entrée = toi) > ").strip()
    if raw.isdigit() and 1 <= int(raw) <= len(sales_users):
        default_seller_user_id = sales_users[int(raw)-1]["id"]
    else:
        default_seller_user_id = uid

    print_preview_block("🧾 PREVIEW 2 (finale)", df, mapping, notes_cfg)

    if input("\n🚀 On lance l’import final ? [O/n] ").strip().lower() in ("n","non","no"):
        print(WARN("Import annulé."))
        return

    created, updated = 0, 0
    total = len(df)
    print(H(f"\n📦 Import en cours… {total} lignes à traiter"))
    if FORCE_CREATE:
        print(WARN("⚠️ MODE FORCE_CREATE actif : aucune mise à jour ne sera faite."))

    for idx, (_, r) in enumerate(df.iterrows(), 1):
        row = r.to_dict()
        vals = build_vals_from_row(row, mapping, notes_cfg, models, uid, team_id, default_seller_user_id)

        if FORCE_CREATE:
            existing = False
        else:
            existing = lead_exists(models, uid, vals.get("email_from"), vals.get("phone"), vals.get("mobile"))

        if existing:
            models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, LEAD_MODEL, "write", [[existing], vals])
            updated += 1
        else:
            models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, LEAD_MODEL, "create", [vals])
            created += 1

        if idx % 10 == 0 or idx == total:
            print(DIM(f"   ➜ {idx}/{total} lignes traitées…"))

    print(OK(f"\n✅ Import terminé. Créées: {created} | Mises à jour: {updated}"))
    print(H("\n🎉 Fin du wizard. Bonne chasse aux pistes !"))
