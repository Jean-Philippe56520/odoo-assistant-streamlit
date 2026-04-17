APP_TITLE = "Saisie prospection Odoo V2"
APP_CAPTION = (
    "Version web sécurisée par identifiant partagé, avec contrôle des leads similaires, "
    "confirmation finale, et planification optionnelle d'activité commerciale."
)

DEFAULT_DUPLICATE_ACTION = "Mettre à jour le lead existant"

# Clés de session Streamlit globales
APP_STATE_KEYS = (
    "form_data",
    "preview_data",
    "preview_vals",
    "existing_id",
    "existing_data",
    "seller_name",
    "seller_user_id",
    "result_banner",
    "pending_form_reset",
    "pending_preview_reset",
)

# Champs du formulaire principal
FORM_FIELD_KEYS = (
    "partner_name",
    "contact_name",
    "phone",
    "mobile",
    "email_from",
    "street",
    "street2",
    "zip",
    "city",
    "current_equipment",
    "free_comment",
    # Bloc activité
    "create_activity",
    "activity_type",
    "activity_summary",
    "activity_date_mode",
    "activity_custom_date",
)

# Types d'activités gérés côté interface
ACTIVITY_TYPE_LABELS = (
    "To-Do",
    "Appel",
    "Email",
)

DEFAULT_ACTIVITY_TYPE = "To-Do"
DEFAULT_ACTIVITY_SUMMARY = "Relance commerciale"

# Modes de date proposés au commercial
ACTIVITY_DATE_MODES = (
    "J+7",
    "J+30",
    "Choisir une date",
)

DEFAULT_ACTIVITY_DATE_MODE = "J+7"

# Libellés et textes UX
ACTIVITY_SECTION_TITLE = "Relance / activité commerciale"
ACTIVITY_TOGGLE_LABEL = "Prévoir une activité de relance"
ACTIVITY_TOGGLE_HELP = (
    "Optionnel. Cochez cette case pour planifier une prochaine action commerciale "
    "liée à la piste créée dans Odoo."
)

ACTIVITY_SUMMARY_LABEL = "Résumé"
ACTIVITY_SUMMARY_PLACEHOLDER = "Ex. : rappeler pour proposer un rendez-vous"

ACTIVITY_TYPE_LABEL = "Type d'activité"
ACTIVITY_DATE_LABEL = "Date de relance"
ACTIVITY_CUSTOM_DATE_LABEL = "Choisir une date"
ACTIVITY_PREVIEW_LABEL = "Relance prévue le"

# Messages de validation
ERROR_ACTIVITY_TYPE_REQUIRED = "Le type d'activité est obligatoire."
ERROR_ACTIVITY_SUMMARY_REQUIRED = "Le résumé de l'activité est obligatoire."
ERROR_ACTIVITY_DATE_REQUIRED = "La date de relance est obligatoire."
ERROR_ACTIVITY_DATE_PAST = "La date de relance ne peut pas être dans le passé."
ERROR_ACTIVITY_CUSTOM_DATE_INVALID = "La date personnalisée de relance est invalide."
