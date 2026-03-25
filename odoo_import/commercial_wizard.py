import re
import sys
from datetime import datetime, timedelta

try:
    from .config import ODOO_DB, ODOO_API_KEY, LEAD_MODEL
    from .console_utils import H, OK, WARN, ERR, DIM
    from .odoo_client import (
        odoo_connect,
        find_team_ventes,
        get_active_sales_users,
        lead_exists,
        find_or_create_tag,
    )
except ImportError:
    from config import ODOO_DB, ODOO_API_KEY, LEAD_MODEL
    from console_utils import H, OK, WARN, ERR, DIM
    from odoo_client import (
        odoo_connect,
        find_team_ventes,
        get_active_sales_users,
        lead_exists,
        find_or_create_tag,
    )

PROSPECTION_TAG = "Prospection"


def normalize_text(value):
    return str(value or "").strip()


def normalize_email(value):
    return normalize_text(value).lower()


def normalize_phone(value):
    raw = normalize_text(value)
    if not raw:
        return ""
    return re.sub(r"\s+", " ", raw)


def comparable_phone(value):
    return re.sub(r"\D", "", normalize_text(value))


def validate_email(value):
    email = normalize_email(value)
    if not email:
        return True, None, ""
    if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return True, None, email
    return False, "Email invalide.", None


def validate_phone(value):
    phone = normalize_phone(value)
    if not phone:
        return True, None, ""
    digits = comparable_phone(phone)
    if len(digits) < 8:
        return False, "Téléphone trop court.", None
    return True, None, phone


def validate_date(value):
    raw = normalize_text(value)
    if not raw:
        return True, None, ""

    shortcuts = {
        "7j": 7,
        "15j": 15,
        "30j": 30,
    }
    lower = raw.lower()
    if lower in shortcuts:
        dt = datetime.today().date()
        return True, None, (dt + timedelta(days=shortcuts[lower])).strftime("%Y-%m-%d")

    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return True, None, dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return False, "Date invalide. Formats acceptés : JJ/MM/AAAA, AAAA-MM-JJ, 7j, 15j, 30j.", None


def ask_text(label, required=False, default=None, validator=None):
    while True:
        suffix = f" {DIM(f'(Entrée = {default})')}" if default else ""
        raw = input(f"{label}{suffix} > ").strip()

        if raw.lower() in ("stop", "quitter"):
            print(WARN("Saisie interrompue."))
            sys.exit(0)

        if raw == "" and default is not None:
            raw = default

        if raw == "":
            if required:
                print(WARN("Champ obligatoire."))
                continue
            return ""

        if validator:
            ok, msg, normalized = validator(raw)
            if not ok:
                print(WARN(msg))
                continue
            return normalized

        return raw


def ask_yes_no(label, default_yes=True):
    prompt = "[O/n]" if default_yes else "[o/N]"
    while True:
        raw = input(f"{label} {prompt} > ").strip().lower()
        if raw in ("stop", "quitter"):
            print(WARN("Saisie interrompue."))
            sys.exit(0)
        if raw == "":
            return default_yes
        if raw in ("o", "oui", "y", "yes"):
            return True
        if raw in ("n", "non", "no"):
            return False
        print(WARN("Réponse attendue : oui ou non."))


def ask_duplicate_action():
    print(H("\n🤔 Un lead similaire a été détecté"))
    print("Choisissez une action :")
    print("  1. Mettre à jour le lead existant")
    print("  2. Créer un nouveau lead quand même")
    print("  3. Revenir à la correction")
    print("  4. Annuler")

    while True:
        raw = input("Votre choix [1/2/3/4] > ").strip().lower()
        if raw in ("stop", "quitter"):
            print(WARN("Saisie interrompue."))
            sys.exit(0)

        if raw in {"1", "2", "3", "4"}:
            return raw

        print(WARN("Choix invalide. Tapez 1, 2, 3 ou 4."))


def confirm_duplicate_action(choice):
    if choice == "1":
        return ask_yes_no("Confirmer la mise à jour du lead existant ?", default_yes=False)
    if choice == "2":
        return ask_yes_no(
            "Confirmer la création d'un nouveau lead malgré la similarité détectée ?",
            default_yes=False,
        )
    if choice == "4":
        return ask_yes_no("Confirmer l'annulation complète ?", default_yes=False)
    return True


