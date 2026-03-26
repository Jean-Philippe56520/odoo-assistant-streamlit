import sys

from .config import ODOO_API_KEY
from .console_utils import H, OK, WARN, ERR, DIM
from .odoo_client import odoo_connect, find_team_ventes, get_active_sales_users
from .lead_service import (
    PROSPECTION_TAG,
    validate_email,
    validate_phone,
    ensure_minimum_contact,
    normalize_text,
    prepare_lead_preview,
    build_vals_from_answers,
    create_new_lead,
    update_existing_lead,
)


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
        "street": "Adresse 1",
        "street2": "Adresse 2",
        "zip": "Code postal",
        "city": "Ville",
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


FIELD_ORDER = [
    ("partner_name", "Nom de l'entreprise", True, None),
    ("contact_name", "Nom du contact", False, None),
    ("phone", "Téléphone", False, validate_phone),
    ("mobile", "Mobile", False, validate_phone),
    ("email_from", "Email", False, validate_email),
    ("street", "Adresse", False, None),
    ("street2", "Complément d'adresse", False, None),
    ("zip", "Code postal", False, None),
    ("city", "Ville", False, None),
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

        print(H("\nÉtape 2/3 — Adresse"))
        answers["street"] = ask_text("Adresse")
        answers["street2"] = ask_text("Complément d'adresse")
        answers["zip"] = ask_text("Code postal")
        answers["city"] = ask_text("Ville")

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


def run_single_capture(uid, models, team_id, seller_user_id, seller_name):
    answers = ask_commercial_answers()

    while True:
        answers = edit_answers_loop(answers)

        preview = prepare_lead_preview(
            uid=uid,
            models=models,
            raw_data=answers,
            team_id=team_id,
            seller_user_id=seller_user_id,
            seller_name=None,
            actor_user=None,
            audit_mode=None,
        )

        if not preview.is_valid:
            for error in preview.errors:
                print(WARN(error))
            continue

        preview_answers(preview.vals, seller_name)

        if not preview.existing_match:
            if not ask_yes_no("Confirmer la création de cette piste dans Odoo ?", default_yes=False):
                if ask_yes_no("Revenir à la correction ?", default_yes=True):
                    continue
                print(WARN("Création annulée."))
                return

            result = create_new_lead(models, uid, preview.vals)
            print(OK(f"\n✅ {result.message}"))
            return

        existing_id = preview.existing_match.lead_id
        existing_data = preview.existing_match.summary

        print(WARN(f"\n⚠️ Un lead similaire existe déjà (ID {existing_id})."))
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
                result = update_existing_lead(models, uid, existing_id, preview.vals)
                print(OK(f"\n✅ {result.message}"))
                return

            if action == "2":
                create_vals = build_vals_from_answers(
                    preview.cleaned_data,
                    team_id,
                    seller_user_id,
                    replace_tags=True,
                    existing_description=None,
                )
                result = create_new_lead(models, uid, create_vals)
                print(OK(f"\n✅ {result.message}"))
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