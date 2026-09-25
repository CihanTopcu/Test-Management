"""Runtime configuration, read from the environment."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DGTest"
    api_port: int = 8010
    debug: bool = False

    database_url: str = (
        "postgresql+psycopg://tm:tm@localhost:5432/testmgmt"
    )
    # where attachment blobs live; a mounted volume on-prem
    storage_dir: str = "/var/lib/testmgmt/attachments"

    secret_key: str = "change-me"

    # request throttling; off in the test suite, on everywhere else
    rate_limit_enabled: bool = True
    access_token_ttl_minutes: int = 8 * 60

    # kept so imported TestRail links keep working during the transition
    legacy_testrail_url: str = "https://dgpaysit.testrail.com"

    # where the app is reachable, used to build links inside e-mail
    public_url: str = "http://localhost:5173"

    # Jira, read only: an issue key in a case's refs or a result's defects
    # becomes a link, with the issue's status and summary beside it
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""

    # single sign-on (OpenID Connect); for Entra ID the issuer is
    # https://login.microsoftonline.com/<tenant id>/v2.0
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_label: str = "Microsoft"

    # mail is optional: with no host configured everything still lands in the
    # in-app notification list
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "test-yonetimi@dgpays.com"
    smtp_ssl: bool = False
    smtp_starttls: bool = True

    # first-run administrator; the password is generated and logged once if
    # this is left empty
    bootstrap_email: str = "admin@dgpays.com"
    bootstrap_password: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