def build_title(answers):
    company = normalize_text(answers.get("partner_name"))
    contact = normalize_text(answers.get("contact_name"))

    if company and contact:
        return f"{company} - {contact}"
    if company:
        return f"Prospection - {company}"
    return "Piste sans nom"


def build_new_note_block(answers):
    parts = []
    stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
    parts.append(f"--- Saisie prospection du {stamp} ---")

    current_equipment = normalize_text(answers.get("current_equipment"))
    if current_equipment:
        parts.append(f"📌 Équipement actuel\n{current_equipment}")

    free_comment = normalize_text(answers.get("free_comment"))
    if free_comment:
        parts.append(f"📌 Commentaire libre\n{free_comment}")

    return "\n\n".join(parts)


def build_description_for_create(answers):
    block = build_new_note_block(answers)
    return block if block.strip() else ""


def merge_descriptions(existing_description, answers):
    new_block = build_new_note_block(answers).strip()
    old = normalize_text(existing_description)

    if old and new_block:
        return f"{old}\n\n{new_block}"
    if new_block:
        return new_block
    return old


def build_vals_from_answers(answers, team_id, seller_user_id, replace_tags=True, existing_description=None):
    vals = {
        "name": build_title(answers),
        "user_id": seller_user_id,
    }

    for field in (
        "partner_name",
        "contact_name",
        "email_from",
        "phone",
        "mobile",
        "website",
        "street",
        "street2",
        "zip",
        "city",
        "date_deadline",
    ):
        value = normalize_text(answers.get(field))
        if value:
            vals[field] = value

    if team_id:
        vals["team_id"] = team_id

    if replace_tags:
        description = build_description_for_create(answers)
    else:
        description = merge_descriptions(existing_description, answers)

    if description:
        vals["description"] = description

    tag_id = find_or_create_tag(answers["_models"], answers["_uid"], PROSPECTION_TAG)
    vals["tag_ids"] = [(6, 0, [tag_id])] if replace_tags else [(4, tag_id)]

    return vals


def preview_answers(vals, seller_name):
    print(H("\n🧾 Prévisualisation de la piste"))
    print(f"  • Vendeur confirmé: {seller_name}")

    labels = {
        "name": "Titre",
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
        "date_deadline": "Date de clôture prévue",
        "description": "Notes",
    }
    for key, label in labels.items():
        value = vals.get(key)
        if value:
            if key == "description":
                print(f"  • {label}:\n{value}")
            else:
                print(f"  • {label}: {value}")

    print(f"  • Étiquette: {PROSPECTION_TAG}")


def choose_confirmed_seller(uid, models):
    sales_users = get_active_sales_users(models, uid)
    if not sales_users:
        print(WARN("Aucun vendeur actif trouvé. L'utilisateur connecté sera utilisé."))
        return uid, "Utilisateur connecté"

    while True:
        print(H("\n🧑‍💼 Identification du commercial"))
        for i, user in enumerate(sales_users, 1):
            print(f"  {i}. {user['name']}")

        raw = ask_text("Choisis ton numéro vendeur", required=True)
        if not raw.isdigit():
            print(WARN("Merci de saisir un numéro de la liste."))
            continue

        index = int(raw)
        if not (1 <= index <= len(sales_users)):
            print(WARN("Numéro hors liste."))
            continue

        seller = sales_users[index - 1]
        if ask_yes_no(f"Tu confirmes être {seller['name']} ?", default_yes=True):
            return seller["id"], seller["name"]

        if not ask_yes_no("Veux-tu choisir un autre vendeur ?", default_yes=True):
            print(WARN("Identification annulée."))
            sys.exit(0)


def detect_existing_lead(models, uid, answers):
    email = normalize_email(answers.get("email_from"))
    phone = normalize_phone(answers.get("phone"))
    mobile = normalize_phone(answers.get("mobile"))
    return lead_exists(models, uid, email, phone, mobile)


def read_lead_summary(models, uid, lead_id):
    try:
        rows = models.execute_kw(
            ODOO_DB,
            uid,
            ODOO_API_KEY,
            LEAD_MODEL,
            "read",
            [[lead_id]],
            {
                "fields": [
                    "name",
                    "partner_name",
                    "contact_name",
                    "email_from",
                    "phone",
                    "mobile",
                    "user_id",
                    "description",
                ]
            },
        )
        return rows[0] if rows else None
    except Exception:
        return None


def show_existing_lead_summary(existing_data):
    if not existing_data:
        print(WARN("Impossible de lire le détail du lead existant."))
        return

    print(H("\n🔎 Lead déjà détecté"))
    seller = ""
    user_id = existing_data.get("user_id")
    if isinstance(user_id, list) and len(user_id) >= 2:
        seller = user_id[1]

    mapping = {
        "name": "Titre",
        "partner_name": "Société",
        "contact_name": "Contact",
        "email_from": "Email",
        "phone": "Téléphone",
        "mobile": "Mobile",
    }
    for key, label in mapping.items():
        value = normalize_text(existing_data.get(key))
        if value:
            print(f"  • {label}: {value}")
    if seller:
        print(f"  • Vendeur actuel: {seller}")


def ensure_minimum_contact(answers):
    if any(normalize_text(answers.get(k)) for k in ("phone", "mobile", "email_from")):
        return True
    print(WARN("Il faut au moins un moyen de contact : téléphone, mobile ou email."))
    return False


FIELD_ORDER = [
    ("partner_name", "Nom de l'entreprise", True, None),
    ("contact_name", "Nom du contact", False, None),
    ("phone", "Téléphone", False, validate_phone),
    ("mobile", "Mobile", False, validate_phone),
    ("email_from", "Email", False, validate_email),
    ("website", "Site web", False, None),
    ("street", "Adresse", False, None),
    ("street2", "Complément d'adresse", False, None),
    ("zip", "Code postal", False, None),
    ("city", "Ville", False, None),
    ("date_deadline", "Date de clôture prévue", False, validate_date),
    ("current_equipment", "Équipement actuel", False, None),
    ("free_comment", "Commentaire libre", False, None),
]


def ask_commercial_answers():
    print(H("\n🧭 Assistant de saisie prospection"))
    print(DIM("Tape 'stop' pour quitter à tout moment."))

    answers = {}

    while True:
        print(H("\nÉtape 1/3 — Contact"))
        answers["partner_name"] = ask_text("Nom de l'entreprise", required=True)
        answers["contact_name"] = ask_text("Nom du contact")
        answers["phone"] = ask_text("Téléphone", validator=validate_phone)
        answers["mobile"] = ask_text("Mobile", validator=validate_phone)
        answers["email_from"] = ask_text("Email", validator=validate_email)
        answers["website"] = ask_text("Site web")

        print(H("\nÉtape 2/3 — Adresse"))
        answers["street"] = ask_text("Adresse")
        answers["street2"] = ask_text("Complément d'adresse")
        answers["zip"] = ask_text("Code postal")
        answers["city"] = ask_text("Ville")
        answers["date_deadline"] = ask_text("Date de clôture prévue", validator=validate_date)

        print(H("\nÉtape 3/3 — Notes utiles"))
        answers["current_equipment"] = ask_text("Équipement actuel")
        answers["free_comment"] = ask_text("Commentaire libre")

        if ensure_minimum_contact(answers):
            return answers

        print(WARN("Merci de compléter au moins un moyen de contact."))
        answers["phone"] = ask_text("Téléphone", validator=validate_phone, default=answers.get("phone") or None)
        answers["mobile"] = ask_text("Mobile", validator=validate_phone, default=answers.get("mobile") or None)
        answers["email_from"] = ask_text("Email", validator=validate_email, default=answers.get("email_from") or None)
        if ensure_minimum_contact(answers):
            return answers


def edit_answers_loop(answers):
    while True:
        print(H("\n✏️ Correction avant envoi"))
        for idx, (key, label, required, validator) in enumerate(FIELD_ORDER, 1):
            value = normalize_text(answers.get(key))
            display = value if value else "-"
            print(f"  {idx}. {label}: {display}")

        raw = input("Numéro du champ à corriger (Entrée = continuer) > ").strip()
        if raw.lower() in ("stop", "quitter"):
            print(WARN("Saisie interrompue."))
            sys.exit(0)

        if raw == "":
            if ensure_minimum_contact(answers):
                return answers
            print(WARN("Impossible de continuer sans moyen de contact."))
            continue

        if not raw.isdigit():
            print(WARN("Merci de saisir un numéro valide."))
            continue

        idx = int(raw)
        if not (1 <= idx <= len(FIELD_ORDER)):
            print(WARN("Numéro hors liste."))
            continue

        key, label, required, validator = FIELD_ORDER[idx - 1]
        current = normalize_text(answers.get(key)) or None
        answers[key] = ask_text(label, required=required, default=current, validator=validator)


def run_single_capture(uid, models, team_id, seller_user_id, seller_name):
    answers = ask_commercial_answers()

    while True:
        answers = edit_answers_loop(answers)
        answers["_uid"] = uid
        answers["_models"] = models

        existing = detect_existing_lead(models, uid, answers)
        existing_data = read_lead_summary(models, uid, existing) if existing else None

        replace_tags = existing is None
        existing_description = existing_data.get("description") if existing_data else None
        vals = build_vals_from_answers(
            answers,
            team_id,
            seller_user_id,
            replace_tags=replace_tags,
            existing_description=existing_description,
        )

        preview_answers(vals, seller_name)

        if not existing:
            if not ask_yes_no("Confirmer la création de cette piste dans Odoo ?", default_yes=False):
                if ask_yes_no("Revenir à la correction ?", default_yes=True):
                    continue
                print(WARN("Création annulée."))
                return

            lead_id = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, LEAD_MODEL, "create", [vals])
            print(OK(f"\n✅ Piste créée dans Odoo (ID {lead_id})"))
            return

        print(WARN(f"\n⚠️ Un lead similaire existe déjà (ID {existing})."))
        print(DIM("Vous pouvez le mettre à jour, créer une nouvelle piste, revenir à la correction ou annuler."))
        show_existing_lead_summary(existing_data)

        while True:
            action = ask_duplicate_action()

            if action == "3":
                print(WARN("Retour à la correction de la saisie."))
                break

            if not confirm_duplicate_action(action):
                print(WARN("Action non confirmée."))
                if ask_yes_no("Revenir au choix d'action ?", default_yes=True):
                    continue
                print(WARN("Opération annulée."))
                return

            if action == "1":
                models.execute_kw(
                    ODOO_DB,
                    uid,
                    ODOO_API_KEY,
                    LEAD_MODEL,
                    "write",
                    [[existing], vals],
                )
                print(OK(f"\n✅ Piste mise à jour (ID {existing})"))
                return

            if action == "2":
                create_vals = build_vals_from_answers(
                    answers,
                    team_id,
                    seller_user_id,
                    replace_tags=True,
                    existing_description=None,
                )
                lead_id = models.execute_kw(
                    ODOO_DB,
                    uid,
                    ODOO_API_KEY,
                    LEAD_MODEL,
                    "create",
                    [create_vals],
                )
                print(OK(f"\n✅ Nouvelle piste créée dans Odoo (ID {lead_id})"))
                return

            if action == "4":
                print(WARN("Création annulée."))
                return


def run_commercial_capture():
    print(H("\n🛠️ Assistant de saisie prospection V2.1"))

    if not ODOO_API_KEY:
        print(ERR("❌ ODOO_API_KEY manquante."))
        sys.exit(1)

    uid, models = odoo_connect()
    team_id = find_team_ventes(models, uid)
    if not team_id:
        print(WARN("⚠️ Équipe 'Ventes' introuvable. team_id ignoré."))

    seller_user_id, seller_name = choose_confirmed_seller(uid, models)

    while True:
        run_single_capture(uid, models, team_id, seller_user_id, seller_name)
        print(H("\n🎉 Fin de la saisie guidée."))
        if not ask_yes_no("Créer une autre piste ?", default_yes=False):
            break
